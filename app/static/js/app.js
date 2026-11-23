import { api, session } from "./api.js";
import { applyDir, getLang, setLang, t } from "./i18n.js";
import { clear, errorBox, h, icon, mount } from "./ui.js";

applyDir();
const app = document.getElementById("app");
let me = null;

const NAV = {
  STAFF: ["todo", "timesheet", "leave", "mine", "approvals", "projects", "alerts", "guide"],
  PM: ["todo", "timesheet", "leave", "approvals", "projects", "load", "dashboard", "decisions", "proposals", "reports", "lessons", "alerts", "guide"],
  PMO: ["todo", "timesheet", "leave", "approvals", "projects", "load", "executive", "portfolio", "dashboard", "decisions", "proposals", "programs", "reports", "lessons", "templates", "alerts", "audit", "guide"],
  ADMIN: ["todo", "timesheet", "leave", "approvals", "projects", "load", "executive", "portfolio", "dashboard", "decisions", "proposals", "programs", "reports", "lessons", "templates", "alerts", "audit", "config", "admin", "guide"],
  DECISION_MAKER: ["todo", "executive", "portfolio", "leave", "projects", "load", "dashboard", "decisions", "proposals", "programs", "reports", "lessons", "alerts", "guide"],
  PROGRAM_MANAGER: ["todo", "executive", "portfolio", "leave", "projects", "load", "dashboard", "decisions", "proposals", "programs", "reports", "lessons", "alerts", "guide"],
};
const HOME = { STAFF: "timesheet", PM: "projects", DECISION_MAKER: "executive" };
export const homeFor = (role) => HOME[role] || "dashboard";

async function route() {
  const [name = "", arg] = location.hash.replace(/^#\//, "").split("/");
  const s = session.get();
  if (!s) {
    if (name !== "login") { location.hash = "#/login"; return; }
    const mod = await import("./pages/login.js");
    mount(app); mod.default(app);
    return;
  }
  if (!me) { try { me = await api("GET", "/me"); } catch { return; } }
  const allowed = NAV[me.role] || [];
  const home = me.home_page && (NAV[me.role] || []).includes(me.home_page) ? me.home_page : homeFor(me.role);
  const page = name || home;
  if (page === "login") { location.hash = `#/${home}`; return; }
  if (me.must_change_password && page !== "profile") { location.hash = "#/profile"; return; }
  if (!allowed.includes(page) && page !== "notifications" && page !== "profile" && page !== "search" && !(page === "decisions" && me.is_ccb)) { location.hash = `#/${home}`; return; }

  const main = h("main", {}, h("p", { class: "muted" }, t("loading")));
  document.body.classList.remove("nav-open");
  mount(app, shell(page, main));
  try {
    const mod = await import(`./pages/${page}.js`);
    await mod.default(main, { me, arg, nav: NAV[me.role] || [] });
    setTimeout(refreshBell, 200);
  } catch (e) {
    mount(main, errorBox(e));
  }
}

const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("");

function shell(active, main) {
  const side = h("aside", { class: "side" },
    h("div", { class: "brand" }, h("span", { class: "logo" }, "P"), t("app")),
    h("nav", { "aria-label": "Main" }, (NAV[me.role] || []).map(n =>
      h("a", { href: `#/${n}`, class: n === active ? "active" : "" }, icon(n), t(`nav_${n}`)))),
    h("div", { class: "side-foot" }, "Smart PMO"));
  const top = h("header", { class: "top" },
    h("button", { type: "button", class: "iconbtn menu-btn", "aria-label": "Menu", onClick: () => document.body.classList.toggle("nav-open") }, icon("menu")),
    h("input", { type: "search", class: "topsearch", id: "topsearch", placeholder: t("search_all_ph"), "aria-label": t("search"),
      onKeydown: (e) => { const v = e.target.value.trim(); if (e.key === "Enter" && v.length >= 2) location.hash = `#/search/${encodeURIComponent(v)}`; } }),
    h("span", { class: "spacer" }),
    h("a", { href: "#/notifications", class: "bell", id: "bell", "aria-label": t("notifications"), title: t("notifications") }, icon("bell"), h("span", { class: "bellcount" })),
    h("button", { type: "button", class: "btn-ghost", onClick: () => { setLang(getLang() === "en" ? "ar" : "en"); route(); } }, getLang() === "en" ? "العربية" : "English"),
    h("a", { class: "who", href: "#/profile", title: t("nav_profile") }, h("span", { class: "avatar" }, initials(me.full_name)),
      h("span", { class: "tx" }, h("div", { class: "nm" }, me.full_name), h("div", { class: "rl" }, me.role))),
    h("button", { type: "button", class: "btn-ghost", onClick: () => { session.clear(); me = null; location.hash = "#/login"; } }, t("logout")));
  return h("div", { class: "shell" }, side, h("div", { class: "content" }, top, main));
}

async function refreshBell() {
  const el = document.querySelector("#bell .bellcount");
  if (!el || !session.get()) return;
  try { const { unread } = await api("GET", "/notifications/count"); el.textContent = unread ? String(unread) : ""; } catch { /* ignore */ }
}
window.addEventListener("properm-notif", refreshBell);
window.addEventListener("hashchange", () => setTimeout(refreshBell, 300));
setInterval(refreshBell, 60000);

export function resetMe() { me = null; }
window.addEventListener("hashchange", route);
route();
