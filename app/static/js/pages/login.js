import { api, session } from "../api.js";
import { getLang, setLang, t } from "../i18n.js";
import { bar, errorBox, field, guarded, h, icon, mount } from "../ui.js";
import { resetMe } from "../app.js";

export default function (root) {
  const msg = h("div");
  const id = h("input", { name: "staff_id", autocomplete: "username", required: true });
  const pw = h("input", { name: "password", type: "password", autocomplete: "current-password", required: true });
  const otp = h("input", { name: "otp", inputmode: "numeric", autocomplete: "one-time-code", id: "login-otp" });
  const otpRow = h("div", { hidden: true }, field(t("twofa_code"), otp), h("p", { class: "muted small" }, t("twofa_login_note")));
  const btn = h("button", { class: "btn", type: "submit", style: "width:100%" }, t("login"));
  const form = h("form", { class: "card", onSubmit: guarded(btn, async (ev) => {
      ev.preventDefault();
      mount(msg);
      try {
        const r = await api("POST", "/auth/login", { staff_id: id.value.trim(), password: pw.value, otp: otp.value.trim() || undefined });
        session.set(r.access_token, r.role);
        resetMe();
        location.hash = "#/";
      } catch (e) {
        if (e.message === "otp_required") { otpRow.hidden = false; otp.focus(); return; }
        mount(msg, errorBox(e));
      }
  }) },
    h("h2", { class: "t" }, t("login")),
    field(t("staff_id"), id), field(t("password"), pw), otpRow, msg, btn);
  const quick = h("div", { class: "card", hidden: true });
  const sso = h("div", { class: "card", hidden: true, id: "sso-box" });
  const ssoErr = (location.hash.split("sso_error=")[1] || "").split("&")[0];
  api("GET", "/auth/sso/config").then(c => {
    if (!c.enabled) return;
    mount(sso, ssoErr ? h("p", { class: "warn", role: "alert" }, t("sso_err_" + (["no_account", "expired", "provider_refused", "bad_token", "unverified_email"].includes(ssoErr) ? ssoErr : "failed"))) : null,
      h("a", { class: "btn", id: "sso-btn", href: `${(window.PROPERM_API || "")}/auth/sso/login`, style: "display:block;text-align:center" }, c.label || t("sso_btn")),
      c.sso_only ? h("p", { class: "muted small" }, t("sso_only_note")) : null);
    sso.hidden = false;
  }).catch(() => {});
  const starting = window.PROPERM_EMBEDDED ? h("div", { class: "card" }, h("p", { class: "muted" }, t("demo_starting"))) : null;
  const board = h("div", { class: "card timeline" });
  const hero = h("section", { class: "hero" },
    h("div", { class: "brand" }, h("span", { class: "logo" }, "P"), t("app")),
    h("div", {}, h("h1", {}, t("hero_title")), h("p", { class: "lead" }, t("hero_lead"))),
    h("ul", { class: "points" }, [["timesheet", "hero_p1"], ["chart", "hero_p2"], ["shield", "hero_p3"], ["spark", "hero_p4"]].map(([ic, k]) => h("li", {}, icon(ic), h("span", {}, t(k))))),
    h("div", { class: "foot" }, "Smart PMO · Riyadh"));
  const side = h("section", { class: "login-side" }, sso, form, starting, quick,
    h("button", { class: "btn secondary", type: "button", onClick: () => { setLang(getLang() === "en" ? "ar" : "en"); location.reload(); } }, getLang() === "en" ? "العربية" : "English"));
  mount(root, h("div", { class: "login-page" }, hero, side, h("div", { class: "timeline-wrap" }, board)));
  timeline(board);
  id.focus();
  // Demo quick login: the server only answers when PROPERM_DEMO_LOGIN=1, otherwise this stays hidden.
  api("GET", "/auth/demo-users").then((users) => {
    if (starting) starting.hidden = true;
    if (!users.length) return;
    mount(quick, h("h2", {}, t("quick_login")), h("p", { class: "muted small" }, t("quick_login_note")),
      h("div", { class: "chips" }, users.map(u => h("button", { class: "btn secondary", type: "button", onClick: guarded(null, async () => {
        const r = await api("POST", "/auth/demo-login", { staff_id: u.staff_id });
        session.set(r.access_token, r.role); resetMe(); location.hash = "#/";
      }) }, u.full_name, h("small", {}, u.role)))));
    quick.hidden = false;
  }).catch(() => {});
}

// Build progress: edit app/data/milestones.json as work moves (done / progress / todo). Private: the server sends it only for the owner password (PROPERM_BUILD_PASSWORD).
const STATE = { done: ["✓", "done"], progress: ["…", "progress"], todo: ["○", "todo"] };
async function timeline(board) {
  let on = false;
  try { on = (await api("GET", "/build-progress/enabled")).enabled; } catch { /* no API (demo) */ }
  if (!on) { board.hidden = true; return; }
  const pw = h("input", { type: "password", autocomplete: "off", id: "ms-password", placeholder: t("password") });
  const msg = h("div");
  const open = h("button", { class: "btn", type: "button", id: "ms-open" }, t("ms_show"));
  const unlock = guarded(open, async () => {
    mount(msg);
    try { render(board, await api("POST", "/build-progress", { password: pw.value })); }
    catch (e) { mount(msg, errorBox(e)); }
  });
  open.addEventListener("click", unlock);
  pw.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); unlock(); } });
  mount(board, h("h2", {}, t("ms_title")), h("p", { class: "muted small" }, t("ms_private")), h("div", { class: "row" }, pw, open), msg);
}

function render(board, data) {
  const ar = getLang() === "ar";
  const name = (x) => (ar && x.ar) || x.en;
  const light = (s) => h("span", { class: `light ${STATE[s][1]}`, role: "img", "aria-label": t(`ms_${s}`), title: t(`ms_${s}`) }, STATE[s][0]);
  const all = data.milestones.flatMap(m => m.subs);
  const done = all.filter(s => s.s === "done").length;
  const pct = Math.round((done / all.length) * 100);
  const status = (m) => (m.subs.every(s => s.s === "done") ? "done" : m.subs.some(s => s.s !== "todo") ? "progress" : "todo");
  mount(board,
    h("h2", {}, t("ms_title")),
    h("p", { class: "muted small" }, `${t("ms_updated")}: ${data.updated}`),
    h("div", { class: "ms-total" }, h("strong", {}, `${pct}%`), ` · ${done} / ${all.length} ${t("ms_steps")}`, bar(pct)),
    h("div", { class: "legend small" }, ["done", "progress", "todo"].map(s => h("span", {}, light(s), ` ${t(`ms_${s}`)}`))),
    data.milestones.map((m, i) => {
      const st = status(m), d = m.subs.filter(s => s.s === "done").length;
      return h("details", { class: "ms", open: st === "progress" }, h("summary", {}, light(st), h("span", { class: "ms-name" }, `${i + 1}. ${name(m)}`), h("span", { class: "muted small" }, `${d}/${m.subs.length}`)),
        h("ul", {}, m.subs.map(s => h("li", {}, light(s.s), ` ${name(s)}`))));
    }));
}
