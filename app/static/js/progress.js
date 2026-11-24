// A live progress box for long AI jobs: shows a bar, a percentage, what the AI is doing now and how long it has taken.
import { api } from "./api.js";
import { t } from "./i18n.js";
import { bar, h, mount } from "./ui.js";

const say = (info, step) => {
  const i = info || {};
  const base = t(`prog_${step}`).replace("{n}", i.n ?? "").replace("{total}", i.total ?? "");
  return base;
};

/** Run `job(headers)` (which must send the headers on its request) while showing progress inside `box`. Returns the job's result. */
export async function withProgress(box, job) {
  const key = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()).replace(/[^\w-]/g, "");
  const started = Date.now();
  const msg = h("div", { class: "prog-msg" }, t("prog_start"));
  const pct = h("strong", {}, "0%");
  const time = h("span", { class: "muted small" }, "0s");
  const fill = h("div", {});
  const draw = (p) => { fill.replaceChildren(bar(p)); pct.textContent = `${Math.round(p)}%`; };
  draw(0);
  mount(box, h("div", { class: "card prog", role: "status", "aria-live": "polite" },
    h("div", { class: "row", style: "justify-content:space-between" }, h("strong", {}, t("prog_title")), pct), fill, msg,
    h("div", { class: "row", style: "justify-content:space-between" }, h("span", { class: "muted small" }, t("prog_wait")), time)));
  let stop = false, shown = 0;
  const poll = async () => {
    while (!stop) {
      time.textContent = `${Math.round((Date.now() - started) / 1000)}s`;
      try {
        const j = await api("GET", `/project-intake/progress/${key}`);
        if (!stop) { shown = Math.max(shown, j.pct); draw(shown); msg.textContent = say(j.info, j.step); }
      } catch { /* not reporting yet, keep the last value */ }
      await new Promise(r => setTimeout(r, 1200));
    }
  };
  poll();
  try { return await job({ "X-Progress-Id": key }); }
  finally { stop = true; mount(box); }
}
