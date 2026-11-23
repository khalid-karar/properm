// PMO method library: project templates.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, modal, mount, table, toast } from "../ui.js";

const EXAMPLE = { activities: [{ code: "REQ", name: "Requirements", planned_hours: 80, start_offset_days: 0, duration_days: 20 }, { code: "BLD", name: "Build", planned_hours: 200, start_offset_days: 20, duration_days: 60, after: "REQ" }],
  milestones: [{ name: "Requirements signed", offset_days: 20 }], kpis: [{ name: "Defects at go-live", unit: "#", target: 10, higher_is_better: false }], risks: [{ title: "Unclear scope", probability: 3, impact: 4 }] };

export default async function (root) {
  async function render() {
    const [list, projects] = await Promise.all([api("GET", "/templates"), api("GET", "/projects")]);
    const view = (x) => modal({ title: `${x.code} · ${x.name}`, body: h("div", { class: "prop" }, x.description ? h("p", {}, x.description) : null,
      h("h3", {}, t("activities")), table([t("code"), t("name"), t("planned_hours"), t("start_day"), t("duration_days"), t("depends_on")], x.data.activities.map(a => [a.code, a.name, a.planned_hours ?? "—", a.start_offset_days, a.duration_days, a.after || ""]), t("none")),
      h("h3", {}, t("milestones")), table([t("name"), t("start_day")], x.data.milestones.map(m => [m.name, m.offset_days]), t("none")),
      h("h3", {}, t("kpis")), table([t("name"), t("target")], x.data.kpis.map(k => [`${k.name}${k.unit ? ` (${k.unit})` : ""}`, k.target]), t("none")),
      h("h3", {}, t("risks")), table([t("title"), t("score")], x.data.risks.map(r => [r.title, r.probability * r.impact]), t("none"))),
      actions: [{ label: t("close"), class: "secondary", onClick: (c) => c() }] });
    const fp = { proj: h("select", {}, projects.map(p => h("option", { value: p.id }, `${p.number} · ${p.name}`))), code: h("input", { style: "width:120px" }), name: h("input") }, ferr = h("div");
    const nt = { code: h("input", { style: "width:120px" }), name: h("input"), desc: h("input", { style: "min-width:260px" }), json: h("textarea", { rows: 10, style: "font-family:monospace;font-size:12px" }, JSON.stringify(EXAMPLE, null, 2)) }, nerr = h("div");
    mount(root, h("h1", {}, t("nav_templates")), h("p", { class: "muted" }, t("templates_note")),
      h("div", { class: "card" }, table([t("code"), t("name"), t("activities"), t("milestones"), t("kpis"), t("risks"), t("status"), ""], list.map(x => [x.code, x.name, x.counts.activities, x.counts.milestones, x.counts.kpis, x.counts.risks,
        badge(x.active ? t("active") : t("inactive"), x.active ? "GREEN" : "GREY"),
        h("span", { class: "row", style: "gap:6px;flex-wrap:nowrap" }, h("button", { class: "btn small secondary", type: "button", onClick: () => view(x) }, t("open")),
          h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("PATCH", `/templates/${x.id}`, { active: !x.active }); await render(); }) }, x.active ? t("deactivate") : t("activate")))]), t("none"))),
      h("div", { class: "card", id: "tpl-from-project" }, h("h2", {}, t("tpl_from_project")), h("p", { class: "muted small" }, t("tpl_from_project_note")),
        h("div", { class: "row" }, field(t("project"), fp.proj), field(t("code"), fp.code), field(t("name"), fp.name),
          h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(ferr); try { await api("POST", `/templates/from-project/${fp.proj.value}`, { code: fp.code.value.trim(), name: fp.name.value.trim() }); toast(t("saved")); await render(); } catch (e) { mount(ferr, errorBox(e)); } }) }, t("create"))), ferr),
      h("div", { class: "card" }, h("h2", {}, t("tpl_new")), h("p", { class: "muted small" }, t("tpl_new_note")),
        h("div", { class: "row" }, field(t("code"), nt.code), field(t("name"), nt.name), field(t("description"), nt.desc)), nt.json,
        h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(nerr); let data; try { data = JSON.parse(nt.json.value); } catch { mount(nerr, errorBox(new Error(t("tpl_bad_json")))); return; }
          try { await api("POST", "/templates", { code: nt.code.value.trim(), name: nt.name.value.trim(), description: nt.desc.value.trim() || null, data }); toast(t("saved")); await render(); } catch (e) { mount(nerr, errorBox(e)); } }) }, t("create")), nerr));
  }
  await render();
}
