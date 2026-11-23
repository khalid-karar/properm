// Floating AI assistant and Ctrl/Cmd+K quick jump. Text only goes through h(); nothing is inserted as HTML.
import { aiLabel } from "./aistatus.js";
import { api } from "./api.js";
import { getLang, t } from "./i18n.js";
import { h, icon, mount } from "./ui.js";

let panel, log, input, btn, busy = false;
const hist = [];

function currentProject() { const m = location.hash.match(/#\/projects\/(\d+)/); return m ? Number(m[1]) : null; }

function bubble(who, text, extra) {
  const b = h("div", { class: `msg ${who}` }, h("div", { class: "bub" }, text), extra || null);
  log.append(b); log.scrollTop = log.scrollHeight; return b;
}

async function send(q) {
  q = (q || input.value).trim();
  if (!q || busy) return;
  input.value = ""; busy = true; bubble("me", q);
  const wait = bubble("bot", t("asst_thinking"));
  try {
    const r = await api("POST", "/ai/ask", { question: q, lang: getLang(), project_id: currentProject() });
    wait.remove();
    const links = (r.links || []).map(l => h("a", { class: "chip link", href: l.href, onClick: () => panel.classList.remove("open") }, l.label));
    const sug = (r.suggestions || []).map(s => h("button", { class: "chip", type: "button", onClick: () => send(s) }, s));
    bubble("bot", r.answer, h("div", { class: "chips-row" }, links, sug));
  } catch (e) {
    wait.remove(); bubble("bot", e.lines ? e.lines().join(" · ") : t("error"));
  } finally { busy = false; input.focus(); }
}

function open(q) {
  panel.classList.add("open"); btn.setAttribute("aria-expanded", "true");
  if (!log.children.length) {
    bubble("bot", t("asst_hello"), h("div", { class: "chips-row" }, [t("asst_q_today"), t("asst_q_hours"), t("asst_q_alerts")].map(s => h("button", { class: "chip", type: "button", onClick: () => send(s) }, s))));
  }
  input.focus();
  if (typeof q === "string" && q) send(q);
}

export function mountAssistant() {
  if (document.getElementById("asst-btn")) return;
  btn = h("button", { id: "asst-btn", class: "asst-btn", type: "button", "aria-label": t("asst_title"), "aria-expanded": "false", title: t("asst_title"), onClick: () => (panel.classList.contains("open") ? (panel.classList.remove("open"), btn.setAttribute("aria-expanded", "false")) : open()) }, icon("spark"));
  log = h("div", { id: "asst-log", class: "asst-log", role: "log", "aria-live": "polite" });
  input = h("input", { type: "text", id: "asst-input", placeholder: t("asst_ph"), "aria-label": t("asst_ph"), maxlength: 500, onKeydown: (e) => { if (e.key === "Enter") send(); } });
  panel = h("section", { id: "asst-panel", class: "asst-panel", "aria-label": t("asst_title") },
    h("header", {}, h("span", { class: "asst-ic" }, icon("spark")), h("div", {}, h("strong", {}, t("asst_title")), h("small", {}, t("asst_sub")), h("div", {}, aiLabel())),
      h("button", { class: "iconbtn", type: "button", "aria-label": t("close"), onClick: () => { panel.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); } }, "✕")),
    log, h("footer", {}, input, h("button", { class: "btn", type: "button", onClick: () => send() }, t("asst_send"))));
  document.body.append(panel, btn);
  window.addEventListener("properm-ask", (e) => open(e.detail));
  document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); palette(); } if (e.key === "Escape") panel.classList.remove("open"); });
}

export function unmountAssistant() { for (const id of ["asst-btn", "asst-panel"]) document.getElementById(id)?.remove(); hist.length = 0; }

// ---- Ctrl/Cmd+K: jump to any page or project ----
async function palette() {
  if (document.getElementById("palette")) return;
  const pages = [...document.querySelectorAll("aside.side nav a")].map(a => ({ label: a.textContent, href: a.getAttribute("href") }));
  let projects = [];
  try { projects = (await api("GET", "/projects")).map(p => ({ label: `${p.number} · ${p.name}`, href: `#/projects/${p.id}` })); } catch { /* ignore */ }
  const all = [...pages, ...projects];
  const list = h("div", { class: "pal-list", role: "listbox" });
  const inp = h("input", { type: "text", placeholder: t("palette_ph"), "aria-label": t("palette_ph") });
  const ov = h("div", { id: "palette", class: "overlay", onClick: (e) => { if (e.target === ov) ov.remove(); } }, h("div", { class: "modal pal" }, inp, list));
  let sel = 0, rows = [];
  const draw = () => {
    const q = inp.value.trim().toLowerCase();
    rows = all.filter(x => !q || x.label.toLowerCase().includes(q)).slice(0, 9); sel = Math.min(sel, Math.max(0, rows.length - 1));
    mount(list, rows.map((x, i) => h("a", { class: `pal-row ${i === sel ? "sel" : ""}`, href: x.href, role: "option", onClick: () => ov.remove() }, x.label)));
  };
  inp.addEventListener("input", () => { sel = 0; draw(); });
  inp.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { sel = Math.min(sel + 1, rows.length - 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); draw(); e.preventDefault(); }
    else if (e.key === "Enter" && rows[sel]) { location.hash = rows[sel].href; ov.remove(); }
    else if (e.key === "Escape") ov.remove();
  });
  document.body.append(ov); draw(); inp.focus();
}
