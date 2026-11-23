// Project "RACI & communication" tab, and the resource-request card used on the Allocations tab.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { registerCard } from "../register.js";
import { badge, errorBox, field, guarded, h, mount, num, table, toast, today } from "../ui.js";

const LET = ["", "R", "A", "C", "I"];
const FREQ = ["weekly", "biweekly", "monthly", "quarterly", "milestone", "ad_hoc"];

export async function team(body, p, { pid, me, dir, canManage, render }) {
  const [raci, comms, sh] = await Promise.all([api("GET", `/projects/${pid}/raci`), api("GET", `/projects/${pid}/comms`), api("GET", `/projects/${pid}/stakeholders`).catch(() => [])]);
  const cellOf = (it, pe) => (raci.cells.find(c => c.item === it && c.person === pe) || {}).letter || "";
  const put = (item, person, letter) => api("PUT", `/projects/${pid}/raci`, { item, person, letter }).then(render);
  const newItem = h("input", { placeholder: t("raci_item_ph") }), newPerson = h("input", { list: "raci-people", placeholder: t("raci_person_ph") });
  const suggest = h("datalist", { id: "raci-people" }, [...dir.map(u => u.full_name), ...sh.map(s => s.name)].map(n => h("option", { value: n })));
  const rerr = h("div");
  const grid = raci.items.length && raci.people.length ? h("div", { style: "overflow-x:auto" }, h("table", { class: "heat raci" },
    h("thead", {}, h("tr", {}, h("th", {}, t("deliverable")), raci.people.map(pe => h("th", {}, pe, canManage ? h("button", { class: "x", type: "button", title: t("remove"), onClick: guarded(null, async () => { await api("DELETE", `/projects/${pid}/raci?person=${encodeURIComponent(pe)}`); await render(); }) }, "×") : null)))),
    h("tbody", {}, raci.items.map(it => h("tr", {}, h("td", {}, it, canManage ? h("button", { class: "x", type: "button", title: t("remove"), onClick: guarded(null, async () => { await api("DELETE", `/projects/${pid}/raci?item=${encodeURIComponent(it)}`); await render(); }) }, "×") : null),
      raci.people.map(pe => h("td", { class: `rl-${cellOf(it, pe) || "n"}` }, canManage ? h("select", { onChange: guarded(null, (e) => put(it, pe, e.target.value)) }, LET.map(l => h("option", { value: l, selected: l === cellOf(it, pe) }, l || "·"))) : cellOf(it, pe))))))))
    : h("p", { class: "muted" }, t("raci_empty"));
  const rcard = h("div", { class: "card", id: "raci-card" }, h("h2", {}, t("raci")), h("p", { class: "muted small" }, t("raci_note")), grid,
    raci.warnings.length ? h("ul", { class: "checks" }, raci.warnings.map(w => h("li", { class: "bad" }, `✗ ${w.item}: ${t(`raci_${w.problem}`)}`))) : null,
    canManage ? h("div", { class: "row", style: "margin-top:12px" }, suggest, field(t("deliverable"), newItem), field(t("person"), newPerson),
      field(t("role"), h("select", { id: "raci-letter" }, LET.slice(1).map(l => h("option", { value: l }, `${l} · ${t(`raci_l_${l}`)}`)))),
      h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(rerr); try { await put(newItem.value.trim(), newPerson.value.trim(), document.getElementById("raci-letter").value); } catch (e) { mount(rerr, errorBox(e)); } }) }, t("add"))) : null, rerr);

  const c = { aud: h("input"), info: h("input"), how: h("input", { placeholder: t("comm_method_ph") }), freq: h("select", {}, FREQ.map(f => h("option", { value: f, selected: f === "monthly" }, t(`fq_${f}`)))),
    owner: h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id }, u.full_name))) };
  const cerr = h("div");
  const ccard = h("div", { class: "card", id: "comms-card" }, h("h2", {}, t("comm_plan")), h("p", { class: "muted small" }, t("comm_note")),
    table([t("audience"), t("information"), t("method"), t("frequency"), t("owner"), t("last_sent"), t("next_due"), ""], comms.map(x => [x.audience, x.information, x.method, t(`fq_${x.frequency}`), x.owner || "—", x.last_sent || "—",
      x.next_due ? h("span", { class: x.overdue ? "neg" : "" }, x.next_due) : "—",
      h("span", { class: "row", style: "gap:6px;flex-wrap:nowrap" }, canManage || x.owner_id === me.id ? h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/comms/${x.id}/sent`); toast(t("saved")); await render(); }) }, t("mark_sent")) : null,
        canManage ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/projects/${pid}/comms/${x.id}`); await render(); }) }, t("remove")) : null)]), t("none")),
    canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("audience"), c.aud), field(t("information"), c.info), field(t("method"), c.how), field(t("frequency"), c.freq), field(t("owner"), c.owner),
      h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(cerr); try { await api("POST", `/projects/${pid}/comms`, { audience: c.aud.value.trim(), information: c.info.value.trim(), method: c.how.value.trim(), frequency: c.freq.value, owner_id: c.owner.value ? Number(c.owner.value) : null }); toast(t("saved")); await render(); } catch (e) { mount(cerr, errorBox(e)); } }) }, t("add"))) : null, cerr);
  const norms = await api("GET", `/projects/${pid}/team-norms`);
  const ncard = registerCard({ id: "norms-card", title: t("team_charter"), note: t("team_charter_note"), base: `/projects/${pid}/team-norms`, rows: norms, canManage: canManage && p.state !== "archived", render, dir,
    fields: [{ k: "category", label: t("category"), type: "select", options: ["communication", "meetings", "decisions", "conflict", "quality", "other"].map(x => [x, t(`tn_${x}`)]), def: "communication" }, { k: "text", label: t("text"), type: "textarea", req: true }],
    columns: [{ h: t("category"), f: r => t(`tn_${r.category}`) }, { h: t("text"), f: r => r.text }] });
  mount(body, rcard, ccard, ncard);
}

