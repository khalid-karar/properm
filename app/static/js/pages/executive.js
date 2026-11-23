// Executive summary: one screen for decision makers.
import { api } from "../api.js";
import { ragStack } from "../charts.js";
import { t } from "../i18n.js";
import { badge, h, mount, num, stat, table } from "../ui.js";

export default async function (root) {
  const d = await api("GET", "/dashboards/executive");
  const e = d.evm, money = (v) => (v == null ? "—" : `${Number(v).toLocaleString()} ${e.currency}`);
  mount(root, h("h1", {}, t("nav_executive")), h("p", { class: "muted" }, `${t("as_of")} ${d.as_of}`),
    h("div", { class: "grid", style: "margin-bottom:16px" }, stat(t("projects"), d.projects), ["RED", "AMBER", "GREEN"].map(k => stat(t(`rag_${k}`), d.rag_counts[k])),
      stat(t("pending_decisions"), h("a", { href: "#/decisions" }, d.pending_decisions)), stat(t("overdue_milestones"), d.overdue_milestones)),
    h("div", { class: "grid2" },
      h("div", { class: "card" }, h("h2", {}, t("portfolio_cost")), h("div", { class: "grid" }, stat("BAC", money(e.BAC)), stat("EV", money(e.EV)), stat("AC", money(e.AC)), stat("CPI", e.CPI == null ? "—" : num(e.CPI, 2))),
        e.excluded_currencies.length ? h("p", { class: "muted small" }, `${t("excluded_ccy")}: ${e.excluded_currencies.join(", ")}`) : null),
      h("div", { class: "card" }, h("h2", {}, t("rag_history")), d.rag_history.length > 1 ? ragStack(d.rag_history) : h("p", { class: "muted" }, t("trend_building")))),
    h("div", { class: "card" }, h("h2", {}, t("attention")),
      table([t("project"), t("rag"), t("top_alert")], d.attention.map(x => [h("a", { href: `#/dashboard/${x.project_id}` }, `${x.number} · ${x.name}`), badge(t(`rag_${x.rag}`), x.rag), h("span", { class: "small" }, x.top_alert || "")]), t("none"))),
    h("div", { class: "card" }, h("h2", {}, t("top_risks")), table([t("project"), t("title"), t("score")], d.top_risks.map(r => [h("a", { href: `#/dashboard/${r.project_id}` }, r.project), r.title, badge(r.score, r.score >= 20 ? "critical" : "warning")]), t("none"))));
}
