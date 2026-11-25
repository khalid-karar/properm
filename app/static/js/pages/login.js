import { api, session } from "../api.js";
import { getLang, setLang, t } from "../i18n.js";
import { bar, errorBox, field, guarded, h, icon, mount } from "../ui.js";
import { resetMe } from "../app.js";
import * as S from "./landing-sections.js";

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
  const go = (id) => document.getElementById(id)?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion:reduce)").matches ? "auto" : "smooth", block: "start" });
  const langBtn = h("button", { class: "lp-lang", type: "button", onClick: () => { setLang(getLang() === "en" ? "ar" : "en"); location.reload(); } }, getLang() === "en" ? "العربية" : "English");

  const nav = h("header", { class: "lp-nav" },
    h("div", { class: "brand" }, h("img", { class: "logo", src: "brand/logo-mark-reversed.svg", alt: "", width: 28, height: 32 }), t("app")),
    h("nav", { class: "lp-links", "aria-label": "Page" },
      h("button", { type: "button", onClick: () => go("lp-features") }, t("lp_nav_features")),
      h("button", { type: "button", onClick: () => go("lp-roles") }, t("lp_nav_roles")),
      h("button", { type: "button", onClick: () => go("lp-security") }, t("lp_nav_security")),
      h("button", { type: "button", onClick: () => go("lp-faq") }, t("lp_nav_faq")),
      h("button", { type: "button", onClick: () => go("lp-contact") }, t("lp_nav_contact"))),
    langBtn,
    h("button", { class: "btn gold", type: "button", onClick: () => { go("login-card"); id.focus({ preventScroll: true }); } }, t("lp_signin")));

  const hero = h("section", { class: "lp-hero" },
    h("div", { class: "lp-hero-text" },
      h("span", { class: "lp-kicker" }, t("lp_kicker")),
      h("h1", {}, t("hero_title")), h("p", { class: "lead" }, t("hero_lead")),
      h("div", { class: "lp-cta" },
        h("button", { class: "btn gold lg", type: "button", onClick: () => go("lp-contact") }, t("lp_cta_demo")),
        h("button", { class: "btn ghost lg", type: "button", onClick: () => { go("login-card"); id.focus({ preventScroll: true }); } }, t("lp_cta_signin"))),
      h("ul", { class: "points" }, [["timesheet", "hero_p1"], ["chart", "hero_p2"], ["shield", "hero_p3"], ["spark", "hero_p4"]].map(([ic, k]) => h("li", {}, icon(ic), h("span", {}, t(k))))),
      h("p", { class: "lp-trust" }, t("lp_trust"))),
    h("div", { class: "lp-login", id: "login-card" }, sso, h("p", { class: "muted small lp-login-lead" }, t("lp_signin_lead")), form, starting, quick));

  const contact = h("section", { class: "lp-sec lp-contact-sec", id: "lp-contact", "data-reveal": "" }, h("div", { class: "lp-contact" },
    h("div", {}, h("h2", { class: "lp-h" }, t("lp_form_title")), h("p", { class: "lp-sub" }, t("lp_form_lead")),
      h("ul", { class: "lp-promise" }, ["lp_pm1", "lp_pm2", "lp_pm3"].map(k => h("li", {}, h("span", { class: "lp-mark", "aria-hidden": "true" }, "✓"), t(k)))),
      h("p", { class: "lp-mail" }, t("lp_or_mail"), " ", h("a", { href: "mailto:info@elevantec.sa", dir: "ltr" }, "info@elevantec.sa")),
      h("p", { class: "muted small" }, t("lp_privacy"))),
    consultForm()));
  const sticky = h("div", { class: "lp-sticky" }, h("button", { class: "btn gold lg", type: "button", onClick: () => go("lp-contact") }, t("lp_cta_demo")));
  const foot = h("footer", { class: "lp-foot" }, h("div", { class: "brand" }, h("img", { class: "logo", src: "brand/logo-mark-reversed.svg", alt: "", width: 22, height: 25 }), t("app")),
    h("span", {}, t("lp_footer")), h("a", { href: "mailto:info@elevantec.sa", dir: "ltr" }, "info@elevantec.sa"));

  const page = h("div", { class: "lp" }, nav, hero, S.proof(), S.preview(), S.problem(), S.features(), S.roles(), S.how(), S.security(), S.faq(), contact, h("div", { class: "timeline-wrap" }, board), foot, sticky);
  mount(root, page);
  S.reveal(page);
  document.title = `${t("app")} — ${t("lp_kicker")}`;
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

