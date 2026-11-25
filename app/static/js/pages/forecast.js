// Forecast card for a running project: finish date and cost against the baseline, with the reasons to trust it or not.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, h, mount, num, stat } from "../ui.js";

export async function forecastCard(slot, pid) {
  if (!slot) return;
  let f;
  try { f = await api("GET", `/projects/${pid}/forecast`); } catch { slot.hidden = true; return; }
  if (!f.available) return mount(slot, h("h2", {}, t("fc_title")), h("p", { class: "muted" }, f.reason || t("none")));
  const fin = f.finish, c = f.cost;
  const slip = f.slip_days;
  const tone = { GREEN: "green", AMBER: "amber", RED: "red" }[f.status] || "grey";
  mount(slot,
    h("div", { class: "row", style: "align-items:center;margin-bottom:8px" }, h("h2", { style: "margin:0" }, t("fc_title")), badge(t(`rag_${f.status}`), f.status), badge(`${t("fc_confidence")}: ${t(`fc_conf_${f.confidence}`)}`, "GREY")),
    h("div", { class: "grid" },
      stat(t("fc_baseline_finish"), f.baseline_finish, "grey"),
      stat(t("fc_forecast_finish"), fin ? fin.likely : "—", tone),
      stat(t("fc_slip"), slip == null ? "—" : `${slip > 0 ? "+" : ""}${slip} ${t("fc_days")}`, slip == null ? "grey" : slip > 0 ? tone : "green"),
      c && c.EAC != null ? stat(t("fc_cost_forecast"), `${num(c.EAC, 0)} ${f.currency}`, tone) : null,
      c && c.EAC != null ? stat(t("fc_budget"), `${num(c.BAC, 0)} ${f.currency}`, "grey") : null),
    fin && fin.earliest !== fin.latest ? h("p", { class: "muted small" }, `${t("fc_range")}: ${fin.earliest} → ${fin.latest}`) : null,
    c && c.low != null && c.low !== c.high ? h("p", { class: "muted small" }, `${t("fc_cost_range")}: ${num(c.low, 0)} → ${num(c.high, 0)} ${f.currency}`) : null,
    (f.reasons || []).length ? h("div", { class: "warn" }, h("ul", {}, f.reasons.map(r => h("li", {}, r)))) : null,
    h("p", { class: "muted small" }, t("fc_method")));
}
