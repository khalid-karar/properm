// Landing page sections (kept apart from the sign-in logic in login.js). All text comes from i18n (lp_*); nothing here is real customer data.
import { t } from "../i18n.js";
import { h, icon } from "../ui.js";

const sec = (cls, id, ...kids) => h("section", { class: `lp-sec ${cls}`.trim(), id, "data-reveal": "" }, ...kids);
const head = (title, lead) => h("div", { class: "lp-head" }, h("h2", { class: "lp-h" }, t(title)), lead ? h("p", { class: "lp-sub" }, t(lead)) : null);

// A browser-framed preview of the dashboard, drawn with HTML so it stays sharp, works in both directions and ships no image.
export function preview() {
  const tile = (cls, v, k) => h("div", { class: `pv-tile ${cls}` }, h("b", {}, v), h("span", {}, t(k)));
  const bars = [62, 78, 55, 90, 70, 84, 48].map((n, i) => h("i", { style: `height:${n}%`, class: i === 3 ? "hi" : "" }));
  const alert = (cls, k) => h("li", {}, h("span", { class: `pv-dot ${cls}` }), h("span", {}, t(k)));
  return sec("lp-preview", "lp-preview",
    head("lp_pv_title", "lp_pv_lead"),
    h("div", { class: "pv-frame", role: "img", "aria-label": t("lp_pv_alt") },
      h("div", { class: "pv-bar" }, h("i"), h("i"), h("i"), h("span", {}, "properm / dashboard")),
      h("div", { class: "pv-body" },
        h("div", { class: "pv-side" }, ["dashboard", "projects", "timesheet", "approvals", "alerts", "reports"].map((n, i) => h("span", { class: i === 0 ? "on" : "" }, icon(n)))),
        h("div", { class: "pv-main" },
          h("div", { class: "pv-tiles" }, tile("g", "12", "lp_pv_ok"), tile("a", "3", "lp_pv_risk"), tile("r", "2", "lp_pv_over"), tile("", "68%", "lp_pv_budget")),
          h("div", { class: "pv-cols" },
            h("div", { class: "pv-card" }, h("h4", {}, t("lp_pv_chart")), h("div", { class: "pv-bars" }, bars)),
            h("div", { class: "pv-card" }, h("h4", {}, t("lp_pv_alerts")), h("ul", { class: "pv-alerts" }, alert("r", "lp_pv_a1"), alert("a", "lp_pv_a2"), alert("g", "lp_pv_a3"))))))),
    h("p", { class: "lp-note" }, t("lp_pv_note")));
}

export function proof() {
  const items = [["globe", "lp_pr1"], ["shield", "lp_pr2"], ["approvals", "lp_pr3"], ["spark", "lp_pr4"]];
  return h("section", { class: "lp-proof", "aria-label": t("lp_trust") }, items.map(([ic, k]) => h("div", {}, icon(ic), h("span", {}, t(k)))));
}

export function problem() {
  const col = (cls, title, keys) => h("div", { class: `lp-vs ${cls}` }, h("h3", {}, t(title)), h("ul", {}, keys.map(k => h("li", {}, h("span", { class: "lp-mark", "aria-hidden": "true" }, cls === "bad" ? "✕" : "✓"), t(k)))));
  return sec("alt", "lp-why", head("lp_why_title", "lp_why_lead"),
    h("div", { class: "lp-vs-grid" }, col("bad", "lp_before", ["lp_b1", "lp_b2", "lp_b3", "lp_b4"]), col("good", "lp_after", ["lp_w1", "lp_w2", "lp_w3", "lp_w4"])));
}

export function features() {
  const F = [["timesheet", "f1"], ["chart", "f2"], ["alerts", "f3"], ["approvals", "f4"], ["spark", "f5"], ["shield", "f6"]];
  return sec("", "lp-features", head("lp_feat_title", "lp_feat_lead"),
    h("div", { class: "lp-grid" }, F.map(([ic, k]) => h("div", { class: "lp-feat" }, h("span", { class: "lp-ic" }, icon(ic)), h("h3", {}, t(`lp_${k}_t`)), h("p", {}, t(`lp_${k}_d`))))));
}

// Tabs by role: visitors see their own job in the product. Arrow keys move between tabs.
export function roles() {
  const R = ["staff", "pm", "pmo", "exec", "admin"];
  const panel = h("div", { class: "lp-panel", role: "tabpanel", "aria-live": "polite" });
  const tabs = h("div", { class: "lp-tabs", role: "tablist", "aria-label": t("lp_roles_title") });
  const show = (r, focus) => {
    [...tabs.children].forEach(b => { const on = b.dataset.r === r; b.setAttribute("aria-selected", on); b.tabIndex = on ? 0 : -1; if (on && focus) b.focus(); });
    panel.replaceChildren(h("h3", {}, t(`lp_role_${r}_t`)), h("p", {}, t(`lp_role_${r}_d`)), h("ul", {}, t(`lp_role_${r}_b`).split("|").map(x => h("li", {}, h("span", { class: "lp-mark", "aria-hidden": "true" }, "✓"), x))));
  };
  R.forEach(r => tabs.append(h("button", { type: "button", role: "tab", class: "lp-tab", "data-r": r, onClick: () => show(r) }, t(`lp_role_${r}`))));
  tabs.addEventListener("keydown", (e) => {
    const i = R.indexOf(document.activeElement?.dataset?.r); if (i < 0) return;
    const rtl = document.documentElement.dir === "rtl", step = { ArrowRight: rtl ? -1 : 1, ArrowLeft: rtl ? 1 : -1 }[e.key];
    if (step) { e.preventDefault(); show(R[(i + step + R.length) % R.length], true); }
  });
  show("pmo");
  return sec("alt", "lp-roles", head("lp_roles_title", "lp_roles_lead"), tabs, panel);
}

export function how() {
  return sec("", "lp-how", head("lp_how_title"), h("ol", { class: "lp-steps" }, ["s1", "s2", "s3"].map((k, i) => h("li", {}, h("span", { class: "lp-num" }, String(i + 1)), h("h3", {}, t(`lp_${k}_t`)), h("p", {}, t(`lp_${k}_d`))))));
}

export function security() {
  const S = ["sec1", "sec2", "sec3", "sec4", "sec5", "sec6"];
  return h("section", { class: "lp-sec dark", id: "lp-security", "data-reveal": "" }, h("div", { class: "lp-inner" },
    h("h2", { class: "lp-h" }, t("lp_sec_title")), h("p", { class: "lp-sub" }, t("lp_sec_lead")),
    h("ul", { class: "lp-sec-list" }, S.map(k => h("li", {}, icon("shield"), h("div", {}, h("b", {}, t(`lp_${k}_t`)), h("span", {}, t(`lp_${k}_d`))))))));
}

export function faq() {
  return sec("", "lp-faq", head("lp_faq_title"), h("div", { class: "lp-faq" }, [1, 2, 3, 4, 5, 6].map(n => h("details", {}, h("summary", {}, t(`lp_q${n}`)), h("p", {}, t(`lp_a${n}`))))));
}

// Fade-in on scroll; skipped when the visitor prefers reduced motion or the browser has no IntersectionObserver.
export function reveal(root) {
  const els = root.querySelectorAll("[data-reveal]");
  if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion:reduce)").matches) return;
  const io = new IntersectionObserver((es) => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.08 });
  els.forEach(el => { el.classList.add("pre"); io.observe(el); });
}
