import { api, session } from "./api.js";
import { applyDir, getLang, setLang, t } from "./i18n.js";
import { clear, errorBox, h, mount } from "./ui.js";

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
  if (!allowed.includes(page)) { location.hash = `#/${homeFor(me.role)}`; return; }

  const main = h("main", {}, h("p", { class: "muted" }, t("loading")));
  mount(app, shell(page), main);
  try {
    const mod = await import(`./pages/${page}.js`);
    await mod.default(main, { me, arg });
  } catch (e) {
    mount(main, errorBox(e));
  }
}

function shell(active) {
  return h("header", { class: "top" },
    h("span", { class: "brand" }, t("app")),
    h("nav", {}, (NAV[me.role] || []).map(n =>
      h("a", { href: `#/${n}`, class: n === active ? "active" : "" }, t(`nav_${n}`)))),
    h("span", { class: "who" }, `${me.full_name} · ${me.role}`),
    h("button", { type: "button", onClick: () => { setLang(getLang() === "en" ? "ar" : "en"); route(); } }, getLang() === "en" ? "العربية" : "English"),
    h("button", { type: "button", onClick: () => { session.clear(); me = null; location.hash = "#/login"; } }, t("logout")));
}

export function resetMe() { me = null; }
window.addEventListener("hashchange", route);
route();