const RRCLS = { requested: "AMBER", fulfilled: "GREEN", rejected: "RED", cancelled: "GREY" };

export async function requestCard(pid, canManage, render) {
  const list = await api("GET", `/projects/${pid}/resource-requests`);
  const f = { skill: h("input", { placeholder: t("rr_skill_ph") }), dep: h("input"), hpw: h("input", { type: "number", min: "1", max: "80", value: "20", style: "width:90px" }),
    s: h("input", { type: "date", value: today() }), e: h("input", { type: "date" }), note: h("input") };
  const err = h("div");
  return h("div", { class: "card", id: "rr-card" }, h("h2", {}, t("resource_requests")), h("p", { class: "muted small" }, t("rr_note")),
    table([t("rr_skill"), t("department"), t("hours_per_week"), t("from"), t("to"), t("status"), t("rr_assigned"), ""], list.map(x => [x.skill, x.department || "—", num(x.hours_per_week), x.start, x.end, badge(t(`rr_${x.status}`), RRCLS[x.status]), x.assigned || x.decision_reason || "",
      canManage && x.status === "requested" ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/projects/${pid}/resource-requests/${x.id}`); await render(); }) }, t("cancel")) : ""]), t("none")),
    canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("rr_skill"), f.skill), field(t("department"), f.dep), field(t("hours_per_week"), f.hpw), field(t("from"), f.s), field(t("to"), f.e), field(t("note"), f.note),
      h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(err); try { await api("POST", `/projects/${pid}/resource-requests`, { skill: f.skill.value.trim(), department: f.dep.value.trim() || null, hours_per_week: Number(f.hpw.value), start: f.s.value, end: f.e.value || f.s.value, note: f.note.value.trim() || null }); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } }) }, t("request"))) : null, err);
}
