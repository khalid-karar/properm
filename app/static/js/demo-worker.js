// Runs the real PROPERM backend (Python, via Pyodide) inside the browser. Demo only: data lives in memory
// and resets when the page reloads.
const base = new URL("../", self.location.href).href;
importScripts(base + "pyodide/pyodide.js");

const ready = (async () => {
  const py = await loadPyodide({ indexURL: base + "pyodide/" });
  await py.loadPackage(["sqlalchemy", "pydantic", "anyio", "bcrypt"]);
  const zip = await (await fetch(base + "demo/pyapp.zip", { cache: "no-cache" })).arrayBuffer();
  py.unpackArchive(new Uint8Array(zip), "zip", { extractDir: "/pyapp" });
  py.runPython("import sys; sys.path.insert(0, '/pyapp')\nimport app.embedded as emb\nemb.boot()");
  return py.runPython("emb.handle");
})();

self.onmessage = async (e) => {
  const { id, method, path, headers, body } = e.data;
  try {
    const handle = await ready;
    const r = JSON.parse(handle(method, path, JSON.stringify(headers || {}), body || ""));
    self.postMessage({ id, status: r.status, text: r.body });
  } catch (err) {
    self.postMessage({ id, status: 500, text: JSON.stringify({ detail: String(err && err.message || err) }) });
  }
};