// Request a demo or consultation. Public: no sign-in; the platform owner reads the requests in Admin.
function consultForm() {
  const f = (name, extra = {}) => h("input", { name, ...extra });
  const name = f("name", { autocomplete: "name", required: true, maxlength: 120 });
  const org = f("organization", { autocomplete: "organization", required: true, maxlength: 160 });
  const job = f("job_title", { autocomplete: "organization-title", maxlength: 120 });
  const email = f("email", { type: "email", autocomplete: "email", required: true, maxlength: 200, dir: "ltr" });
  const phone = f("phone", { type: "tel", autocomplete: "tel", maxlength: 40, dir: "ltr" });
  const size = h("select", { name: "team_size" }, h("option", { value: "" }, t("lp_size_pick")), ["1-10", "11-50", "51-200", "200+"].map(v => h("option", { value: v }, v)));
  const msg = h("textarea", { name: "message", rows: 3, maxlength: 2000 });
  const trap = h("input", { name: "website", tabindex: "-1", autocomplete: "off", "aria-hidden": "true" });       // honeypot
  const kind = (v, label, on) => h("label", { class: "lp-radio" }, h("input", { type: "radio", name: "interest", value: v, checked: on }), h("span", {}, label));
  const out = h("div"), box = h("div");
  const btn = h("button", { class: "btn gold lg", type: "submit", style: "width:100%" }, t("lp_send"));
  const form = h("form", { class: "card lp-form", novalidate: true, onSubmit: guarded(btn, async (ev) => {
    ev.preventDefault();
    mount(out);
    if (name.value.trim().length < 2 || org.value.trim().length < 2 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim())) { mount(out, h("p", { class: "err", role: "alert" }, t("lp_req_err"))); return; }
    try {
      await api("POST", "/public/consultation", { name: name.value.trim(), organization: org.value.trim(), job_title: job.value.trim() || null, email: email.value.trim(), phone: phone.value.trim() || null,
        team_size: size.value || null, interest: form.elements.interest.value, message: msg.value.trim() || null, lang: getLang(), website: trap.value });
      const again = h("button", { class: "btn secondary", type: "button", onClick: () => { form.reset(); mount(box, form); } }, t("lp_another"));
      mount(box, h("div", { class: "card lp-done", role: "status" }, h("span", { class: "lp-tick" }, "✓"), h("h2", {}, t("lp_done_t")), h("p", { class: "muted" }, t("lp_done_d").replace("{email}", email.value.trim())), again));
    } catch (e) { mount(out, errorBox(e)); }
  }) },
    h("div", { class: "lp-radios", role: "radiogroup", "aria-label": t("lp_interest") }, kind("demo", t("lp_int_demo"), true), kind("consultation", t("lp_int_consult"), false)),
    h("div", { class: "lp-two" }, field(t("lp_name") + " *", name), field(t("lp_org") + " *", org)),
    h("div", { class: "lp-two" }, field(t("lp_job"), job), field(t("lp_size"), size)),
    h("div", { class: "lp-two" }, field(t("lp_email") + " *", email), field(t("lp_phone"), phone)),
    field(t("lp_msg"), msg), h("div", { class: "lp-trap", "aria-hidden": "true" }, field("Website", trap)), out, btn);
  mount(box, form);
  return box;
}
