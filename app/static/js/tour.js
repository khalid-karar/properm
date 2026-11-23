// First-sign-in tour: four short steps pointing at the menu, search, assistant and theme button. Shown once per person; can be replayed from Home.
import { t } from "./i18n.js";
import { h } from "./ui.js";

const STEPS = [["aside.side nav", "tour_menu"], ["#topsearch", "tour_search"], ["#asst-btn", "tour_assistant"], ["#theme-btn", "tour_theme"]];
const key = (me) => `properm.tour.${me.id}`;
const seen = (me) => { try { return !!localStorage.getItem(key(me)) || !!localStorage.getItem("properm.tour.off"); } catch { return true; } };
const mark = (me) => { try { localStorage.setItem(key(me), "1"); } catch { /* private mode */ } };

export function startTour(me) {
  document.getElementById("tour-card")?.remove(); document.querySelector(".tour-shade")?.remove();
  const steps = STEPS.filter(([sel]) => document.querySelector(sel));
  let i = 0, shade = h("div", { class: "tour-shade" }), card;
  const clear = () => document.querySelectorAll(".tour-on").forEach(e => e.classList.remove("tour-on"));
  const end = () => { clear(); shade.remove(); card?.remove(); mark(me); };
  const show = () => {
    clear();
    const [sel, k] = steps[i];
    document.querySelector(sel).classList.add("tour-on");
    const last = i === steps.length - 1;
    const next = h("button", { class: "btn small", type: "button", id: "tour-next", onClick: () => { if (last) end(); else { i++; show(); } } }, last ? t("tour_done") : t("tour_next"));
    const nc = h("div", { class: "tour-card", id: "tour-card", role: "dialog", "aria-label": t("tour_title") },
      h("h3", {}, t(k + "_t")), h("p", { class: "muted" }, t(k)),
      h("div", { class: "row" }, h("button", { class: "btn small secondary", type: "button", id: "tour-skip", onClick: end }, t("tour_skip")), h("span", { class: "small muted" }, `${i + 1} / ${steps.length}`), next));
    card?.replaceWith(nc); card = card || nc; card = nc;
    if (!nc.isConnected) document.body.append(nc);
    next.focus();
  };
  if (!steps.length) return;
  document.body.append(shade);
  card = h("div"); document.body.append(card);
  show();
}

export function maybeTour(me) { if (!seen(me)) { mark(me); setTimeout(() => startTour(me), 600); } }
