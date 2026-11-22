import { t } from "./i18n.js";

/** Hyperscript element builder. Text is always inserted as text nodes, never as HTML. */
export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false || k === "value") continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  if (attrs && attrs.value != null) el.value = attrs.value;   // after options exist, for <select>
  return el;
}

export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const mount = (root, ...nodes) => { clear(root).append(...nodes.flat(Infinity).filter(Boolean)); return root; };

export function toast(msg, type = "ok") {
  const el = h("div", { class: `toast ${type === "error" ? "error" : ""}` }, msg);
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), type === "error" ? 6000 : 3000);
}

export function errorBox(e) {
  const lines = e && e.lines ? e.lines() : [String(e && e.message || e)];
  return h("div", { class: "err", role: "alert" }, lines.length === 1 ? lines[0] : h("ul", {}, lines.map(l => h("li", {}, l))));
}

export function warnBox(lines) {
  return h("div", { class: "warn" }, h("ul", {}, lines.map(l => h("li", {}, l))));
}

export function modal({ title, body, actions }) {
  const close = () => overlay.remove();
  const overlay = h("div", { class: "overlay", onClick: (e) => { if (e.target === overlay) close(); } },
    h("div", { class: "modal", role: "dialog", "aria-modal": "true" },
      h("h2", {}, title), body,
      h("div", { class: "actions" }, (actions || []).map(a =>
        h("button", { class: `btn ${a.class || ""}`, type: "button", onClick: () => a.onClick(close) }, a.label)))));
  document.body.append(overlay);
  const first = overlay.querySelector("input,textarea,select,button");
  if (first) first.focus();
  return close;
}

/** Ask for free text. Resolves to the trimmed text, or null if cancelled. */
export function askText(title, label, { required = true } = {}) {
  return new Promise((resolve) => {
    const ta = h("textarea", { "aria-label": label });
    const msg = h("div");
    modal({
      title, body: h("div", {}, h("label", {}, label, ta), msg),
      actions: [
        { label: t("cancel"), class: "secondary", onClick: (c) => { c(); resolve(null); } },
        { label: t("submit"), onClick: (c) => {
            const v = ta.value.trim();
            if (required && !v) { mount(msg, h("div", { class: "err" }, label)); return; }
            c(); resolve(v);
        } },
      ],
    });
  });
}

export const badge = (text, cls) => h("span", { class: `badge ${cls ?? text}` }, text);
export const field = (label, input) => h("label", {}, label, input);
export const num = (v, d = 1) => (v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));

export function table(headers, rows, empty) {
  if (!rows.length && empty) return h("p", { class: "muted" }, empty);
  return h("table", {}, h("thead", {}, h("tr", {}, headers.map(x => h("th", {}, x)))),
    h("tbody", {}, rows.map(r => h("tr", {}, r.map(c => h("td", {}, c))))));
}

export function stat(label, value) { return h("div", { class: "stat" }, h("div", { class: "v" }, value), h("div", { class: "l" }, label)); }

export function bar(pct, over = false) { return h("div", { class: `bar ${over ? "over" : ""}` }, h("span", { style: `width:${Math.max(0, Math.min(100, pct || 0))}%` })); }

export const pad = (n) => String(n).padStart(2, "0");
export const fmtDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const today = () => fmtDate(new Date());
export function weekStart(d) { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() - x.getDay()); return x; }  // Sunday
export const addDays = (d, n) => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() + n); return x; };
export const parseDate = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };

/** Wrap an async handler: disable the button while running, toast errors. */
export function guarded(btnOrNull, fn) {
  return async (ev) => {
    const b = btnOrNull || ev?.currentTarget;
    if (b) b.disabled = true;
    try { await fn(ev); } catch (e) { toast(e.lines ? e.lines().join(" · ") : t("error"), "error"); }
    finally { if (b) b.disabled = false; }
  };
}
