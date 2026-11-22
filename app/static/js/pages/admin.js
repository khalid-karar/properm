import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, modal, mount, num, table, toast, today } from "../ui.js";

const ROLES = ["STAFF", "PM", "PMO", "PROGRAM_MANAGER", "DECISION_MAKER", "ADMIN"];

export default async function (root) {
  function editUser(u, users, me) {
    const f = { name: h("input", { value: u.full_name }), role: h("select", {}, ROLES.map(r => h("option", { value: r, selected: r === u.role }, r))),
      grade: h("input", { value: u.rate_grade || "" }), email: h("input", { type: "email", value: u.email || "" }), cap: h("input", { type: "number", value: u.capacity_hours_week, style: "width:80px" }), ccb: h("input", { type: "checkbox", checked: u.is_ccb }),
      active: h("input", { type: "checkbox", checked: u.active, disabled: u.id === me.id }), pw: h("input", { type: "password", autocomplete: "new-password" }),
      lm: h("select", {}, h("option", { value: "" }, "—"), users.filter(x => x.id !== u.id).map(x => h("option", { value: x.id, selected: x.id === u.line_manager_id }, x.full_name))) };
    const err = h("div");
    modal({ title: `${t("edit")}: ${u.staff_id}`,
      body: h("div", {}, h("div", { class: "row" }, field(t("full_name"), f.name), field(t("role"), f.role), field(t("grade"), f.grade), field(t("capacity"), f.cap), field(t("line_manager"), f.lm), field(t("email"), f.email)),
        h("div", { class: "row", style: "margin-top:10px" }, field(t("is_ccb"), f.ccb), field(t("active"), f.active), field(t("new_password"), f.pw)), err),
      actions: [{ label: t("cancel"), onClick: (close) => close() }, { label: t("save"), class: "primary", onClick: async (close) => {
        mount(err);
        const body = { full_name: f.name.value.trim(), role: f.role.value, rate_grade: f.grade.value.trim() || null, capacity_hours_week: Number(f.cap.value), is_ccb: f.ccb.checked, line_manager_id: f.lm.value ? Number(f.lm.value) : null, email: f.email.value.trim() || null, active: f.active.checked };
        if (f.pw.value) body.new_password = f.pw.value;
        try { await api("PATCH", `/users/${u.id}`, body); toast(t("saved")); close(); await render(); } catch (e) { mount(err, errorBox(e)); }
      } }] });
  }

  async function render() {
    const me = await api("GET", "/me");
    const [users, rates, cfg] = await Promise.all([api("GET", "/users"), api("GET", "/admin/rates"), api("GET", "/admin/rules")]);
    const f = { sid: h("input"), name: h("input"), pw: h("input", { type: "password", autocomplete: "new-password" }), role: h("select", {}, ROLES.map(r => h("option", { value: r }, r))), grade: h("input", { style: "width:90px" }),
      cap: h("input", { type: "number", value: "40", style: "width:80px" }), ccb: h("input", { type: "checkbox" }), lm: h("select", {}, h("option", { value: "" }, "—"), users.map(u => h("option", { value: u.id }, u.full_name))) };
    const uerr = h("div");
    const hols = await api("GET", "/calendar/holidays");
    const hd = h("input", { type: "date" }), hn = h("input", { placeholder: t("holiday_name") }), herr = h("div");
    const addH = h("button", { class: "btn", type: "button" }, t("add_holiday"));
    addH.addEventListener("click", guarded(addH, async () => {
      mount(herr);
      try { await api("POST", "/calendar/holidays", { day: hd.value, name: hn.value.trim() }); toast(t("saved")); await render(); } catch (e) { mount(herr, errorBox(e)); }
    }));
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
      h("div", { class: "card" }, h("h2", {}, t("users")), table([t("staff_id"), t("full_name"), t("role"), t("grade"), t("capacity"), t("is_ccb"), t("status"), ""], users.map(u => [u.staff_id, u.full_name, u.role, u.rate_grade || "—", num(u.capacity_hours_week), u.is_ccb ? "✓" : "", badge(u.active ? t("active") : t("inactive"), u.active ? "approved" : "critical"), h("button", { class: "btn small", type: "button", onClick: () => editUser(u, users, me) }, t("edit"))]), t("none")),
        h("h2", { style: "margin-top:14px" }, t("new_user")),
        h("div", { class: "row" }, field(t("staff_id"), f.sid), field(t("full_name"), f.name), field(t("password"), f.pw), field(t("role"), f.role), field(t("grade"), f.grade), field(t("capacity"), f.cap), field(t("is_ccb"), f.ccb), field(t("line_manager"), f.lm), addU), uerr),
      h("div", { class: "card" }, h("h2", {}, t("rates")), table([t("grade"), t("hourly_rate"), t("currency"), t("effective_from")], rates.map(r => [r.grade, num(r.hourly_rate, 2), r.currency, r.effective_from]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("grade"), rg), field(t("hourly_rate"), rv), field(t("currency"), rc), field(t("effective_from"), rd), addR), rerr),
      h("div", { class: "card" }, h("h2", {}, t("holidays")), h("p", { class: "muted" }, t("work_week_note")),
        table([t("date"), t("name"), ""], hols.map(x => [x.day, x.name, h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/calendar/holidays/${x.id}`); await render(); }) }, t("remove"))]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("date"), hd), field(t("name"), hn), addH), herr),
      h("div", { class: "card" }, h("h2", {}, t("rules")), table([t("rule"), t("severity")], Object.keys(cfg.severities).sort().map(r => [r, sevSel(r)]))),
      h("div", { class: "card" }, h("h2", {}, t("settings")), table([t("rule"), t("amount")], Object.keys(cfg.params).sort().map(k => [k, setting(k)]))));
  }
  await render();
}
