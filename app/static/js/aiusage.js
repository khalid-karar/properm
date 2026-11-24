// AI usage and cost: the platform owner sees every tenant, a tenant administrator sees their own tenant.
import { api } from "./api.js";
import { t } from "./i18n.js";
import { bar, errorBox, field, h, mount, num, stat, table } from "./ui.js";

const sar = (v) => `${num(v, v < 1 ? 3 : 2)} ${t("usage_sar")}`;
const kchars = (v) => (v >= 1e6 ? `${num(v / 1e6, 2)} M` : v >= 1e3 ? `${num(v / 1e3, 1)} k` : String(v));

export async function usageCard() {
  const body = h("div", {});
  const days = h("select", {}, [7, 30, 90, 365].map(d => h("option", { value: d, selected: d === 30 }, `${d} ${t("usage_days")}`)));
  const tenant = h("select", {}, h("option", { value: "" }, t("usage_all")));
  let tenantsLoaded = false, hidden = false;
  async function load() {
    try {
      const u = await api("GET", `/admin/ai/usage?days=${days.value}${tenant.value ? `&tenant_id=${tenant.value}` : ""}`);
      if (u.owner && !tenantsLoaded) {
        tenantsLoaded = true;
        for (const x of u.by_tenant || []) if (x.tenant_id != null) tenant.append(h("option", { value: x.tenant_id }, x.name));
      }
      const max = Math.max(1e-9, ...(u.by_tenant || []).map(x => x.cost));
      mount(body,
        h("div", { class: "grid" }, stat(t("usage_month"), sar(u.month.cost)), stat(t("usage_forecast"), sar(u.month.forecast)),
          stat(`${t("usage_period")} (${u.days} ${t("usage_days")})`, sar(u.total.cost)), stat(t("usage_calls"), num(u.total.calls, 0)),
          stat(t("usage_avg"), `${u.total.avg_seconds} s`)),
        u.owner ? h("div", {}, h("h3", {}, t("usage_by_tenant")),
          table([t("ai_tenant"), t("usage_calls"), t("usage_chars"), t("usage_cost"), ""], (u.by_tenant || []).map(x => [x.name, num(x.calls, 0), kchars(x.chars), sar(x.cost), bar(x.cost / max * 100)]), t("none"))) : null,
        h("h3", {}, t("usage_by_user")),
        table([t("name"), u.owner ? t("ai_tenant") : "", t("usage_calls"), t("usage_chars"), t("usage_cost")].filter((x, i) => x !== "" || i !== 1),
          u.by_user.map(x => (u.owner ? [x.name, x.tenant || "", num(x.calls, 0), kchars(x.chars), sar(x.cost)] : [x.name, num(x.calls, 0), kchars(x.chars), sar(x.cost)])), t("none")),
        h("h3", {}, t("usage_by_task")),
        table([t("type"), t("usage_calls"), t("usage_chars"), t("usage_cost")], u.by_task.map(x => [x.task, num(x.calls, 0), kchars(x.chars), sar(x.cost)]), t("none")),
        h("p", { class: "muted small" }, t("usage_note").replace("{rate}", String(u.rate_per_10k_chars))));
    } catch (e) { if (e.status === 403) hidden = true; else mount(body, errorBox(e)); }
  }
  days.addEventListener("change", load);
  tenant.addEventListener("change", load);
  await load();
  if (hidden) return null;   // not the platform owner: no card
  return h("div", { class: "card", id: "ai-usage-card" }, h("h2", {}, t("usage_title")), h("p", { class: "muted small" }, t("usage_intro")),
    h("div", { class: "row", style: "align-items:end" }, field(t("usage_period"), days), field(t("ai_tenant"), tenant)), body);
}
