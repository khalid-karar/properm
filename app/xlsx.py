"""Minimal .xlsx writer (standard library only, so it also runs in the browser build). Text, numbers, bold header, column widths."""
import io
import zipfile
from datetime import date, datetime
from xml.sax.saxutils import escape

_ILLEGAL = {c: None for c in list(range(0, 9)) + [11, 12] + list(range(14, 32))}


def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref: str, v, style: int = 0) -> str:
    st = f' s="{style}"' if style else ""
    if v is None or v == "":
        return f'<c r="{ref}"{st}/>'
    if isinstance(v, bool):
        v = "Yes" if v else "No"
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{st}><v>{v}</v></c>'
    if isinstance(v, (date, datetime)):
        v = v.isoformat()
    t = escape(str(v).translate(_ILLEGAL))
    if str(v)[:1] in "=+-@" and not isinstance(v, (int, float)):
        t = "'" + t                                   # keep spreadsheet formulas out of exported text
    return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{t}</t></is></c>'


def _sheet(header: list, rows: list) -> str:
    widths = [max([len(str(header[i]))] + [len(str(r[i])) if i < len(r) and r[i] is not None else 0 for r in rows[:200]]) for i in range(len(header))]
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{min(60, max(10, w + 2))}" customWidth="1"/>' for i, w in enumerate(widths))
    body = ['<row r="1">' + "".join(_cell(f"{_col(i)}1", h, 1) for i, h in enumerate(header)) + "</row>"]
    for n, r in enumerate(rows, start=2):
        body.append(f'<row r="{n}">' + "".join(_cell(f"{_col(i)}{n}", v) for i, v in enumerate(r)) + "</row>")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{cols}</cols><sheetData>{"".join(body)}</sheetData></worksheet>')


def build_xlsx(sheets: list[tuple[str, list, list]]) -> bytes:
    """sheets: [(name, header, rows)] -> bytes of an .xlsx workbook."""
    names = []
    for n, _, _ in sheets:
        base = "".join(c for c in n if c not in '[]:*?/\\')[:31] or "Sheet"
        nm, i = base, 2
        while nm in names:
            nm, i = f"{base[:28]}_{i}", i + 1
        names.append(nm)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(sheets))) + "</Types>")
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
                   '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0B1F3A"/></patternFill></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i, (_, header, rows) in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet(header, rows))
    return buf.getvalue()
