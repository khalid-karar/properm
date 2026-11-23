// Home: a calm start page for every role. Greeting, what needs attention, and the next useful actions.
import { api } from "../api.js";
import { getLang, t } from "../i18n.js";
import { badge, h, icon, mount, num } from "../ui.js";
import { startTour } from "../tour.js";

const ACTIONS = {
  STAFF: [["timesheet", "act_log_hours", "act_log_hours_d"], ["leave", "act_leave", "act_leave_d"], ["mine", "act_my_projects", "act_my_projects_d"], ["skills", "act_skills", "act_skills_d"]],
  PM: [["projects", "act_new_project", "act_new_project_d"], ["approvals", "act_approve", "act_approve_d"], ["load", "act_team_load", "act_team_load_d"], ["reports", "act_reports", "act_reports_d"]],
  PMO: [["projects", "act_new_project", "act_new_project_d"], ["alerts", "act_alerts", "act_alerts_d"], ["portfolio", "act_portfolio", "act_portfolio_d"], ["reports", "act_reports", "act_reports_d"]],
  PROGRAM_MANAGER: [["programs", "act_programs", "act_programs_d"], ["portfolio", "act_portfolio", "act_portfolio_d"], ["alerts", "act_alerts", "act_alerts_d"], ["reports", "act_reports", "act_reports_d"]],
  DECISION_MAKER: [["decisions", "act_decide", "act_decide_d"], ["executive", "act_exec", "act_exec_d"], ["portfolio", "act_portfolio", "act_portfolio_d"], ["alerts", "act_alerts", "act_alerts_d"]],
  ADMIN: [["admin", "act_users", "act_users_d"], ["config", "act_config", "act_config_d"], ["audit", "act_audit", "act_audit_d"], ["projects", "act_projects", "act_projects_d"]],
};

const tile = (href, ic, big, small, tone = "") => h("a", { class: `tile ${tone}`, href }, h("span", { class: "tile-ic" }, icon(ic)), h("span", { class: "tile-tx" }, h("span", { class: "tile-v" }, big), h("span", { class: "tile-l" }, small)));

export default async function (root, { me }) {
  const hr = new Date().getHours();
  const hello = hr < 12 ? t("good_morning") : hr < 18 ? t("good_afternoon") : t("good_evening");
  const first = (me.full_name || "").split(/\s+/)[0];
  mount(root, h("p", { class: "muted" }, t("loading")));
  const ok = (r) => (r.status === "fulfilled" ? r.value : null);
  const [todo, util, alerts, projects] = (await Promise.allSettled([api("GET", "/me/todo"), api("GET", "/me/utilization"), api("GET", "/alerts"), api("GET", "/projects")])).map(ok);
  const active = (alerts || []).filter(a => a.active && !["closed", "dismissed"].includes(a.status));
  const crit = active.filter(a => a.severity === "critical").length;
  const tiles = [];
  if (me.role === "STAFF" || me.role === "PM") if (util) tiles.push(tile("#/timesheet", "timesheet", `${num(util.submitted + util.approved)} / ${num(util.capacity, 0)}`, t("hm_hours_week"), util.utilization_pct > 100 ? "amber" : ""));
  if (todo) tiles.push(tile("#/todo", "todo", todo.total, t("hm_todo"), todo.total ? "amber" : "green"));
  if (todo && ["PM", "PMO", "ADMIN", "STAFF"].includes(me.role) && todo.approvals_waiting) tiles.push(tile("#/approvals", "approvals", todo.approvals_waiting, t("hm_approvals"), "amber"));
  if (alerts && me.role !== "STAFF") tiles.push(tile("#/alerts", "alerts", active.length, crit ? `${t("hm_alerts")} · ${crit} ${t("hm_critical")}` : t("hm_alerts"), crit ? "red" : active.length ? "amber" : "green"));
  if (projects) tiles.push(tile(me.role === "STAFF" ? "#/mine" : "#/projects", "projects", projects.length, t("hm_projects")));
  const needs = [];
  if (todo) {
    if (todo.week_due) needs.push([t("hm_week_due"), "#/timesheet"]);
    if (todo.rejected_entries.length) needs.push([`${todo.rejected_entries.length} ${t("hm_rejected")}`, "#/todo"]);
    if (todo.approvals_waiting) needs.push([`${todo.approvals_waiting} ${t("hm_approvals")}`, "#/approvals"]);
    if (todo.leave_waiting) needs.push([`${todo.leave_waiting} ${t("hm_leave")}`, "#/leave"]);
    for (const a of todo.alerts.slice(0, 3)) needs.push([a.title, "#/alerts"]);
  }
  mount(root,
    h("div", { class: "welcome" },
      h("div", {}, h("h1", {}, `${hello}، ${first}`.replace("،", getLang() === "ar" ? "،" : ",")), h("p", { class: "muted" }, `${new Date().toLocaleDateString(getLang() === "ar" ? "ar-SA" : "en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })} · `, badge(me.role, "gold"))),
      h("button", { class: "btn gold ask-btn", type: "button", onClick: () => window.dispatchEvent(new CustomEvent("properm-ask", { detail: t("asst_q_today") })) }, icon("spark"), " ", t("asst_ask_me"))),
    h("div", { class: "tiles" }, tiles),
    h("div", { class: "grid2" },
      h("div", { class: "card" }, h("h2", {}, t("hm_needs")),
        needs.length ? h("ul", { class: "needs" }, needs.map(([txt, href]) => h("li", {}, h("a", { href }, txt)))) : h("div", { class: "allgood" }, icon("approvals"), h("span", {}, t("hm_all_good")))),
      h("div", { class: "card" }, h("h2", {}, t("hm_next")),
        h("div", { class: "actions" }, (ACTIONS[me.role] || []).map(([page, k, d]) => h("a", { class: "action", href: `#/${page}` }, h("span", { class: "tile-ic" }, icon(page)), h("span", {}, h("strong", {}, t(k)), h("small", {}, t(d)))))))));
  root.append(h("p", { class: "muted small" }, h("button", { class: "btn secondary small", type: "button", id: "tour-btn", onClick: () => startTour(me) }, t("tour_replay"))));
}
