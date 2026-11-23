// Project "Details" tab: intake fields, team, documents and stakeholders.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, table, toast } from "../ui.js";


export async function details(body, p, { pid, me, dir, canManage, render }) {
  const byId = Object.fromEntries(dir.map(u => [u.id, u]));
  const [stakes] = await Promise.all([api("GET", `/projects/${pid}/stakeholders`)]);
  const editable = canManage && p.state !== "archived";
  const afterBaseline = p.baseline_version > 0;

  // ----- intake fields -----
  const f = {
    name: h("input", { value: p.name, style: "min-width:260px" }),
    client: h("input", { value: p.client || "" }), sponsor: h("input", { value: p.sponsor || "" }),
    type: h("select", { disabled: afterBaseline }, ["predictive", "hybrid", "adaptive"].map(x => h("option", { value: x, selected: x === p.project_type }, t(`ptype_${x}`)))),
    start: h("input", { type: "date", value: p.planned_start || "", disabled: afterBaseline }), end: h("input", { type: "date", value: p.planned_end || "", disabled: afterBaseline }),
    budget: h("input", { type: "number", min: "0", value: p.budget_ceiling ?? "", disabled: afterBaseline, style: "width:140px" }),
    ccy: h("input", { value: p.currency, maxlength: "3", disabled: afterBaseline, style: "width:70px" }),
    scope: h("textarea", { rows: "4" }, p.scope_statement || ""),
  };
  f.scope.value = p.scope_statement || "";
  const err = h("div"), save = h("button", { class: "btn", type: "button" }, t("save"));
  save.addEventListener("click", guarded(save, async () => {
    mount(err);
    const b = { name: f.name.value.trim(), client: f.client.value.trim() || null, sponsor: f.sponsor.value.trim() || null, scope_statement: f.scope.value.trim() || null };
    if (!afterBaseline) Object.assign(b, { project_type: f.type.value, planned_start: f.start.value || null, planned_end: f.end.value || null, budget_ceiling: f.budget.value === "" ? null : Number(f.budget.value), currency: f.ccy.value.toUpperCase() });
    try { await api("PATCH", `/projects/${pid}`, b); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); }
  }));
  const ro = (v) => h("span", {}, v || "—");
  const info = h("div", { class: "card" }, h("h2", {}, t("project_details")),
    afterBaseline ? h("p", { class: "muted small" }, t("details_locked_note")) : null,
    editable
      ? h("div", {}, h("div", { class: "row" }, field(t("name"), f.name), field(t("client"), f.client), field(t("sponsor"), f.sponsor), field(t("project_type"), f.type)),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("planned_start"), f.start), field(t("planned_end"), f.end), field(t("budget"), f.budget), field(t("currency"), f.ccy)),
        h("div", { style: "margin-top:12px" }, field(t("scope_statement"), f.scope)), h("div", { class: "row", style: "margin-top:12px" }, save), err)
      : h("dl", { class: "dl" }, [[t("client"), p.client], [t("sponsor"), p.sponsor], [t("project_type"), t(`ptype_${p.project_type}`)], [t("budget"), p.budget_ceiling != null ? `${p.budget_ceiling.toLocaleString()} ${p.currency}` : null], [t("scope_statement"), p.scope_statement]]
        .map(([k, v]) => h("div", {}, h("dt", {}, k), h("dd", {}, ro(v))))));

  // ----- team -----
  const ids = p.assigned_user_ids || [];
  const who = h("select", {}, dir.filter(u => !ids.includes(u.id)).map(u => h("option", { value: u.id }, `${u.full_name} (${u.staff_id})`)));
  const addBtn = h("button", { class: "btn secondary", type: "button" }, t("assign_staff"));
  addBtn.addEventListener("click", guarded(addBtn, async () => { if (!who.value) return; await api("POST", `/projects/${pid}/assignments`, { user_id: Number(who.value) }); toast(t("staff_assigned")); await render(); }));
  const mgr = h("select", {}, dir.filter(u => ["PM", "PMO", "ADMIN"].includes(u.role)).map(u => h("option", { value: u.id, selected: u.id === p.pm_id }, u.full_name)));
  const team = h("div", { class: "card" }, h("h2", {}, t("team")),
    h("p", {}, h("strong", {}, `${t("project_manager")}: `), byId[p.pm_id]?.full_name || p.pm_id),
    ["PMO", "ADMIN"].includes(me.role) ? h("div", { class: "row", style: "margin-bottom:12px" }, field(t("project_manager"), mgr),
      h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, async () => { await api("PUT", `/projects/${pid}/manager`, { user_id: Number(mgr.value) }); toast(t("saved")); await render(); }) }, t("reassign"))) : null,
    canManage ? [table([t("name"), t("role"), ""], ids.map(id => [byId[id]?.full_name || `#${id}`, byId[id]?.role || "", id === p.pm_id ? badge(t("project_manager"), "gold") :
      h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/projects/${pid}/assignments/${id}`); await render(); }) }, t("remove"))]), t("none")),
      h("div", { class: "row", style: "margin-top:12px" }, field(t("staff"), who), addBtn)] : null);

  // ----- stakeholders -----
  const s = { name: h("input"), org: h("input"), role: h("input"), power: h("input", { type: "number", min: "1", max: "5", value: "3", style: "width:70px" }), interest: h("input", { type: "number", min: "1", max: "5", value: "3", style: "width:70px" }), eng: h("input", { style: "min-width:220px" }) };
  const serr = h("div"), sadd = h("button", { class: "btn", type: "button" }, t("add"));
  sadd.addEventListener("click", guarded(sadd, async () => {
    mount(serr);
    try { await api("POST", `/projects/${pid}/stakeholders`, { name: s.name.value.trim(), organisation: s.org.value.trim() || null, role: s.role.value.trim() || null, power: Number(s.power.value), interest: Number(s.interest.value), engagement: s.eng.value.trim() || null }); toast(t("saved")); await render(); }
    catch (e) { mount(serr, errorBox(e)); }
  }));
  const stake = h("div", { class: "card" }, h("h2", {}, t("stakeholders")),
    table([t("name"), t("organisation"), t("role"), t("power"), t("interest"), t("engagement"), ""], stakes.map(x => [x.name, x.organisation || "—", x.role || "—", x.power, x.interest, x.engagement || "—",
      canManage ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/projects/${pid}/stakeholders/${x.id}`); await render(); }) }, t("remove")) : ""]), t("none")),
    editable ? h("div", { class: "row", style: "margin-top:12px" }, field(t("name"), s.name), field(t("organisation"), s.org), field(t("role"), s.role), field(t("power"), s.power), field(t("interest"), s.interest), field(t("engagement"), s.eng), sadd) : null, serr);

  mount(body, info, team, stake);
}
