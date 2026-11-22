import { api, downloadCsv } from "../api.js";
import { st, t } from "../i18n.js";
import { badge, bar, errorBox, field, guarded, h, mount, num, stat, table } from "../ui.js";

const EXEC = ["PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"];
const rag = (r) => badge(t(`rag_${r}`), r);

export default async function (root, { me, arg }) {
  if (arg) return project(root, Number(arg));
  if (!EXEC.includes(me.role)) {                       // a PM's entry point: own delivery projects
    const list = (await api("GET", "/projects")).filter(p => ["execution", "closing"].includes(p.state));
    return mount(root, h("h1", {}, t("nav_dashboard")), h("div", { class: "card" },
      table([t("number"), t("name"), ""], list.map(p => [p.number, p.name, h("a", { href: `#/dashboard/${p.id}` }, t("open"))]), t("none"))));
  }
  let filter = "";
  async function render() {
    const d = await api("GET", `/dashboards/portfolio${filter ? `?rag=${filter}` : ""}`);
    const risks = await api("GET", "/dashboards/top-risks?limit=5");
    const sel = h("select", { value: filter, onChange: (e) => { filter = e.target.value; render(); } },
      h("option", { value: "" }, t("all")), ["RED", "AMBER", "GREEN", "GREY"].map(x => h("option", { value: x }, t(`rag_${x}`))));
    mount(root, h("h1", {}, `${t("nav_dashboard")} · ${t("portfolio")}`),
      h("p", {}, h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => downloadCsv("/export/portfolio.csv", "portfolio.csv")) }, t("export_csv"))),
      h("div", { class: "grid", style: "margin-bottom:16px" }, ["RED", "AMBER", "GREEN", "GREY"].map(k => stat(t(`rag_${k}`), d.rag_counts[k]))),
      h("div", { class: "card" }, h("div", { class: "row", style: "margin-bottom:10px" }, field(t("filter_rag"), sel)),
        table([t("project"), t("state"), t("rag"), t("progress"), "CPI", "SPI", t("open_alerts"), t("top_alert")],
          d.projects.map(p => [h("a", { href: `#/dashboard/${p.project_id}` }, `${p.number} · ${p.name}`), t(p.state), rag(p.rag),
            p.progress_pct == null ? "—" : `${num(p.progress_pct)}%`, num(p.cpi, 2), num(p.spi, 2),
            h("span", {}, [p.open_alerts.critical ? badge(p.open_alerts.critical, "critical") : null, " ", p.open_alerts.warning ? badge(p.open_alerts.warning, "warning") : null]),
            h("span", { class: "small" }, p.top_alert || "")]), t("none"))),
      h("div", { class: "card" }, h("h2", {}, t("risks")), table([t("project"), t("title"), t("score")], risks.map(r => [`#${r.project_id}`, r.title, badge(r.score, r.score >= 20 ? "critical" : "warning")]), t("none"))));
  }
  await render();
}

async function project(root, pid) {
  let d;
  try { d = await api("GET", `/dashboards/project/${pid}`); } catch (e) { return mount(root, errorBox(e)); }
  const p = d.project, e = d.evm;
  mount(root, h("p", {}, h("a", { href: "#/dashboard" }, `← ${t("nav_dashboard")}`)),
    h("h1", {}, `${p.number} · ${p.name} `, rag(d.rag)),
    d.health_reasons.length ? h("div", { class: d.rag === "RED" ? "err" : "warn" }, h("strong", {}, `${t("why")}: `), h("ul", {}, d.health_reasons.map(r => h("li", {}, `[${st(r.severity)}] ${r.cause}`)))) : null,
    h("div", { class: "grid", style: "margin-bottom:16px" },
      stat(t("progress"), d.progress_pct == null ? "—" : `${num(d.progress_pct)}%`), stat(t("planned"), `${num(d.hours.planned)} h`), stat(t("approved"), `${num(d.hours.approved)} h`), stat(t("pending_approval"), `${num(d.hours.pending_approval)} h`),
      stat(t("risks"), `${d.risks.open}${d.risks.top_score ? ` (${t("max")} ${d.risks.top_score})` : ""}`), stat(t("issues"), `${d.issues.open}${d.issues.critical ? ` · ${d.issues.critical} ${t("critical_short")}` : ""}`)),
    h("div", { class: "card" }, bar(d.progress_pct || 0)),
    e ? h("div", { class: "card" }, h("h2", {}, t("evm")), e.available ? h("div", { class: "grid" }, ["BAC", "PV", "EV", "AC", "CPI", "SPI", "EAC", "VAC"].map(k => stat(k, num(e[k], k === "CPI" || k === "SPI" ? 2 : 0)))) : h("p", { class: "muted" }, `${t("not_available")}: ${e.reason || ""}`),
      (e.warnings || []).length ? h("div", { class: "warn" }, h("ul", {}, e.warnings.map(w => h("li", {}, w)))) : null) : null,
    d.overdue_activities.length ? h("div", { class: "card" }, h("h2", {}, t("overdue")), table([t("activity"), t("planned_end"), t("days_late")], d.overdue_activities.map(a => [a.code, a.planned_end, a.days_late]))) : null,
    h("div", { class: "card" }, h("h2", {}, t("alerts")), table([t("severity"), t("cause"), t("status")], d.alerts.map(a => [badge(st(a.severity), a.severity), a.cause, st(a.status)]), t("none")), h("p", {}, h("a", { href: "#/alerts" }, t("nav_alerts")))));
}
