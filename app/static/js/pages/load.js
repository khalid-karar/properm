import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, bar, field, h, mount, num, stat, table, today } from "../ui.js";

export default async function (root) {
  const wk = h("input", { type: "date", value: today() });
  async function render() {
    const r = await api("GET", `/allocations/load?week_of=${wk.value}`);
    const rows = r.staff.map(s => [h("div", {}, s.full_name || s.staff_id, s.leave_days ? h("div", { class: "muted small" }, `${t("leave_short")}: ${s.leave_days} ${t("days_h")}`) : null, s.by_project && s.by_project.length > 1 ? h("div", { class: "muted small" }, s.by_project.map(b => `${b.project}: ${num(b.hours)} h`).join(" · ")) : null), num(s.capacity), num(s.planned), h("div", {}, num(s.actual), bar(s.capacity ? (s.actual / s.capacity) * 100 : 0, s.actual > s.capacity)), s.over_allocated ? badge(t("over_allocated"), "critical") : ""]);
    mount(root, h("h1", {}, t("load_title")),
      h("div", { class: "card" }, h("div", { class: "row" }, field(t("week_of"), wk)), h("p", { class: "muted" }, `${t("week_of")} ${r.week_start}`)),
      h("div", { class: "grid" }, stat(t("over_allocated"), r.staff.filter(s => s.over_allocated).length), stat(t("staff"), r.staff.length)),
      h("div", { class: "card" }, table([t("staff"), t("capacity"), t("planned"), t("actual"), ""], rows, t("no_load"))));
  }
  wk.addEventListener("change", render);
  await render();
}
