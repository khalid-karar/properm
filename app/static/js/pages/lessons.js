// Lessons library: lessons from every project, searchable.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, field, h, mount, table } from "../ui.js";
import { LESSON_CATS } from "./control.js";

export default async function (root) {
  const q = h("input", { type: "search", placeholder: t("search_ph") }), cat = h("select", {}, h("option", { value: "" }, t("all")), LESSON_CATS.map(c => h("option", { value: c }, t(`lc_${c}`))));
  const imp = h("select", {}, h("option", { value: "" }, t("all")), ["negative", "positive"].map(x => h("option", { value: x }, t(`li_${x}`))));
  const out = h("div");
  async function load() {
    const p = new URLSearchParams(); if (q.value.trim()) p.set("q", q.value.trim()); if (cat.value) p.set("category", cat.value); if (imp.value) p.set("impact", imp.value);
    const d = await api("GET", `/lessons?${p}`);
    mount(out, table([t("project"), t("category"), t("impact_h"), t("what_happened"), t("recommendation")],
      d.lessons.map(x => [h("a", { href: `#/projects/${x.project_id}` }, x.project || ""), t(`lc_${x.category}`), badge(t(`li_${x.impact}`), x.impact === "positive" ? "GREEN" : "AMBER"), x.what_happened, x.recommendation]), t("none")));
  }
  let timer; q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 300); });
  cat.addEventListener("change", load); imp.addEventListener("change", load);
  mount(root, h("h1", {}, t("nav_lessons")), h("p", { class: "muted" }, t("lessons_lib_note")),
    h("div", { class: "card" }, h("div", { class: "row" }, field(t("search"), q), field(t("category"), cat), field(t("impact_h"), imp))), h("div", { class: "card" }, out));
  await load();
}
