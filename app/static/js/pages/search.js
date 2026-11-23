// Search results across projects, people, risks, issues, documents, actions, lessons, programs, proposals.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { h, mount } from "../ui.js";

const GROUPS = ["projects", "programs", "proposals", "people", "risks", "issues", "actions", "documents", "lessons"];

export default async function (root, { arg }) {
  const q = decodeURIComponent(arg || "");
  const box = h("input", { type: "search", value: q, style: "min-width:280px", id: "search-page-box" });
  const go = () => { if (box.value.trim().length >= 2) location.hash = `#/search/${encodeURIComponent(box.value.trim())}`; };
  box.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  if (q.length < 2) { mount(root, h("h1", {}, t("search")), h("div", { class: "card" }, box)); return; }
  const r = await api("GET", `/search?q=${encodeURIComponent(q)}`);
  mount(root, h("h1", {}, `${t("search")}: “${q}”`), h("div", { class: "card" }, h("div", { class: "row" }, box, h("button", { class: "btn", type: "button", onClick: go }, t("search")))),
    r.total ? null : h("div", { class: "card" }, h("p", { class: "muted" }, t("no_results"))),
    GROUPS.filter(g => (r[g] || []).length).map(g => h("div", { class: "card search-group" }, h("h2", {}, `${t(`sg_${g}`)} (${r[g].length})`),
      h("ul", { class: "declog" }, r[g].map(x => h("li", {}, x.link ? h("a", { href: x.link }, x.title) : h("strong", {}, x.title), x.sub ? h("span", { class: "muted small" }, ` · ${x.sub}`) : null))))));
}
