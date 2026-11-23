// Strategic objectives register and coverage view.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, h, mount } from "../ui.js";
import { registerCard } from "../register.js";

export default async function (root, { me }) {
  const edit = ["PMO", "ADMIN", "DECISION_MAKER"].includes(me.role);
  async function render() {
    const [objs, cov, dir] = await Promise.all([api("GET", "/objectives"), api("GET", "/objectives/coverage"), me.role === "STAFF" ? [] : api("GET", "/directory").catch(() => [])]);
    const link = (x) => h("a", { href: `#/projects/${x.id}`, style: "margin-inline-end:8px" }, x.number);
    const uncovered = new Set(cov.uncovered);
    const card = registerCard({ id: "objectives-card", title: t("nav_strategy"), note: t("strategy_note"), base: "/objectives", rows: objs, canManage: edit, render, dir, remove: false,
      fields: [{ k: "code", label: t("code"), req: true }, { k: "name", label: t("name"), req: true }, { k: "horizon", label: t("horizon") }, { k: "owner_id", label: t("owner"), type: "user" },
        { k: "description", label: t("description"), type: "textarea" }, { k: "active", label: t("active"), type: "select", options: [["true", t("yes")], ["false", t("no")]], def: "true" }].map(f => f),
      columns: [{ h: t("code"), f: o => o.code }, { h: t("name"), f: o => h("span", {}, o.name, o.active ? null : badge(t("inactive"), "GREY")) }, { h: t("horizon"), f: o => o.horizon || "—" }, { h: t("owner"), f: o => o.owner || "—" },
        { h: t("projects"), f: o => o.projects.length || o.delivered.length ? h("span", {}, o.projects.map(link), o.delivered.length ? h("span", { class: "muted small" }, `+${o.delivered.length} ${t("delivered")}`) : null) : (uncovered.has(o.id) ? badge(t("no_project"), "RED") : "—") },
        { h: t("nav_proposals"), f: o => o.proposals.map(x => x.number).join(", ") || "—" }] });
    mount(root, h("h1", {}, t("nav_strategy")),
      h("div", { class: "stats" }, h("div", { class: `stat ${cov.uncovered.length ? "red" : "green"}` }, h("div", { class: "v" }, cov.uncovered.length), h("div", { class: "l" }, t("uncovered_objectives"))),
        h("div", { class: `stat ${cov.projects_without_objective.length ? "amber" : "green"}` }, h("div", { class: "v" }, cov.projects_without_objective.length), h("div", { class: "l" }, t("projects_no_objective")))),
      card,
      cov.projects_without_objective.length ? h("div", { class: "card", id: "orphans-card" }, h("h2", {}, t("projects_no_objective")), h("p", { class: "muted small" }, t("orphans_note")),
        h("ul", {}, cov.projects_without_objective.map(x => h("li", {}, h("a", { href: `#/projects/${x.id}` }, `${x.number} · ${x.name}`), " ", badge(t(x.state), "gold"))))) : null);
  }
  await render();
}
