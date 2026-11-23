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

/** Fetch a text resource (CSV, HTML) with the session token. */
export async function apiText(path) {
  const s = session.get();
  const res = await send("GET", path, s ? { Authorization: `Bearer ${s.token}` } : {}, undefined);
  const text = await res.text();
  if (!res.ok) { let d = null; try { d = JSON.parse(text); } catch { /* not JSON */ } throw new ApiError(res.status, d); }
  return text;
}

/** Download a CSV (adds the BOM back; fetch strips it) via a temporary link. */
export async function downloadCsv(path, filename) {
  const text = await apiText(path);
  const url = URL.createObjectURL(new Blob(["﻿", text.replace(/^﻿/, "")], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** Open the print-friendly report in a new tab. */
export async function openReport(path) {
  const html = await apiText(path);
  const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

/** Save a project document (fetched as base64 JSON so it works in the browser demo as well). */
export async function saveDocument(path, fallbackName) {
  const d = await api("GET", path);
  const bin = atob(d.content_b64), bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url; a.download = d.filename || fallbackName; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** Read a File as base64 (no data: prefix). */
export const fileToB64 = (file) => new Promise((res, rej) => {
  const r = new FileReader();
  r.onload = () => res(String(r.result).split(",")[1] || "");
  r.onerror = () => rej(new Error("Could not read the file"));
  r.readAsDataURL(file);
});
