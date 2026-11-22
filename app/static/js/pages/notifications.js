import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, table, toast } from "../ui.js";

export default async function (root, { me }) {
  const canSchedule = me.role !== "STAFF";
  const projects = canSchedule ? await api("GET", "/projects") : [];
  async function render() {
    const list = await api("GET", "/notifications");
    const scheds = canSchedule ? await api("GET", "/reports/schedules") : [];
    const kind = h("select", {}, me.role !== "PM" ? h("option", { value: "portfolio" }, t("portfolio_report")) : null, h("option", { value: "project" }, t("project_report")));
    const proj = h("select", {}, projects.map(p => h("option", { value: p.id }, `${p.number} · ${p.name}`)));
    const freq = h("select", {}, h("option", { value: "weekly" }, t("weekly")), h("option", { value: "monthly" }, t("monthly")));
    const err = h("div"), add = h("button", { class: "btn", type: "button" }, t("add"));
    add.addEventListener("click", guarded(add, async () => {
      mount(err);
      try { await api("POST", "/reports/schedules", { kind: kind.value, frequency: freq.value, project_id: kind.value === "project" ? Number(proj.value) : null }); toast(t("saved")); await render(); }
      catch (e) { mount(err, errorBox(e)); }
    }));
    const pname = (id) => { const p = projects.find(x => x.id === id); return p ? p.number : "—"; };
    mount(root, h("h1", {}, t("notifications")),
      h("div", { class: "card" },
        h("div", { class: "row" }, h("button", { class: "btn secondary small", onClick: guarded(null, async () => { await api("POST", "/notifications/read-all"); await render(); window.dispatchEvent(new Event("properm-notif")); }) }, t("mark_all_read"))),
        table(["", t("notifications"), t("date")], list.map(n => [n.read ? "" : badge("●", "gold"),
          h("div", {}, n.link ? h("a", { href: n.link, onClick: () => api("POST", `/notifications/${n.id}/read`).then(() => window.dispatchEvent(new Event("properm-notif"))) }, n.title) : n.title,
            n.body ? h("div", { class: "muted", style: "white-space:pre-line" }, n.body) : null), String(n.created_at).slice(0, 16).replace("T", " ")]), t("none"))),
      canSchedule ? h("div", { class: "card" }, h("h2", {}, t("scheduled_reports")),
        table([t("report"), t("frequency"), t("last_run"), ""], scheds.map(s => [s.kind === "portfolio" ? t("portfolio_report") : `${t("project_report")} ${pname(s.project_id)}`, t(s.frequency), s.last_run_on || "—",
          h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/reports/schedules/${s.id}`); await render(); }) }, t("remove"))]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("report"), kind), field(t("project"), proj), field(t("frequency"), freq), add), err,
        ["PMO", "ADMIN"].includes(me.role) ? h("p", {}, h("button", { class: "btn gold small", onClick: guarded(null, async () => { const r = await api("POST", "/reports/run-due"); toast(`${t("reports_sent")}: ${r.sent}`); await render(); }) }, t("run_due_now"))) : null) : null);
  }
  await render();
}
