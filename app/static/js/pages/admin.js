import { api } from "../api.js";
import { t } from "../i18n.js";
import { errorBox, field, guarded, h, mount, num, table, toast, today } from "../ui.js";

const ROLES = ["STAFF", "PM", "PMO", "PROGRAM_MANAGER", "DECISION_MAKER", "ADMIN"];

export default async function (root) {
  async function render() {
    const [users, rates, cfg] = await Promise.all([api("GET", "/users"), api("GET", "/admin/rates"), api("GET", "/admin/rules")]);
    const f = { sid: h("input"), name: h("input"), pw: h("input", { type: "password", autocomplete: "new-password" }), role: h("select", {}, ROLES.map(r => h("option", { value: r }, r))), grade: h("input", { style: "width:90px" }),
      cap: h("input", { type: "number", value: "40", style: "width:80px" }), ccb: h("input", { type: "checkbox" }), lm: h("select", {}, h("option", { value: "" }, "—"), users.map(u => h("option", { value: u.id }, u.full_name))) };
    const uerr = h("div");
    const addU = h("button", { class: "btn", type: "button" }, t("create"));
    addU.addEventListener("click", guarded(addU, async () => {
      mount(uerr);
      try { await api("POST", "/users", { staff_id: f.sid.value.trim(), full_name: f.name.value.trim(), password: f.pw.value, role: f.role.value, rate_grade: f.grade.value.trim() || null, capacity_hours_week: Number(f.cap.value), is_ccb: f.ccb.checked, line_manager_id: f.lm.value ? Number(f.lm.value) : null }); toast(t("saved")); await render(); }
      catch (e) { mount(uerr, errorBox(e)); }
    }));
    const rg = h("input", { style: "width:90px" }), rv = h("input", { type: "number", min: "0", style: "width:100px" }), rc = h("input", { value: "SAR", maxlength: "3", style: "width:70px" }), rd = h("input", { type: "date", value: today() });
    const rerr = h("div");
    const addR = h("button", { class: "btn", type: "button" }, t("add"));
    addR.addEventListener("click", guarded(addR, async () => { mount(rerr); try { await api("POST", "/admin/rates", { grade: rg.value.trim(), hourly_rate: Number(rv.value), currency: rc.value.toUpperCase(), effective_from: rd.value }); toast(t("saved")); await render(); } catch (e) { mount(rerr, errorBox(e)); } }));

    const sevSel = (rule) => h("select", { value: cfg.severities[rule], onChange: guarded(null, async (ev) => { await api("PUT", `/admin/rules/${rule}`, { severity: ev.target.value }); toast(t("saved_ok")); }) }, ["BLOCK", "WARN", "FLAG"].map(s => h("option", { value: s }, s)));
    const setting = (key) => { const i = h("input", { type: "number", step: "any", value: cfg.params[key], style: "width:110px" }); i.addEventListener("change", guarded(i, async () => { await api("PUT", `/admin/settings/${key}`, { value: Number(i.value) }); toast(t("saved_ok")); })); return i; };

    mount(root, h("h1", {}, t("nav_admin")),
      h("div", { class: "card" }, h("h2", {}, t("users")), table([t("staff_id"), t("full_name"), t("role"), t("grade"), t("capacity"), t("is_ccb")], users.map(u => [u.staff_id, u.full_name, u.role, u.rate_grade || "—", num(u.capacity_hours_week), u.is_ccb ? "✓" : ""]), t("none")),
        h("h2", { style: "margin-top:14px" }, t("new_user")),
        h("div", { class: "row" }, field(t("staff_id"), f.sid), field(t("full_name"), f.name), field(t("password"), f.pw), field(t("role"), f.role), field(t("grade"), f.grade), field(t("capacity"), f.cap), field(t("is_ccb"), f.ccb), field(t("line_manager"), f.lm), addU), uerr),
      h("div", { class: "card" }, h("h2", {}, t("rates")), table([t("grade"), t("hourly_rate"), t("currency"), t("effective_from")], rates.map(r => [r.grade, num(r.hourly_rate, 2), r.currency, r.effective_from]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("grade"), rg), field(t("hourly_rate"), rv), field(t("currency"), rc), field(t("effective_from"), rd), addR), rerr),
      h("div", { class: "card" }, h("h2", {}, t("rules")), table([t("rule"), t("severity")], Object.keys(cfg.severities).sort().map(r => [r, sevSel(r)]))),
      h("div", { class: "card" }, h("h2", {}, t("settings")), table([t("rule"), t("amount")], Object.keys(cfg.params).sort().map(k => [k, setting(k)]))));
  }
  await render();
}
