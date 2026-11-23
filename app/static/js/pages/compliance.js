// Compliance: requirement library (PMO) and portfolio overview.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, h, mount, table } from "../ui.js";
import { registerCard } from "../register.js";

export default async function (root, { me }) {
  const edit = ["PMO", "ADMIN"].includes(me.role), view = ["PMO", "ADMIN", "DECISION_MAKER", "PROGRAM_MANAGER"].includes(me.role);
  async function render() {
    const [lib, ov] = await Promise.all([api("GET", "/compliance-library"), view ? api("GET", "/compliance/overview") : null]);
    const pct = (b) => b == null ? "—" : badge(`${b}%`, b >= 90 ? "GREEN" : b >= 60 ? "AMBER" : "RED");
    const libCard = registerCard({ id: "library-card", title: t("compliance_library"), note: t("library_note"), base: "/compliance-library", rows: lib, canManage: edit, render, remove: false,
      fields: [{ k: "code", label: t("code"), req: true }, { k: "framework", label: t("framework"), req: true }, { k: "title", label: t("title"), req: true }, { k: "description", label: t("description"), type: "textarea" }],
      columns: [{ h: t("framework"), f: r => r.framework }, { h: t("code"), f: r => r.code }, { h: t("title"), f: r => r.title }, { h: t("active"), f: r => r.active ? t("yes") : t("no") }] });
    mount(root, h("h1", {}, t("nav_compliance")),
      ov ? h("div", { class: "card", id: "compliance-overview" }, h("h2", {}, t("compliance_overview")),
        table([t("framework"), t("total"), t("st_compliant"), t("st_open"), t("st_exception"), t("overdue")], ov.frameworks.map(f => [f.framework, f.total, f.compliant, f.open, f.exception, f.overdue ? h("span", { class: "neg" }, f.overdue) : 0]), t("none")),
        h("h3", {}, t("projects")),
        table([t("project"), t("compliance"), t("st_open"), t("st_exception"), t("overdue")], ov.projects.map(b => [h("a", { href: `#/projects/${b.id}` }, `${b.number} · ${b.name}`), pct(b.pct), b.open, b.exception, b.overdue || 0]), t("none")),
        ov.projects_without_any.length ? h("p", { class: "muted small" }, `${t("no_compliance_rows")}: ${ov.projects_without_any.map(x => x.number).join(", ")}`) : null) : null,
      libCard);
  }
  await render();
}
