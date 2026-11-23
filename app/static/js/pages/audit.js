// Audit log viewer + period lock (PMO / ADMIN).
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, table, toast, today } from "../ui.js";

const PAGE = 50;

export default async function (root, { me }) {
  const [facets, dir] = await Promise.all([api("GET", "/admin/audit/facets"), api("GET", "/directory")]);
  const state = { offset: 0 };
  const f = {
    actor: h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id }, u.full_name))),
    action: h("select", {}, h("option", { value: "" }, "—"), facets.actions.map(a => h("option", { value: a }, a))),
    entity: h("select", {}, h("option", { value: "" }, "—"), facets.entities.map(a => h("option", { value: a }, a))),
    from: h("input", { type: "date" }), to: h("input", { type: "date" }),
  };
  const results = h("div"), periodBox = h("div", { class: "card" });

  async function load() {
    const q = new URLSearchParams({ limit: PAGE, offset: state.offset });
    if (f.actor.value) q.set("actor_id", f.actor.value);
    if (f.action.value) q.set("action", f.action.value);
    if (f.entity.value) q.set("entity", f.entity.value);
    if (f.from.value) q.set("date_from", f.from.value);
    if (f.to.value) q.set("date_to", f.to.value);
    const r = await api("GET", `/admin/audit?${q}`);
    const prev = h("button", { class: "btn small secondary", type: "button", disabled: state.offset === 0, onClick: () => { state.offset = Math.max(0, state.offset - PAGE); load(); } }, t("prev"));
    const next = h("button", { class: "btn small secondary", type: "button", disabled: state.offset + PAGE >= r.total, onClick: () => { state.offset += PAGE; load(); } }, t("next"));
    mount(results, table([t("time"), t("actor"), t("action"), t("entity"), t("detail")], r.items.map(i => [String(i.ts).replace("T", " ").slice(0, 19), i.actor || (i.actor_id ?? "system"), badge(i.action, "GREY"), `${i.entity}${i.entity_id != null ? ` #${i.entity_id}` : ""}`,
      h("code", { class: "small" }, JSON.stringify(i.detail))]), t("none")),
      h("div", { class: "row", style: "margin-top:10px; align-items:center" }, prev, next, h("span", { class: "muted small" }, `${r.total ? state.offset + 1 : 0}–${Math.min(state.offset + PAGE, r.total)} / ${r.total}`)));
  }

  async function loadPeriods() {
    const p = await api("GET", "/timesheets/periods");
    const through = h("input", { type: "date", value: today() }), err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("lock_period"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      if (!confirm(t("lock_confirm").replace("{d}", through.value))) return;
      try { await api("POST", "/timesheets/periods/lock", { locked_through: through.value }); toast(t("saved")); await loadPeriods(); await load(); } catch (e) { mount(err, errorBox(e)); }
    }));
    const pend = Object.entries(p.pending_by_date);
    mount(periodBox, h("h2", {}, t("period_lock")), h("p", {}, `${t("locked_through")}: `, h("strong", {}, p.locked_through || t("none"))),
      h("p", { class: "muted small" }, t("period_note")),
      pend.length ? h("p", {}, badge(`${pend.reduce((a, [, n]) => a + n, 0)} ${t("pending_entries")}`, "AMBER"), ` ${t("oldest")}: ${pend[0][0]}`) : null,
      h("div", { class: "row" }, field(t("locked_through"), through), btn), err,
      p.history.length ? table([t("locked_through"), t("by"), t("time")], p.history.map(x => [x.locked_through, x.locked_by || "—", String(x.at).replace("T", " ").slice(0, 19)])) : null);
  }

  const go = h("button", { class: "btn", type: "button", onClick: () => { state.offset = 0; load(); } }, t("filter"));
  mount(root, h("h1", {}, t("nav_audit")), periodBox,
    h("div", { class: "card" }, h("h2", {}, t("audit_log")), h("p", { class: "muted small" }, t("audit_note")),
      h("div", { class: "row" }, field(t("actor"), f.actor), field(t("action"), f.action), field(t("entity"), f.entity), field(t("from"), f.from), field(t("to"), f.to), go), results));
  await Promise.all([loadPeriods(), load()]);
}
