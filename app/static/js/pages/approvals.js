import { api } from "../api.js";
import { t } from "../i18n.js";
import { askText, badge, field, guarded, h, mount, num, table, toast } from "../ui.js";

export default async function (root, { me }) {
  const dir = Object.fromEntries((await api("GET", "/directory")).map(u => [u.id, u]));
  const projects = Object.fromEntries((await api("GET", "/projects")).map(p => [p.id, p]));
  const F = { project: "", user: "", flagged: false };
  const picked = new Set();

  async function render() {
    const q = new URLSearchParams();
    if (F.project) q.set("project_id", F.project);
    if (F.user) q.set("user_id", F.user);
    if (F.flagged) q.set("flagged", "true");
    const rows = await api("GET", `/timesheets/queue/filtered?${q}`);
    const history = await api("GET", "/timesheets/decided");
    const canDecide = me.is_ccb || ["PMO", "ADMIN"].includes(me.role);
    const changes = canDecide ? await api("GET", "/changes/pending") : [];
    const cdecide = async (c, body) => { await api("POST", `/projects/${c.project_id}/changes/${c.id}/decision`, body); toast(t("saved")); await render(); };
    const decide = async (id, body) => { await api("POST", `/timesheets/${id}/decision`, body); toast(t("saved")); picked.delete(id); await render(); };
    const bulk = async (action) => {
      const ids = [...picked].filter(id => rows.some(r => r.id === id));
      if (!ids.length) return;
      let reason = null;
      if (action === "reject") { reason = await askText(t("reject"), t("reason")); if (reason === null) return; }
      const r = await api("POST", "/timesheets/bulk-decision", { ids, action, reason });
      picked.clear();
      toast(`${r.done.length} ${t("done_count")}${r.failed.length ? ` · ${r.failed.length} ${t("failed_count")}: ${r.failed[0].error}` : ""}`, r.failed.length ? "err" : "ok");
      await render();
    };
    const people = [...new Set(rows.map(r => r.user_id))];
    const projSel = h("select", { onChange: (e) => { F.project = e.target.value; render(); } }, h("option", { value: "" }, t("all")), Object.values(projects).map(p => h("option", { value: p.id, selected: String(p.id) === String(F.project) }, p.number)));
    const userSel = h("select", { onChange: (e) => { F.user = e.target.value; render(); } }, h("option", { value: "" }, t("all")), Object.values(dir).map(u => h("option", { value: u.id, selected: String(u.id) === String(F.user) }, u.full_name)));
    const flagBox = h("input", { type: "checkbox", checked: F.flagged, onChange: (e) => { F.flagged = e.target.checked; render(); } });
    const all = h("input", { type: "checkbox", checked: rows.length > 0 && rows.every(r => picked.has(r.id)), "aria-label": t("select_all"), onChange: (e) => { rows.forEach(r => e.target.checked ? picked.add(r.id) : picked.delete(r.id)); render(); } });
    const cell = (e) => h("span", { class: "small" }, [e.overtime_flag ? badge(t("overtime"), "warning") : null, e.overtime_reason, ...(e.flags || [])].filter(Boolean).map(x => x.nodeType ? x : h("span", {}, x + " ")));
    mount(root, h("h1", {}, t("queue")),
      h("div", { class: "card" },
        h("div", { class: "row", style: "margin-bottom:10px; align-items:end" }, field(t("project"), projSel), field(t("staff"), userSel), h("label", { style: "flex-direction:row;align-items:center;gap:8px" }, flagBox, t("flagged_only")),
          h("span", { class: "grow" }), h("button", { class: "btn small", type: "button", disabled: !picked.size, onClick: guarded(null, () => bulk("approve")) }, `${t("approve_selected")} (${picked.size})`),
          h("button", { class: "btn danger small", type: "button", disabled: !picked.size, onClick: guarded(null, () => bulk("reject")) }, t("reject_selected"))),
        table([all, t("staff"), t("date"), t("project"), t("hours"), t("flags"), ""],
          rows.map(e => [h("input", { type: "checkbox", checked: picked.has(e.id), "aria-label": t("select"), onChange: (ev) => { ev.target.checked ? picked.add(e.id) : picked.delete(e.id); render(); } }),
            (dir[e.user_id] || {}).full_name || e.user_id, e.entry_date,
            e.project_id ? (projects[e.project_id] || {}).number || e.project_id : `${t("non_project")}: ${e.code}`,
            num(e.hours), cell(e),
            h("div", { class: "row", style: "flex-wrap:nowrap" },
              h("button", { class: "btn small", onClick: guarded(null, () => decide(e.id, { action: "approve" })) }, t("approve")),
              h("button", { class: "btn secondary small", onClick: guarded(null, async () => { const n = await askText(t("adjust"), t("hours")); if (n === null) return; const r = await askText(t("adjust"), t("reason")); if (r === null) return; await decide(e.id, { action: "adjust", hours: Number(n), reason: r }); }) }, t("adjust")),
              h("button", { class: "btn danger small", onClick: guarded(null, async () => { const r = await askText(t("reject"), t("reason")); if (r !== null) await decide(e.id, { action: "reject", reason: r }); }) }, t("reject")))]),
          t("queue_empty"))),
      canDecide ? h("div", { class: "card" }, h("h2", {}, t("pending_changes")), table([t("project"), t("change_type"), t("description"), t("hours_delta"), t("cost_delta"), t("schedule_days"), t("requested_by"), ""],
        changes.map(c => [(projects[c.project_id] || {}).number || c.project_id, t(`ct_${c.change_type}`), c.description, num(c.impact_hours_delta), num(c.impact_cost_delta, 0), num(c.impact_schedule_days, 0), (dir[c.requested_by] || {}).full_name || c.requested_by,
          h("div", { class: "row", style: "flex-wrap:nowrap" },
            h("button", { class: "btn small", onClick: guarded(null, () => cdecide(c, { approve: true })) }, t("approve")),
            h("button", { class: "btn danger small", onClick: guarded(null, async () => { const r = await askText(t("reject"), t("reason")); if (r !== null) await cdecide(c, { approve: false, reason: r }); }) }, t("reject")))]), t("none"))) : null,
      h("div", { class: "card" }, h("h2", {}, t("my_decisions")), h("p", { class: "muted small" }, t("my_decisions_note")),
        table([t("staff"), t("date"), t("project"), t("hours"), t("status"), t("reason")], history.map(e => [(dir[e.user_id] || {}).full_name || e.user_id, e.entry_date,
          e.project_id ? (projects[e.project_id] || {}).number || e.project_id : `${t("non_project")}: ${e.code}`, num(e.hours) + (e.original_hours ? ` (${num(e.original_hours)})` : ""), badge(t(e.status), e.status), e.decision_reason || ""]), t("none"))));
  }
  await render();
}
