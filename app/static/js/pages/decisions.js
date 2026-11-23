// Decision queue: everything waiting on this person, in one list.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, h, mount, num, table } from "../ui.js";

export default async function (root) {
  const d = await api("GET", "/dashboards/decisions");
  const link = (pid, text) => h("a", { href: `#/projects/${pid}` }, text);
  mount(root, h("h1", {}, `${t("nav_decisions")} `, d.total ? badge(d.total, "critical") : null),
    d.total ? null : h("div", { class: "card" }, h("p", { class: "muted" }, t("nothing_pending"))),
    d.changes.length ? h("div", { class: "card" }, h("h2", {}, t("changes")),
      table([t("project"), t("change_type"), t("description"), t("cost_delta"), t("schedule_days"), ""], d.changes.map(c => [c.project, t(`ct_${c.type}`), c.title, num(c.cost_delta, 0), num(c.schedule_days, 0), link(c.project_id, t("open"))]))) : null,
    d.costs.length ? h("div", { class: "card" }, h("h2", {}, t("cost_approvals")),
      table([t("project"), t("category"), t("amount"), ""], d.costs.map(c => [c.project, c.title, `${num(c.amount, 0)} ${c.currency}`, link(c.project_id, t("open"))]))) : null,
    d.alerts.length ? h("div", { class: "card" }, h("h2", {}, t("critical_alerts")),
      table([t("project"), t("cause"), ""], d.alerts.map(a => [a.project, a.title, h("a", { href: "#/alerts" }, t("open"))]))) : null);
}
