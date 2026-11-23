// My projects (staff view): assigned projects, my activities, hours used against my cap.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, bar, h, mount, num, table } from "../ui.js";

export default async function (root) {
  const rows = await api("GET", "/me/projects");
  mount(root, h("h1", {}, t("nav_mine")),
    rows.length ? null : h("div", { class: "card" }, h("p", { class: "muted" }, t("no_projects"))),
    rows.map(p => h("div", { class: "card" },
      h("h2", {}, h("a", { href: `#/projects/${p.id}` }, `${p.number} · ${p.name}`), " ", badge(t(p.state), "GREY")),
      h("p", { class: "muted" }, `${t("my_hours_cap")}: ${num(p.my_hours)} h`, " ", h("a", { class: "btn small secondary", href: "#/timesheet" }, t("log_time"))),
      table([t("code"), t("activity"), t("planned_h"), t("cap_h"), t("hours"), t("remaining"), ""],
        p.activities.map(a => [a.code, a.name, num(a.planned_hours), num(a.cap), num(a.my_hours), num(a.remaining),
          h("div", { style: "min-width:120px" }, bar(a.cap ? 100 * a.my_hours / a.cap : 0, a.my_hours > a.cap))])))));
}
