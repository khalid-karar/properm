// My to-do: everything that is waiting on me, across the system.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, guarded, h, mount, num, table, toast } from "../ui.js";

export default async function (root, { me }) {
  async function render() {
    const [d, cal] = await Promise.all([api("GET", "/me/todo"), api("GET", "/me/calendar")]);
    const link = (pid, text) => h("a", { href: `#/projects/${pid}` }, text);
    mount(root, h("h1", {}, `${t("nav_todo")} `, d.total ? badge(d.total, "critical") : null),
      d.total ? null : h("div", { class: "card" }, h("p", { class: "muted" }, t("nothing_pending"))),
      d.week_due ? h("div", { class: "card" }, h("h2", {}, t("week_due_title")), h("p", {}, `${t("week_of")} ${d.week_due.week_start}: ${num(d.week_due.total)} h` + (d.week_due.missing_days ? ` · ${t("missing_days_h")}: ${d.week_due.missing_days}` : ""), " ", h("a", { class: "btn small", href: "#/timesheet" }, t("nav_timesheet")))) : null,
      d.leave_waiting ? h("div", { class: "card" }, h("h2", {}, t("leave_requests")), h("p", {}, `${d.leave_waiting} ${t("leave_waiting_txt")} `, h("a", { href: "#/leave" }, t("open")))) : null,
      d.approvals_waiting ? h("div", { class: "card" }, h("h2", {}, t("queue")), h("p", {}, `${d.approvals_waiting} ${t("entries_waiting")} `, h("a", { href: "#/approvals" }, t("open")))) : null,
      d.rejected_entries.length ? h("div", { class: "card" }, h("h2", {}, t("rejected_entries")), h("p", { class: "muted small" }, t("rejected_note")),
        table([t("date"), t("hours"), t("reason"), ""], d.rejected_entries.map(e => [e.entry_date, num(e.hours), e.decision_reason || "—", h("span", { class: "row", style: "gap:6px" },
          h("a", { class: "btn small secondary", href: "#/timesheet" }, t("nav_timesheet")),
          h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/timesheets/${e.id}`); toast(t("withdrawn")); await render(); }) }, t("withdraw")))]))) : null,
      d.alerts.length ? h("div", { class: "card" }, h("h2", {}, t("assigned_alerts")), table([t("project"), t("cause"), t("severity"), ""], d.alerts.map(a => [a.project, a.title, badge(a.severity, a.severity), h("a", { href: "#/alerts" }, t("open"))]))) : null,
      (d.actions || []).length ? h("div", { class: "card" }, h("h2", {}, t("my_actions")), table([t("project"), t("title"), t("due_date"), ""], d.actions.map(a => [a.project, a.title, a.due_date ? h("span", { class: a.overdue ? "neg" : "" }, a.due_date) : "—",
        h("span", { class: "row", style: "gap:6px" }, link(a.project_id, t("open")), h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { await api("PATCH", `/projects/${a.project_id}/actions/${a.id}`, { status: "done" }); toast(t("saved")); await render(); }) }, t("mark_done")))]))) : null,
      d.risks.length ? h("div", { class: "card" }, h("h2", {}, t("my_risks")), table([t("project"), t("title"), t("score"), ""], d.risks.map(r => [r.project, r.title, badge(r.score, r.score >= 20 ? "critical" : "warning"), link(r.project_id, t("open"))]))) : null,
      d.issues.length ? h("div", { class: "card" }, h("h2", {}, t("my_issues")), table([t("project"), t("title"), t("severity"), ""], d.issues.map(i => [i.project, i.title, i.severity, link(i.project_id, t("open"))]))) : null);
    root.append(h("div", { class: "card", id: "coming-up" }, h("h2", {}, t("coming_up")), cal.length ? table([t("date"), t("type"), t("title"), ""],
      cal.map(x => [h("span", { class: x.overdue ? "neg" : "" }, x.date), t(`ck_${x.kind}`), x.title, x.link ? h("a", { href: x.link }, t("open")) : ""])) : h("p", { class: "muted" }, t("none"))));
  }
  await render();
}
