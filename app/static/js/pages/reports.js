// Monthly / quarterly / annual reports for a project, program or the whole portfolio.
import { api, downloadCsv, openReport, saveDocument } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, num, stat, table, today } from "../ui.js";

const EXEC = ["PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"];

export default async function (root, { me }) {
  const isExec = EXEC.includes(me.role);
  const [projects, programs] = await Promise.all([api("GET", "/projects"), isExec ? api("GET", "/programs") : []]);
  const scope = h("select", {}, (isExec ? ["portfolio", "program", "project"] : ["project"]).map(x => h("option", { value: x }, t(`scope_${x}`))));
  const target = h("select");
  const period = h("select", {}, ["month", "quarter", "year"].map(x => h("option", { value: x }, t(`period_${x}`))));
  const anchor = h("input", { type: "date", value: today() });
  const out = h("div");
  const fillTarget = () => {
    const list = scope.value === "program" ? programs.map(g => [g.id, `${g.code} · ${g.name}`]) : scope.value === "project" ? projects.map(p => [p.id, `${p.number} · ${p.name}`]) : [];
    mount(target, list.map(([v, l]) => h("option", { value: v }, l)));
    target.disabled = scope.value === "portfolio";
  };
  scope.addEventListener("change", fillTarget);
  fillTarget();
  const qs = (extra = "") => `scope=${scope.value}${scope.value !== "portfolio" && target.value ? `&id=${target.value}` : ""}&period=${period.value}&anchor=${anchor.value}${extra}`;

  async function preview() {
    mount(out);
    try {
      const r = await api("GET", `/reports/period?${qs()}`);
      const tt = r.totals;
      mount(out, h("div", { class: "card" }, h("h2", {}, `${r.scope.name} · ${r.period.label}`), h("p", { class: "muted small" }, `${r.period.start} → ${r.period.end}`),
        h("div", { class: "grid", style: "margin-bottom:14px" }, stat(t("hours_approved"), `${num(tt.hours)} h`), stat(t("cost_period"), Object.keys(tt.cost).length ? Object.entries(tt.cost).map(([k, v]) => `${num(v, 0)} ${k}`).join(" · ") : "—"),
          stat(t("rep_ms_achieved"), tt.milestones_achieved), stat(t("rep_ms_missed"), tt.milestones_missed), ["RED", "AMBER", "GREEN"].map(k => stat(t(`rag_${k}`), tt.rag_counts[k]))),
        table([t("project"), t("state"), t("rag"), t("progress"), "CPI", "SPI", t("hours_approved"), t("cost_period"), t("rep_ms_achieved"), t("rep_ms_missed"), t("risks"), t("issues")],
          r.rows.map(x => [`${x.number} · ${x.name}`, t(x.state), badge(t(`rag_${x.rag}`), x.rag), x.progress_pct == null ? "—" : `${num(x.progress_pct)}%`, num(x.cpi, 2), num(x.spi, 2), num(x.hours), x.cost == null ? "—" : `${num(x.cost, 0)} ${x.currency}`,
            x.milestones_achieved, x.milestones_missed, x.open_risks, x.open_issues]), t("none"))));
    } catch (e) { mount(out, errorBox(e)); }
  }
  const btn = (label, fn, cls = "secondary") => h("button", { class: `btn ${cls}`, type: "button", onClick: guarded(null, fn) }, label);
  mount(root, h("h1", {}, t("nav_reports")),
    h("div", { class: "card" }, h("div", { class: "row", style: "align-items:end" }, field(t("scope"), scope), field(t("target"), target), field(t("period"), period), field(t("date"), anchor),
      btn(t("preview"), preview, ""), btn(t("export_excel"), () => saveDocument(`/reports/period/xlsx-b64?${qs()}`, "report.xlsx")), btn(t("export_csv"), () => downloadCsv(`/reports/period?${qs("&format=csv")}`, "report.csv")),
      btn(t("print_pdf"), () => openReport(`/reports/period?${qs("&format=html")}`))), h("p", { class: "muted small", style: "margin-top:10px" }, t("print_pdf_note"))), out);
  await preview();
}
