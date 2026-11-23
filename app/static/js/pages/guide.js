// Role guide: what this role can do, with a link for each task.
import { t } from "../i18n.js";
import { h, mount } from "../ui.js";

const TASKS = {"STAFF": [[0, "timesheet"], [1, "timesheet"], [2, "mine"], [3, "todo"], [4, "profile"]], "PM": [[0, "projects"], [1, "projects"], [2, "approvals"], [3, "projects"], [4, "load"], [5, "reports"]], "PMO": [[0, "executive"], [1, "alerts"], [2, "approvals"], [3, "programs"], [4, "audit"], [5, "reports"]], "PROGRAM_MANAGER": [[0, "programs"], [1, "executive"], [2, "reports"], [3, "alerts"]], "DECISION_MAKER": [[0, "executive"], [1, "decisions"], [2, "executive"], [3, "reports"]], "ADMIN": [[0, "admin"], [1, "config"], [2, "audit"], [3, "admin"]]};

export default async function (root, { me }) {
  const items = TASKS[me.role] || [];
  mount(root, h("h1", {}, t("guide_title")), h("p", { class: "muted" }, `${t("guide_intro")} ${me.role}.`),
    h("div", { class: "card" }, h("ul", { class: "guide" }, items.map(([i, page]) =>
      h("li", {}, h("a", { href: `#/${page}` }, t(`g_${me.role}_${i}`)))))));
}
