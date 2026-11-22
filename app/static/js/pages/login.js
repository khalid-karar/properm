import { api, session } from "../api.js";
import { getLang, setLang, t } from "../i18n.js";
import { errorBox, field, guarded, h, mount } from "../ui.js";
import { homeFor, resetMe } from "../app.js";

export default function (root) {
  const msg = h("div");
  const id = h("input", { name: "staff_id", autocomplete: "username", required: true });
  const pw = h("input", { name: "password", type: "password", autocomplete: "current-password", required: true });
  const btn = h("button", { class: "btn", type: "submit" }, t("login"));
  const form = h("form", { class: "card login", onSubmit: guarded(btn, async (ev) => {
      ev.preventDefault();
      mount(msg);
      try {
        const r = await api("POST", "/auth/login", { staff_id: id.value.trim(), password: pw.value });
        session.set(r.access_token, r.role);
        resetMe();
        location.hash = `#/${homeFor(r.role)}`;
      } catch (e) { mount(msg, errorBox(e)); }
  }) },
    h("h1", {}, `${t("app")} — Smart PMO`),
    field(t("staff_id"), id), field(t("password"), pw), msg,
    h("div", { class: "row" }, btn,
      h("button", { class: "btn secondary right", type: "button", onClick: () => { setLang(getLang() === "en" ? "ar" : "en"); location.reload(); } }, getLang() === "en" ? "العربية" : "English")));
  const quick = h("div", { class: "card login", hidden: true });
  const starting = window.PROPERM_EMBEDDED ? h("div", { class: "card login" }, h("p", { class: "muted" }, t("demo_starting"))) : null;
  mount(root, form, starting, quick);
  id.focus();
  // Demo quick login: the server only answers when PROPERM_DEMO_LOGIN=1, otherwise this stays hidden.
  api("GET", "/auth/demo-users").then((users) => {
    if (starting) starting.hidden = true;
    if (!users.length) return;
    mount(quick, h("h2", {}, t("quick_login")), h("p", { class: "muted small" }, t("quick_login_note")),
      h("div", { class: "row" }, users.map(u => h("button", { class: "btn secondary", type: "button", onClick: guarded(null, async () => {
        const r = await api("POST", "/auth/demo-login", { staff_id: u.staff_id });
        session.set(r.access_token, r.role); resetMe(); location.hash = `#/${homeFor(r.role)}`;
      }) }, `${u.full_name} · ${u.role}`))));
    quick.hidden = false;
  }).catch(() => {});
}
