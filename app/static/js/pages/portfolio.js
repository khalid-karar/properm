// Portfolio: ranked priorities (projects and proposals), 12-week capacity plan, governance compliance per PM.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, bar, errorBox, field, guarded, h, modal, mount, num, table, toast } from "../ui.js";

const RAG = { green: "GREEN", amber: "AMBER", red: "RED" };

export default async function (root, { me }) {
  const canScore = ["PMO", "ADMIN", "DECISION_MAKER"].includes(me.role);
  const canComp = ["PMO", "ADMIN", "PROGRAM_MANAGER"].includes(me.role);
  let group = "department";

  const scoreModal = (r, render) => {
    const sel = (v) => h("select", {}, [1, 2, 3, 4, 5].map(n => h("option", { value: n, selected: n === (v || 3) }, String(n))));
    const f = { fit: sel(r.strategic_fit), val: sel(r.value), urg: sel(r.urgency), risk: sel(r.risk_level) }, err = h("div");
    modal({ title: `${t("set_score")}: ${r.number}`, body: h("div", {}, err, h("div", { class: "row" }, field(t("strategic_fit"), f.fit), field(t("value_score"), f.val), field(t("urgency"), f.urg), field(t("risk_level"), f.risk)), h("p", { class: "muted small" }, t("scoring_note"))),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("save"), onClick: async (c) => {
        try { await api("PUT", `/portfolio/scores/${r.id}`, { strategic_fit: Number(f.fit.value), value: Number(f.val.value), urgency: Number(f.urg.value), risk_level: Number(f.risk.value) }); c(); toast(t("saved")); await render(); }
        catch (e) { mount(err, errorBox(e)); } } }] });
  };

  async function render() {
    const [pri, cap, comp] = await Promise.all([api("GET", "/portfolio/priorities"), api("GET", `/portfolio/capacity?group=${group}`), canComp ? api("GET", "/portfolio/compliance") : null]);
    const gsel = h("select", { onChange: (e) => { group = e.target.value; render(); } }, ["department", "grade", "person"].map(g => h("option", { value: g, selected: g === group }, t(`grp_${g}`))));
    const cell = (x) => {
      const cls = x.load_pct == null ? (x.demand ? "cp-r" : "") : x.load_pct > 100 ? "cp-r" : x.load_pct >= 85 ? "cp-a" : x.demand ? "cp-g" : "";
      return h("td", { class: `cp ${cls}`, title: `${t("demand")} ${num(x.demand)} / ${t("supply")} ${num(x.supply)} h` }, x.load_pct == null ? (x.demand ? "!" : "—") : `${x.load_pct}%`);
    };
    const wkLabel = (w) => w.slice(5);
    const capTable = h("div", { style: "overflow-x:auto" }, h("table", { class: "heat" },
      h("thead", {}, h("tr", {}, h("th", {}, t(`grp_${group}`)), cap.weeks.map(w => h("th", {}, wkLabel(w))))),
      h("tbody", {}, cap.groups.map(g => h("tr", {}, h("td", {}, `${g.group}`, h("span", { class: "muted small" }, ` (${g.people})`)), g.weeks.map(cell))),
        h("tr", { class: "tot" }, h("td", {}, h("strong", {}, t("total"))), cap.totals.map(x => cell({ ...x, load_pct: x.supply ? Math.round(100 * x.demand / x.supply) : null }))))));
    mount(root, h("h1", {}, t("nav_portfolio")),
      h("div", { class: "card", id: "priorities" }, h("h2", {}, t("priorities")), h("p", { class: "muted small" }, t("priorities_note")),
        table(["#", t("number"), t("name"), t("type"), t("state"), "RAG", t("score"), t("budget"), "CPI", canScore ? "" : null].filter(x => x !== null),
          pri.map(r => [r.rank || "—", r.kind === "project" ? h("a", { href: `#/projects/${r.id}` }, r.number) : h("a", { href: "#/proposals" }, r.number), r.name,
            r.kind === "project" ? t("project") : t("proposal"), r.kind === "project" ? t(r.state) : t(`ps_${r.state}`), r.rag ? badge(t(`rag_${r.rag}`), r.rag) : "",
            r.score == null ? h("span", { class: "muted" }, t("not_scored")) : h("div", { style: "min-width:80px" }, `${r.score}`, bar(r.score)),
            r.budget == null ? "—" : `${num(r.budget, 0)} ${r.currency}`, r.cpi == null ? "—" : num(r.cpi, 2),
            ...(canScore ? [r.kind === "project" ? h("button", { class: "btn small secondary", type: "button", onClick: () => scoreModal(r, render) }, t("set_score")) : ""] : [])]), t("none"))),
      h("div", { class: "card", id: "capacity" }, h("h2", {}, t("capacity_plan")), h("p", { class: "muted small" }, t("capacity_note")),
        h("div", { class: "row" }, field(t("group_by"), gsel)), capTable,
        cap.over_allocated.length ? [h("h3", {}, t("over_allocated")), table([t("staff"), t("week_of"), t("demand"), t("supply")], cap.over_allocated.slice(0, 20).map(o => [o.user, o.week_start, num(o.demand), num(o.supply)]))] : null),
      comp ? h("div", { class: "card", id: "compliance" }, h("h2", {}, `${t("compliance")} · ${t("week_of")} ${comp.week_start}`), h("p", { class: "muted small" }, t("compliance_note")),
        table([t("manager"), t("projects"), t("missing_reports"), t("stale_progress"), t("risks_unreviewed"), t("overdue_actions"), t("approvals_3d"), t("team_weeks_missing"), ""],
          comp.managers.map(r => [r.pm, r.projects, r.missing_reports.length ? h("span", { class: "neg" }, r.missing_reports.join(", ")) : "0", r.stale_progress, r.risks_unreviewed, r.overdue_actions, r.approvals_waiting_3d, r.team_weeks_missing,
            badge(t(`rag_${RAG[r.rating]}`), RAG[r.rating])]), t("none"))) : null);
  }
  await render();
}
