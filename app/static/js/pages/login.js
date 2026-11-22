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
  mount(root, form);
  id.focus();
}
