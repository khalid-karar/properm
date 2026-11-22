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

export async function api(method, path, body) {
  const s = session.get();
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", ...(s ? { Authorization: `Bearer ${s.token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
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
