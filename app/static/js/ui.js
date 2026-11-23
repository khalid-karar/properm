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

const ICONS = {
  timesheet: "M12 7v5l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  approvals: "M9 12l2 2 4-4M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  projects: "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z",
  load: "M17 20v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M10 10a4 4 0 100-8 4 4 0 000 8zM21 20v-2a4 4 0 00-3-3.9M16 2.1a4 4 0 010 7.8",
  dashboard: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  programs: "M12 2l10 5-10 5L2 7l10-5zM2 12l10 5 10-5M2 17l10 5 10-5",
  alerts: "M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
  admin: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
  config: "M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6",
  reports: "M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6",
  todo: "M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2",
  executive: "M4 20V10M10 20V4M16 20v-8M22 20H2",
  decisions: "M9 11l3 3 8-8M20 12v7a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2h9",
  proposals: "M12 3v18M3 12h18M5 5h14v14H5z",
  lessons: "M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4zM8 9h8M8 13h6",
  leave: "M4 6h16v14H4zM4 10h16M8 3v5M16 3v5",
  portfolio: "M3 7h18v13H3zM8 7V4h8v3M3 12h18",
  strategy: "M12 3a9 9 0 100 18 9 9 0 000-18zm0 4a5 5 0 110 10 5 5 0 010-10zm0 3a2 2 0 100 4 2 2 0 000-4z",
  skills: "M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7L12 3z",
  procurement: "M3 7h18v13H3zM8 7V4h8v3M3 13h18",
  compliance: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3zm-1 11l5-5-1.4-1.4L11 11.2 9.4 9.6 8 11l3 3z",
  templates: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  guide: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5M12 8h.01",
  mine: "M4 7h16M4 12h16M4 17h10",
  audit: "M9 12h6M9 16h6M9 8h3M6 3h9l4 4v14H6z",
  bell: "M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0",
  menu: "M3 6h18M3 12h18M3 18h18",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  spark: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z",
  chart: "M3 3v18h18M7 14l4-4 3 3 5-6",
};
/** Inline SVG icon (stroke icons, no external assets). */
export function icon(name) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "ico"); svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(NS, "path"); p.setAttribute("d", ICONS[name] || ICONS.chart); svg.append(p);
  return svg;
}

export const badge = (text, cls) => h("span", { class: `badge ${cls ?? text}` }, text);
export const field = (label, input) => h("label", {}, label, input);
export const num = (v, d = 1) => (v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));

export function table(headers, rows, empty) {
  if (!rows.length && empty) return h("div", { class: "empty" }, empty);
  return h("div", { class: "table-wrap", tabindex: "0" }, h("table", {}, h("thead", {}, h("tr", {}, headers.map(x => h("th", {}, x)))),
    h("tbody", {}, rows.map(r => h("tr", {}, r.map(c => h("td", {}, c)))))));
}

export function stat(label, value) { return h("div", { class: `stat ${{ RED: "red", AMBER: "amber", GREEN: "green", GREY: "grey" }[label] || ""}` }, h("div", { class: "v" }, value), h("div", { class: "l" }, label)); }

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

/** Give every form control that has no accessible name one (from its wrapping label, placeholder, title or name), so screen readers can announce it. */
export function nameControls(root = document) {
  root.querySelectorAll("select:not([aria-label]):not([aria-labelledby]), input:not([type=hidden]):not([aria-label]):not([aria-labelledby]), textarea:not([aria-label]):not([aria-labelledby])").forEach(el => {
    if (el.id && root.querySelector(`label[for="${el.id}"]`)) return;
    const lab = el.closest("label");
    const own = lab && lab.textContent.trim();
    const prev = el.previousElementSibling && ["SPAN", "LABEL", "DIV"].includes(el.previousElementSibling.tagName) ? el.previousElementSibling.textContent.trim() : "";
    const name = own || prev || el.getAttribute("placeholder") || el.getAttribute("title") || el.getAttribute("name") || (el.tagName === "SELECT" && el.selectedOptions[0]?.textContent.trim()) || "";
    if (name) el.setAttribute("aria-label", name.slice(0, 80));
  });
}
