// Landing page: start a 14-day sandbox with sample data. Shown only when the server has trials switched on.
import { api } from "../api.js";
import { getLang, t } from "../i18n.js";
import { errorBox, field, guarded, h, mount } from "../ui.js";

export async function trialCard(slot) {
  let cfg;
  try { cfg = await api("GET", "/public/trial/config"); } catch { return; }
  if (!cfg.enabled) return;
  const name = h("input", { name: "name", autocomplete: "name", maxlength: 120, required: true });
  const org = h("input", { name: "organization", autocomplete: "organization", maxlength: 120, required: true });
  const email = h("input", { name: "email", type: "email", autocomplete: "email", maxlength: 200, dir: "ltr", required: true });
  const trap = h("input", { name: "website", tabindex: "-1", autocomplete: "off", "aria-hidden": "true" });
  const out = h("div");
  const btn = h("button", { class: "btn gold", type: "submit", id: "trial-go", style: "width:100%" }, t("tr_start"));
  const copy = (v) => h("code", { dir: "ltr", style: "user-select:all" }, v);
  const form = h("form", { class: "card lp-form", id: "trial-card", novalidate: true, onSubmit: guarded(btn, async (ev) => {
    ev.preventDefault();
    mount(out);
    if (name.value.trim().length < 2 || org.value.trim().length < 2 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim())) { mount(out, h("p", { class: "err", role: "alert" }, t("lp_req_err"))); return; }
    try {
      const r = await api("POST", "/public/trial", { name: name.value.trim(), organization: org.value.trim(), email: email.value.trim(), lang: getLang(), website: trap.value });
      if (!r.password) return;
      const state = h("p", { class: "small", id: "trial-state" }, t("tr_loading"));
      mount(slot, h("div", { class: "card lp-done", id: "trial-done", role: "status" }, h("h3", {}, t("tr_ready_t")), h("p", { class: "warn small" }, t("tr_once")),
        h("p", { class: "small" }, `${t("tr_password")}: `, copy(r.password)),
        h("ul", { class: "small" }, r.accounts.map(a => h("li", {}, copy(a.staff_id), ` · ${a.role}`))),
        h("p", { class: "small muted" }, t("tr_until").replace("{date}", r.expires)), state));
      for (let i = 0; i < 60; i++) {
        await new Promise(res => setTimeout(res, 3000));
        const s = await api("GET", `/public/trial/status?slug=${encodeURIComponent(r.slug)}`).catch(() => ({ state: "loading" }));
        if (s.state === "ready") { state.textContent = t("tr_ok"); state.className = "ok small"; break; }
        if (s.state === "failed") { state.textContent = t("tr_failed"); state.className = "err small"; break; }
      }
    } catch (e) { mount(out, errorBox(e)); }
  }) }, h("h3", {}, t("tr_title")), h("p", { class: "muted small" }, t("tr_lead")),
    h("div", { class: "lp-two" }, field(t("lp_name") + " *", name), field(t("lp_org") + " *", org)), field(t("lp_email") + " *", email),
    h("div", { class: "lp-trap", "aria-hidden": "true" }, field("Website", trap)), out, btn);
  mount(slot, form);
}
