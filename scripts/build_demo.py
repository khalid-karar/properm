"""Build app/static/demo/pyapp.zip: the app package plus the pure-Python dependencies that Pyodide does not ship.
Standard library only, so it runs on any build image:  python3 scripts/build_demo.py"""
import pathlib
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
out = root / "app" / "static" / "demo" / "pyapp.zip"
out.parent.mkdir(parents=True, exist_ok=True)
FIXED = (2020, 1, 1, 0, 0, 0)

def add(z, name, data):
    z.writestr(zipfile.ZipInfo(name, FIXED), data, zipfile.ZIP_DEFLATED)

with zipfile.ZipFile(out, "w") as z:
    for p in sorted((root / "app").rglob("*.py")):
        rel = p.relative_to(root)
        if "static" in rel.parts or "__pycache__" in rel.parts:
            continue
        add(z, rel.as_posix(), p.read_bytes())
    for wheel in sorted((root / "vendor").glob("*.whl")):
        with zipfile.ZipFile(wheel) as w:
            for n in sorted(w.namelist()):
                if n.endswith("/") or ".dist-info/" in n:
                    continue
                add(z, n, w.read(n))
print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
