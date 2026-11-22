const KEY = "properm_session";

export const session = {
  get() { try { return JSON.parse(sessionStorage.getItem(KEY)) || null; } catch { return null; } },
  set(token, role) { sessionStorage.setItem(KEY, JSON.stringify({ token, role })); },
  clear() { sessionStorage.removeItem(KEY); },
};

export class ApiError extends Error {
  constructor(status, data) {
    super(typeof data?.detail === "string" ? data.detail : `Request failed (${status})`);
    this.status = status;
    this.data = data;
  }
  /** Human-readable list of problems (rule violations, per-field errors, or the message). */
  lines() {
    const d = this.data || {};
    if (Array.isArray(d.violations) && d.violations.length) return d.violations.map(v => `${v.rule}: ${v.message}`);
    if (d.detail && Array.isArray(d.detail.errors)) return d.detail.errors;
    if (Array.isArray(d.detail)) return d.detail.map(x => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`);
    return [this.message];
  }
}

// Transport: real HTTP, or (demo hosting without a server) the Python backend running in a Web Worker.
let worker = null, seq = 0;
const pending = new Map();
function viaWorker(method, path, headers, body) {
  if (!worker) {
    worker = new Worker(new URL("./demo-worker.js", import.meta.url));
    worker.onmessage = (e) => { const p = pending.get(e.data.id); pending.delete(e.data.id); if (p) p(e.data); };
  }
  return new Promise((resolve) => { const id = ++seq; pending.set(id, resolve); worker.postMessage({ id, method, path, headers, body }); });
}
async function send(method, path, headers, body) {
  if (window.PROPERM_EMBEDDED) { const r = await viaWorker(method, path, headers, body); return { status: r.status, ok: r.status < 400, text: async () => r.text }; }
  return fetch((window.PROPERM_API || "") + path, { method, headers, body });
}

export async function api(method, path, body) {
  const s = session.get();
  const res = await send(method, path,
    { "Content-Type": "application/json", ...(s ? { Authorization: `Bearer ${s.token}` } : {}) },
    body === undefined ? undefined : JSON.stringify(body));
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON error body */ }
  if (res.status === 401 && path !== "/auth/login") {
    session.clear();
    location.hash = "#/login";
    throw new ApiError(401, { detail: "Session expired, please sign in again" });
  }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}
