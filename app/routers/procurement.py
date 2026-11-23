"""Procurement: contract register, payment milestones through to invoice and payment, vendor performance reviews."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from ..deps import current_user, get_db, require_roles
from ..models import Contract, ContractPayment, CostEntry, Project, User, VendorReview
from ..regkit import project_register
from .projects import can_manage, can_view_cost, get_project

router = APIRouter(tags=["procurement"])


def _reader(db, user, p):
    return can_view_cost(db, user, p)


def _contract_validate(db, p, data, row):
    if data.get("number"):
        q = db.query(Contract).filter_by(project_id=p.id, number=data["number"]).first()
        if q and (row is None or q.id != row.id):
            raise HTTPException(409, "Contract number already used in this project")
    s, e = data.get("start_date") or (row and row.start_date), data.get("end_date") or (row and row.end_date)
    if s and e and e < s:
        raise HTTPException(422, "Contract end is before its start")
    if data.get("value") is not None and data["value"] < 0:
        raise HTTPException(422, "Value cannot be negative")
    status = data.get("status") or (row.status if row else "draft")
    value = data["value"] if "value" in data else (row.value if row else None)
    if status in ("active", "completed") and not value:
        raise HTTPException(422, "An active contract needs a value")
    if row and value is not None:
        sched = sum(x.amount for x in db.query(ContractPayment).filter_by(contract_id=row.id))
        if sched > value + 0.01:
            raise HTTPException(409, f"Payment milestones ({sched:,.0f}) already exceed that value")
    if status == "completed" and row:
        if db.query(ContractPayment).filter(ContractPayment.contract_id == row.id, ContractPayment.status != "paid").first():
            raise HTTPException(409, "Not every payment milestone is paid yet")
    if data.get("owner_id") and not db.get(User, data["owner_id"]):
        raise HTTPException(422, "Unknown user")


def _contract_enrich(db, p, rows, ds):
    today = date.today()
    cost = {}
    for x in db.query(CostEntry).filter_by(project_id=p.id):
        if x.vendor and x.approval == "approved":
            cost[x.vendor.strip().lower()] = cost.get(x.vendor.strip().lower(), 0) + x.amount
    names = {u.id: u.full_name for u in db.query(User)}
    for r, d in zip(rows, ds):
        pays = db.query(ContractPayment).filter_by(contract_id=r.id).all()
        rev = db.query(VendorReview).filter_by(contract_id=r.id).all()
        inv = sum(x.amount for x in pays if x.status in ("invoiced", "paid"))
        d.update({"owner": names.get(r.owner_id), "scheduled": sum(x.amount for x in pays), "invoiced": inv, "paid": sum(x.amount for x in pays if x.status == "paid"),
                  "remaining": (r.value or 0) - inv, "pct_invoiced": round(100 * inv / r.value) if r.value else None,
                  "unscheduled": (r.value or 0) - sum(x.amount for x in pays),
                  "overdue_payments": sum(1 for x in pays if x.due_date and x.due_date < today and x.status in ("planned", "achieved")),
                  "ledger_cost": cost.get((r.vendor or "").strip().lower(), 0),
                  "expires_in": (r.end_date - today).days if r.end_date and r.status == "active" else None,
                  "rating": round(sum((v.quality + v.schedule + v.communication) / 3 for v in rev) / len(rev), 1) if rev else None, "reviews": len(rev)})


def _contract_delete(db, p, row):
    if db.query(ContractPayment).filter(ContractPayment.contract_id == row.id, ContractPayment.status.in_(("invoiced", "paid"))).first():
        raise HTTPException(409, "This contract has invoiced or paid milestones. Terminate it instead of deleting it")
    db.query(ContractPayment).filter_by(contract_id=row.id).delete()
    db.query(VendorReview).filter_by(contract_id=row.id).delete()


C = project_register(router, "contracts", Contract,
                     {"number": str, "title": str, "vendor": str, "value": float, "currency": str, "start_date": date, "end_date": date, "status": str, "owner_id": int, "note": str},
                     choices={"status": ("draft", "active", "completed", "terminated")}, required=("number", "title", "vendor"),
                     defaults={"status": "draft", "currency": "SAR"}, validate=_contract_validate, enrich=_contract_enrich, reader=_reader, on_delete=_contract_delete, order=[Contract.number])


def _own_contract(db, p, cid):
    c = db.get(Contract, cid or 0)
    if not c or c.project_id != p.id:
        raise HTTPException(422, "Contract not found in this project")
    return c


def _pay_validate(db, p, data, row):
    c = _own_contract(db, p, data.get("contract_id") or (row and row.contract_id))
    if row is None and c.status in ("completed", "terminated"):
        raise HTTPException(409, f"The contract is {c.status}")
    if "contract_id" in data and row and data["contract_id"] != row.contract_id:
        raise HTTPException(422, "A payment cannot move to another contract")
    amt = data.get("amount", row.amount if row else 0)
    if amt is None or amt <= 0:
        raise HTTPException(422, "Amount must be positive")
    others = sum(x.amount for x in db.query(ContractPayment).filter_by(contract_id=c.id) if not row or x.id != row.id)
    if c.value is not None and others + amt > c.value + 0.01:
        raise HTTPException(409, f"Milestones would total {others + amt:,.0f}, above the contract value {c.value:,.0f}")
    status = data.get("status") or (row.status if row else "planned")
    inv = data["invoice_no"] if "invoice_no" in data else (row.invoice_no if row else None)
    if status in ("invoiced", "paid"):
        if not (inv or "").strip():
            raise HTTPException(422, "Enter the invoice number")
        if "invoiced_on" not in data and not (row and row.invoiced_on):
            data["invoiced_on"] = date.today()
    if status == "paid" and "paid_on" not in data and not (row and row.paid_on):
        data["paid_on"] = date.today()
    if status in ("planned", "achieved"):
        data["paid_on"] = None
        data["invoiced_on"] = None
    if status == "paid" and row and row.status in ("planned", "achieved") and "status" in data:
        raise HTTPException(409, "Mark the milestone invoiced before paid")
    if status == "invoiced" and row and row.status == "paid":
        data["paid_on"] = None


def _pay_enrich(db, p, rows, ds):
    cn = {c.id: f"{c.number} · {c.vendor}" for c in db.query(Contract).filter_by(project_id=p.id)}
    today = date.today()
    for r, d in zip(rows, ds):
        d["contract"] = cn.get(r.contract_id)
        d["overdue"] = bool(r.due_date and r.due_date < today and r.status in ("planned", "achieved"))


P = project_register(router, "payments", ContractPayment,
                     {"contract_id": int, "name": str, "amount": float, "due_date": date, "status": str, "invoice_no": str, "invoiced_on": date, "paid_on": date},
                     choices={"status": ("planned", "achieved", "invoiced", "paid")}, required=("contract_id", "name", "amount"),
                     defaults={"status": "planned"}, validate=_pay_validate, enrich=_pay_enrich, reader=_reader, order=[ContractPayment.due_date, ContractPayment.id])


def _rev_validate(db, p, data, row):
    _own_contract(db, p, data.get("contract_id") or (row and row.contract_id))
    for k in ("quality", "schedule", "communication"):
        if k in data and not (1 <= (data[k] or 0) <= 5):
            raise HTTPException(422, f"{k} must be between 1 and 5")


def _rev_enrich(db, p, rows, ds):
    cn = {c.id: f"{c.number} · {c.vendor}" for c in db.query(Contract).filter_by(project_id=p.id)}
    for d in ds:
        d["contract"] = cn.get(d["contract_id"])
        d["average"] = round((d["quality"] + d["schedule"] + d["communication"]) / 3, 1)


project_register(router, "vendor-reviews", VendorReview,
                 {"contract_id": int, "review_date": date, "quality": int, "schedule": int, "communication": int, "note": str},
                 required=("contract_id", "review_date", "quality", "schedule", "communication"), validate=_rev_validate, enrich=_rev_enrich,
                 reader=_reader, order=[VendorReview.review_date.desc()])


@router.get("/procurement/overview")
def overview(db=Depends(get_db), user: User = Depends(require_roles("PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"))):
    today = date.today()
    prj = {p.id: p for p in db.query(Project)}
    out, vendors = [], {}
    for c in db.query(Contract).filter(Contract.status.in_(("active", "draft"))):
        p = prj.get(c.project_id)
        pays = db.query(ContractPayment).filter_by(contract_id=c.id).all()
        inv = sum(x.amount for x in pays if x.status in ("invoiced", "paid"))
        od = sum(1 for x in pays if x.due_date and x.due_date < today and x.status in ("planned", "achieved"))
        out.append({"id": c.id, "project_id": c.project_id, "project": p.number if p else "", "number": c.number, "title": c.title, "vendor": c.vendor, "status": c.status,
                    "value": c.value or 0, "currency": c.currency, "invoiced": inv, "end_date": c.end_date.isoformat() if c.end_date else None,
                    "expires_in": (c.end_date - today).days if c.end_date else None, "overdue_payments": od})
    for r in db.query(VendorReview):
        c = db.get(Contract, r.contract_id)
        if c:
            v = vendors.setdefault(c.vendor, {"vendor": c.vendor, "reviews": 0, "sum": 0.0})
            v["reviews"] += 1
            v["sum"] += (r.quality + r.schedule + r.communication) / 3
    return {"contracts": sorted(out, key=lambda x: (x["expires_in"] is None, x["expires_in"] or 0)),
            "expiring_soon": [x for x in out if x["status"] == "active" and x["expires_in"] is not None and x["expires_in"] <= 60],
            "vendors": sorted(({"vendor": v["vendor"], "reviews": v["reviews"], "rating": round(v["sum"] / v["reviews"], 1)} for v in vendors.values()), key=lambda x: x["rating"]),
            "total_value": sum(x["value"] for x in out), "total_invoiced": sum(x["invoiced"] for x in out)}
