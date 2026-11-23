import { api, session } from "./api.js";
import { applyDir, getLang, setLang, t } from "./i18n.js";
import { clear, errorBox, h, icon, mount } from "./ui.js";

applyDir();
const app = document.getElementById("app");
let me = null;

const NAV = {
  STAFF: ["timesheet", "approvals", "projects", "alerts"],
  PM: ["timesheet", "approvals", "projects", "load", "dashboard", "alerts"],
  PMO: ["timesheet", "approvals", "projects", "load", "dashboard", "programs", "alerts"],
  ADMIN: ["timesheet", "approvals", "projects", "load", "dashboard", "programs", "alerts", "admin"],
  DECISION_MAKER: ["projects", "load", "dashboard", "programs", "alerts"],
  PROGRAM_MANAGER: ["projects", "load", "dashboard", "programs", "alerts"],
};
const HOME = { STAFF: "timesheet", PM: "projects" };
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
  const page = name || homeFor(me.role);
  if (page === "login") { location.hash = `#/${homeFor(me.role)}`; return; }
  if (!allowed.includes(page) && page !== "notifications") { location.hash = `#/${homeFor(me.role)}`; return; }

  const main = h("main", {}, h("p", { class: "muted" }, t("loading")));
  document.body.classList.remove("nav-open");
  mount(app, shell(page, main));
  try {
    const mod = await import(`./pages/${page}.js`);
    await mod.default(main, { me, arg });
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
    h("span", { class: "spacer" }),
    h("a", { href: "#/notifications", class: "bell", id: "bell", "aria-label": t("notifications"), title: t("notifications") }, icon("bell"), h("span", { class: "bellcount" })),
    h("button", { type: "button", class: "btn-ghost", onClick: () => { setLang(getLang() === "en" ? "ar" : "en"); route(); } }, getLang() === "en" ? "العربية" : "English"),
    h("span", { class: "who" }, h("span", { class: "avatar" }, initials(me.full_name)),
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
