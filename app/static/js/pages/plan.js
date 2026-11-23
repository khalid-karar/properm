// Project "Plan" tab: milestones, KPIs, dependencies, per-person activity limits.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, bar, errorBox, field, guarded, h, mount, num, table, toast } from "../ui.js";

const RAG = { green: "GREEN", amber: "AMBER", red: "RED" };
const delBtn = (fn) => h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, fn) }, t("remove"));

export async function plan(body, p, { pid, dir, canManage, render }) {
  const byId = Object.fromEntries(dir.map(u => [u.id, u]));
  const acts = p.activities.filter(a => a.phase === "execution");
  const editable = canManage && p.state !== "archived";
  const [ms, kpis, deps, limits] = await Promise.all([
    api("GET", `/projects/${pid}/milestones`), api("GET", `/projects/${pid}/kpis`), api("GET", `/projects/${pid}/dependencies`),
    canManage ? api("GET", `/projects/${pid}/limits`) : [],
  ]);
  const actSel = (blank) => h("select", {}, blank ? h("option", { value: "" }, "—") : null, acts.map(a => h("option", { value: a.id }, `${a.code} · ${a.name}`)));
  const form = (fields, submit, label) => {
    const err = h("div"), btn = h("button", { class: "btn", type: "button" }, label || t("add"));
    btn.addEventListener("click", guarded(btn, async () => { mount(err); try { await submit(); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } }));
    return h("div", {}, h("div", { class: "row", style: "margin-top:12px" }, fields, btn), err);
  };

  // milestones
  const m = { name: h("input"), due: h("input", { type: "date" }), act: actSel(true) };
  const mcard = h("div", { class: "card" }, h("h2", {}, t("milestones")),
    table([t("name"), t("ms_due"), t("status"), t("slip_days"), ""], ms.map(x => [x.name, x.due_date, badge(t(`ms_${x.status}`), x.status === "achieved" ? "GREEN" : x.status === "missed" ? "RED" : "GREY"), x.slip_days || "—",
      editable ? h("span", { class: "row", style: "gap:6px" },
        x.achieved_on ? "" : h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("PATCH", `/projects/${pid}/milestones/${x.id}`, { achieved_on: new Date().toISOString().slice(0, 10) }); await render(); }) }, t("mark_achieved")),
        delBtn(async () => { await api("DELETE", `/projects/${pid}/milestones/${x.id}`); await render(); })) : ""]), t("none")),
    editable ? form([field(t("name"), m.name), field(t("ms_due"), m.due), field(t("activity"), m.act)],
      () => api("POST", `/projects/${pid}/milestones`, { name: m.name.value.trim(), due_date: m.due.value, activity_id: m.act.value ? Number(m.act.value) : null })) : null);

  // KPIs
  const k = { name: h("input"), unit: h("input", { style: "width:80px" }), target: h("input", { type: "number", step: "any", style: "width:110px" }), hib: h("select", {}, h("option", { value: "1" }, t("higher_better")), h("option", { value: "0" }, t("lower_better"))) };
  const kcard = h("div", { class: "card" }, h("h2", {}, t("kpis")),
    table([t("name"), t("target"), t("actual"), t("achievement"), t("kpi_status"), ""], kpis.map(x => {
      const inp = h("input", { type: "number", step: "any", value: x.actual ?? "", style: "width:100px" });
      return [`${x.name}${x.unit ? ` (${x.unit})` : ""}`, num(x.target, 2), editable ? h("span", { class: "row", style: "gap:6px" }, inp, h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { if (inp.value === "") return; await api("PUT", `/projects/${pid}/kpis/${x.id}/actual`, { actual: Number(inp.value) }); await render(); }) }, t("save"))) : num(x.actual, 2),
        x.achievement_pct != null ? h("div", { style: "min-width:90px" }, `${x.achievement_pct}%`, bar(x.achievement_pct, x.rag === "red")) : "—", x.rag ? badge(RAG[x.rag], RAG[x.rag]) : "—",
        editable ? delBtn(async () => { await api("DELETE", `/projects/${pid}/kpis/${x.id}`); await render(); }) : ""];
    }), t("none")),
    editable ? form([field(t("name"), k.name), field(t("unit"), k.unit), field(t("target"), k.target), field(t("direction"), k.hib)],
      () => api("POST", `/projects/${pid}/kpis`, { name: k.name.value.trim(), unit: k.unit.value.trim() || null, target: Number(k.target.value), higher_is_better: k.hib.value === "1" })) : null);

  // dependencies
  const d = { a: actSel(), pr: actSel() };
  const dcard = h("div", { class: "card" }, h("h2", {}, t("dependencies")), h("p", { class: "muted small" }, t("dep_note")),
    table([t("activity"), t("depends_on"), t("status"), ""], deps.map(x => [x.activity_code, x.predecessor_code, x.date_conflict ? badge(t("date_conflict"), "AMBER") : badge("OK", "GREEN"),
      editable ? delBtn(async () => { await api("DELETE", `/projects/${pid}/dependencies/${x.id}`); await render(); }) : ""]), t("none")),
    editable && acts.length > 1 ? form([field(t("activity"), d.a), field(t("depends_on"), d.pr)], () => api("POST", `/projects/${pid}/dependencies`, { activity_id: Number(d.a.value), predecessor_id: Number(d.pr.value) })) : null);

  // limits
  const l = { a: actSel(), u: h("select", {}, (p.assigned_user_ids || []).map(id => h("option", { value: id }, byId[id]?.full_name || id))), hrs: h("input", { type: "number", min: "0", step: "any", style: "width:100px" }) };
  const lcard = canManage ? h("div", { class: "card" }, h("h2", {}, t("activity_limits")), h("p", { class: "muted small" }, t("limits_note")),
    table([t("activity"), t("name"), t("max_hours"), ""], limits.map(x => [x.activity_code, byId[x.user_id]?.full_name || x.user_id, num(x.max_hours),
      editable ? delBtn(async () => { await api("DELETE", `/projects/${pid}/activities/${x.activity_id}/limits/${x.user_id}`); await render(); }) : ""]), t("none")),
    editable && acts.length ? form([field(t("activity"), l.a), field(t("staff"), l.u), field(t("max_hours"), l.hrs)],
      () => api("PUT", `/projects/${pid}/activities/${l.a.value}/limits`, { user_id: Number(l.u.value), max_hours: Number(l.hrs.value) }), t("save")) : null) : null;

  mount(body, mcard, kcard, dcard, lcard);
}
