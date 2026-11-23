"""Read a table from CSV, .xlsx (standard library only, so it runs in the browser build too) or an MS Project XML file.
Returns (header, rows): header names are lower-cased with spaces turned into underscores; rows are lists of cell values."""
import csv
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET

MAX_ROWS = 200_000
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


class TableError(ValueError):
    pass


def norm(h) -> str:
    return re.sub(r"[^\w]+", "_", str(h or "").strip().lower()).strip("_")


def _colnum(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_csv(data: bytes):
    text = data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not rows:
        raise TableError("The file is empty")
    return [norm(h) for h in rows[0]], rows[1:MAX_ROWS + 1]


def read_xlsx(data: bytes):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise TableError("Not a valid .xlsx file")
    if sum(i.file_size for i in z.infolist()) > 300 * 1024 * 1024:
        raise TableError("The workbook is too large")
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    first = wb.find("m:sheets/m:sheet", NS)
    if first is None:
        raise TableError("The workbook has no sheets")
    target = rels.get(first.get("{%s}id" % NS["r"]), "worksheets/sheet1.xml").lstrip("/")
    path = target if target.startswith("xl/") else "xl/" + target
    styles_date = set()
    if "xl/styles.xml" in z.namelist():                       # cells whose number format is a date
        st = ET.fromstring(z.read("xl/styles.xml"))
        custom = {int(n.get("numFmtId")): n.get("formatCode", "") for n in st.iter("{%s}numFmt" % NS["m"])}
        for i, xf in enumerate(st.findall("m:cellXfs/m:xf", NS)):
            fid = int(xf.get("numFmtId", 0))
            if 14 <= fid <= 22 or fid in (45, 46, 47) or re.search(r"[dy]", re.sub(r'"[^"]*"|\[[^\]]*\]', "", custom.get(fid, "")).lower()):
                styles_date.add(i)
    out = []
    for row in ET.fromstring(z.read(path)).iter("{%s}row" % NS["m"]):
        vals = {}
        for c in row.findall("m:c", NS):
            t, v = c.get("t"), c.find("m:v", NS)
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            elif v is None or v.text is None:
                continue
            elif t == "s":
                val = shared[int(v.text)]
            elif t in ("str", "e"):
                val = v.text
            elif t == "b":
                val = v.text == "1"
            else:
                num = float(v.text)
                if int(c.get("s", 0)) in styles_date:
                    val = (datetime(1899, 12, 30) + timedelta(days=num)).date()
                else:
                    val = int(num) if num == int(num) else num
            vals[_colnum(c.get("r"))] = val
        if vals:
            out.append([vals.get(i) for i in range(max(vals) + 1)])
        if len(out) > MAX_ROWS:
            break
    if not out:
        raise TableError("The sheet is empty")
    return [norm(h) for h in out[0]], out[1:]


def read_msproject(data: bytes):
    """MS Project XML (MSPDI): leaf tasks become rows code, name, planned_hours, planned_start, planned_end."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise TableError("Not a valid MS Project XML file")
    ns = {"p": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    q = (lambda t: f"p:{t}") if ns else (lambda t: t)
    tasks = root.findall(f".//{q('Task')}", ns) if ns else root.findall(".//Task")
    parents = {t.findtext(q("OutlineNumber"), "", ns).rsplit(".", 1)[0] for t in tasks if "." in t.findtext(q("OutlineNumber"), "", ns)}
    rows = []
    for t in tasks:
        outline, name = t.findtext(q("OutlineNumber"), "", ns), (t.findtext(q("Name"), "", ns) or "").strip()
        if not name or t.findtext(q("Summary"), "0", ns) == "1" or outline in parents or t.findtext(q("UID"), "0", ns) == "0":
            continue
        dur = t.findtext(q("Work"), "", ns) or t.findtext(q("Duration"), "", ns)
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", dur or "")
        hours = round(int(m.group(1) or 0) + int(m.group(2) or 0) / 60, 1) if m else 0
        s, f = (t.findtext(q("Start"), "", ns) or "")[:10], (t.findtext(q("Finish"), "", ns) or "")[:10]
        rows.append([t.findtext(q("WBS"), "", ns) or outline or t.findtext(q("ID"), "", ns), name, hours, s, f])
    if not rows:
        raise TableError("No tasks found in the project file")
    return ["code", "name", "planned_hours", "planned_start", "planned_end"], rows


def read_any(filename: str, data: bytes):
    n = (filename or "").lower()
    if n.endswith(".xlsx"):
        return read_xlsx(data)
    if n.endswith(".xml"):
        return read_msproject(data)
    if n.endswith((".csv", ".txt", ".tsv")):
        return read_csv(data)
    raise TableError("Use a .xlsx, .csv or MS Project .xml file")


def to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"cannot read the date '{s}'")


def to_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).strip().replace(",", ""))
