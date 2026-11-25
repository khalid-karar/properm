"""Load finance data from SAP, Oracle, Odoo or any spreadsheet into the non-labour cost ledger. Preview first (commit=false), then commit.

The column names below are the ones those systems commonly use in their standard exports. Exports vary by customer configuration, so the preview shows
every row and what it was read as: check it against your own export before committing. A row needs a project number that already exists in PROPERM."""
import base64
import binascii
import re

from fastapi import APIRouter, Depends, HTTPException

from .. import tabular
from ..audit import log
from ..deps import get_db, require_roles
from ..models import CostEntry, Project, User
from .imports import MAX_FILE, ImportIn, _s, _verdict

router = APIRouter(tags=["imports"])

# field -> accepted header names (lower case, spaces and punctuation ignored)
ALIASES = {
    "project": ["project", "projectnumber", "projectno", "projectid", "projectcode", "wbselement", "wbs", "psp", "network", "analyticaccount", "analyticaccountname", "costcenter", "project_number"],
    "date": ["date", "entrydate", "postingdate", "documentdate", "invoicedate", "accountingdate", "transactiondate", "glDate", "budat", "bldat", "expenditureitemdate"],
    "amount": ["amount", "amountinlocalcurrency", "amountindoccurr", "dmbtr", "wrbtr", "netamount", "debit", "balance", "totalamount", "transactionamount", "enteredamount", "amountuntaxed"],
    "currency": ["currency", "currencykey", "waers", "hwaer", "transactioncurrency", "documentcurrency"],
    "category": ["category", "costelement", "costelementname", "glaccount", "glaccountname", "account", "accountname", "expensecategory", "expendituretype", "kstar", "saknr"],
    "vendor": ["vendor", "vendorname", "supplier", "suppliername", "partner", "partnername", "lifnr", "payee"],
    "reference": ["reference", "documentnumber", "docref", "invoicenumber", "invoiceno", "belnr", "entry", "move", "ref", "number", "purchaseorder", "ebeln", "documentno"],
    "status": ["status", "coststatus", "paymentstate", "paymentstatus"],
}
SOURCES = {"generic": "Any spreadsheet with the columns project, date, amount", "sap": "SAP: WBS element or project, posting date, amount in local currency, cost element, vendor, document number",
           "oracle": "Oracle: project number, expenditure item date, transaction amount, expenditure type, supplier, invoice number",
           "odoo": "Odoo: analytic account, date, amount, account, partner, journal entry"}
_NORM = re.compile(r"[^a-z0-9]")
STATUS = {"committed": "committed", "invoiced": "invoiced", "paid": "paid", "posted": "invoiced", "open": "invoiced", "not_paid": "invoiced", "in_payment": "paid"}


def _norm(h) -> str:
    return _NORM.sub("", str(h or "").lower())


@router.get("/import/costs/sources")
def sources(user: User = Depends(require_roles("ADMIN", "PMO"))):
    return {"sources": SOURCES, "fields": {k: v[:4] for k, v in ALIASES.items()}}


@router.post("/import/costs")
def import_costs(body: ImportIn, source: str = "generic", db=Depends(get_db), user: User = Depends(require_roles("ADMIN", "PMO"))):
    """Columns are matched by name, whatever the system. Needed: project, date, amount. Optional: currency (default: the project's), category, vendor, reference, status.
    Rows with a reference already in the ledger for that project and amount are skipped as duplicates, so the same export can be loaded again safely."""
    if source not in SOURCES:
        raise HTTPException(422, f"source must be one of {', '.join(SOURCES)}")
    try:
        data = base64.b64decode(body.content_b64, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "The file could not be read")
    if len(data) > MAX_FILE:
        raise HTTPException(413, "The file is larger than 10 MB. Split it and import in parts.")
    try:
        head, rows = tabular.read_any(body.filename, data)
    except tabular.TableError as e:
        raise HTTPException(422, str(e))
    pick = {}
    for field, names in ALIASES.items():
        for i, h in enumerate(head):
            if h and _norm(h) in {_norm(n) for n in names} and field not in pick:
                pick[field] = i
    miss = [f for f in ("project", "date", "amount") if f not in pick]
    if miss:
        raise HTTPException(422, f"Could not find a column for: {', '.join(miss)}. Found: {', '.join(h for h in head if h)}")
    get = lambda r, f: (r[pick[f]] if f in pick and pick[f] < len(r) else None)
    projects = {p.number: p for p in db.query(Project)}
    existing = {(c.project_id, round(c.amount, 2), c.doc_ref) for c in db.query(CostEntry.project_id, CostEntry.amount, CostEntry.doc_ref) if c.doc_ref}
    out, seen = [], set()
    for n, r in enumerate(rows, start=2):
        if not any(v not in (None, "") for v in r):
            continue
        pnum, e = _s(get(r, "project")), None
        p = projects.get(pnum)
        if p is None:
            # SAP WBS elements look like "PRJ-001-02": accept the project number as a prefix
            p = next((q for k, q in projects.items() if pnum.startswith(k + "-") or pnum.startswith(k + ".")), None)
        try:
            d = tabular.to_date(get(r, "date"))
        except ValueError as ex:
            d, e = None, str(ex)
        try:
            amt = round(tabular.to_float(get(r, "amount")), 2)
            if not e and amt <= 0:
                e = "amount must be above 0 (credits and reversals are not imported)"
        except (ValueError, TypeError):
            amt, e = 0, "amount must be a number"
        if not e and p is None:
            e = f"unknown project '{pnum}'"
        if not e and p.state not in ("execution", "closing", "approved"):
            e = f"project {p.number} is in '{p.state}': costs can only be loaded once it is approved or running"
        ref = _s(get(r, "reference")) or None
        if e:
            out.append({"line": n, "key": pnum, "status": "error", "message": e})
            continue
        key = (p.id, amt, ref)
        if ref and (key in existing or key in seen):
            out.append({"line": n, "key": pnum, "status": "duplicate", "message": "already in the ledger, skipped"})
            continue
        seen.add(key)
        st = STATUS.get(_norm(get(r, "status")).replace("_", ""), "invoiced") if _s(get(r, "status")) else "invoiced"
        cur = (_s(get(r, "currency")) or p.currency or "SAR").upper()[:3]
        out.append({"line": n, "key": pnum, "status": "ok", "message": f"{d} · {amt:,.2f} {cur}",
                    "_obj": (p.id, (_s(get(r, "category")) or "Imported")[:60], (_s(get(r, "vendor")) or None), amt, cur, d, ref, st)})

    def save(objs):
        for o in objs:
            db.add(CostEntry(project_id=o[0], category=o[1], vendor=o[2][:200] if o[2] else None, amount=o[3], currency=o[4], entry_date=o[5], doc_ref=o[6][:200] if o[6] else None,
                             cost_status=o[7], approval="approved", created_by=user.id, approved_by=user.id))
        log(db, user.id, "import.costs", "cost", None, {"count": len(objs), "file": body.filename[:100], "source": source})
        db.commit()
        return len(objs)
    res = _verdict(out, body, save)
    res["source"] = source
    res["matched_columns"] = {f: head[i] for f, i in pick.items()}
    return res
