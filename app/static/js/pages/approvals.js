import { api } from "../api.js";
import { t } from "../i18n.js";
import { askText, badge, errorBox, field, guarded, h, modal, mount, num, table, toast } from "../ui.js";

export default async function (root) {
  const dir = Object.fromEntries((await api("GET", "/directory")).map(u => [u.id, u]));
  const projects = Object.fromEntries((await api("GET", "/projects")).map(p => [p.id, p]));

  async function render() {
    const rows = await api("GET", "/timesheets/queue");
    const decide = async (id, body) => { await api("POST", `/timesheets/${id}/decision`, body); toast(t("saved")); await render(); };
    mount(root, h("h1", {}, t("queue")),
      h("div", { class: "card" }, table([t("staff"), t("date"), t("project"), t("hours"), t("flags"), ""],
        rows.map(e => [(dir[e.user_id] || {}).full_name || e.user_id, e.entry_date,
          e.project_id ? (projects[e.project_id] || {}).number || e.project_id : `${t("non_project")}: ${e.code}`,
          num(e.hours), h("span", { class: "small" }, [e.overtime_flag ? badge(t("overtime"), "warning") : null, e.overtime_reason, ...(e.flags || [])].filter(Boolean).map(x => x.nodeType ? x : h("span", {}, x + " "))),
          h("div", { class: "row", style: "flex-wrap:nowrap" },
            h("button", { class: "btn small", onClick: guarded(null, () => decide(e.id, { action: "approve" })) }, t("approve")),
            h("button", { class: "btn secondary small", onClick: guarded(null, async () => { const n = await askText(t("adjust"), t("hours")); if (n === null) return; const r = await askText(t("adjust"), t("reason")); if (r === null) return; await decide(e.id, { action: "adjust", hours: Number(n), reason: r }); }) }, t("adjust")),
            h("button", { class: "btn danger small", onClick: guarded(null, async () => { const r = await askText(t("reject"), t("reason")); if (r !== null) await decide(e.id, { action: "reject", reason: r }); }) }, t("reject")))]),
        t("queue_empty"))));
  }
  await render();
}
