// Configuration (ADMIN): maintained lists and AI administration.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, num, table, toast } from "../ui.js";

const LISTS = ["nonproject_code", "risk_category", "kpi_template", "closure_item"];

export default async function (root) {
  async function render() {
    const [lists, ai] = await Promise.all([api("GET", "/admin/lists"), api("GET", "/admin/ai")]);
    const cards = LISTS.map(key => {
      const code = h("input", { style: "width:130px", placeholder: key === "risk_category" ? "" : "CODE" }), label = h("input", { style: "min-width:200px" }), err = h("div");
      const unit = h("input", { style: "width:80px" }), hib = h("select", {}, h("option", { value: "1" }, t("higher_better")), h("option", { value: "0" }, t("lower_better")));
      const add = h("button", { class: "btn", type: "button" }, t("add"));
      add.addEventListener("click", guarded(add, async () => {
        mount(err);
        try { await api("PUT", `/admin/lists/${key}/${encodeURIComponent(code.value.trim())}`, { label: label.value.trim(), data: key === "kpi_template" ? { unit: unit.value.trim(), higher_is_better: hib.value === "1" } : null }); toast(t("saved")); await render(); }
        catch (e) { mount(err, errorBox(e)); }
      }));
      const toggle = (x) => h("input", { type: "checkbox", checked: x.active, disabled: x.protected, "aria-label": t("active"), onChange: guarded(null, async (ev) => {
        await api("PUT", `/admin/lists/${key}/${encodeURIComponent(x.code)}`, { label: x.label, active: ev.target.checked, data: x.data }); toast(t("saved")); await render(); }) });
      return h("div", { class: "card" }, h("h2", {}, t(`list_${key}`)), h("p", { class: "muted small" }, t(`list_${key}_note`)),
        table([t("code"), t("name"), key === "kpi_template" ? t("unit") : null, t("active"), ""].filter(x => x !== null),
          lists[key].map(x => [x.code, x.label, ...(key === "kpi_template" ? [x.data.unit || "—"] : []), toggle(x),
            x.default ? badge(t("built_in"), "GREY") : h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/admin/lists/${key}/${encodeURIComponent(x.code)}`); await render(); }) }, t("remove"))]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("code"), code), field(t("name"), label), key === "kpi_template" ? [field(t("unit"), unit), field(t("direction"), hib)] : null, add), err);
    });
    const limit = h("input", { type: "number", min: "1", value: ai.hourly_limit, style: "width:90px" });
    const setSetting = (k, v) => api("PUT", `/admin/settings/${k}`, { value: v }).then(() => { toast(t("saved")); return render(); });
    const testOut = h("div");
    const aiCard = h("div", { class: "card" }, h("h2", {}, t("ai_admin")),
      h("div", { class: "grid", style: "margin-bottom:12px" },
        h("div", { class: "stat" }, h("div", { class: "v" }, ai.mode === "live" ? t("ai_live") : t("ai_stub")), h("div", { class: "l" }, t("mode"))),
        h("div", { class: "stat" }, h("div", { class: "v" }, ai.model), h("div", { class: "l" }, t("model"))),
        h("div", { class: "stat" }, h("div", { class: "v" }, ai.host || "—"), h("div", { class: "l" }, t("host"))),
        h("div", { class: `stat ${ai.in_kingdom === false ? "red" : ai.in_kingdom ? "green" : ""}` }, h("div", { class: "v" }, ai.in_kingdom == null ? "—" : ai.in_kingdom ? t("yes") : t("no")), h("div", { class: "l" }, t("in_kingdom")))),
      ai.mode === "stub" ? h("div", { class: "warn" }, t("ai_stub_admin_note")) : null,
      h("p", { class: "muted small" }, `${t("allowed_suffixes")}: ${ai.allowed_host_suffixes.join(", ")}`),
      h("div", { class: "row", style: "align-items:end; margin-bottom:12px" },
        h("label", { style: "flex-direction:row;align-items:center;gap:8px" }, h("input", { type: "checkbox", checked: ai.enabled, onChange: guarded(null, (ev) => setSetting("ai_enabled", ev.target.checked ? 1 : 0)) }), t("ai_enabled")),
        field(t("ai_hourly_limit"), limit), h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => setSetting("ai_hourly_limit", Number(limit.value))) }, t("save")),
        h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { const r = await api("POST", "/admin/ai/test"); mount(testOut, r.ok ? h("div", { class: "ok" }, `${t("test_ok")}: ${r.sample}`) : h("div", { class: "err" }, r.error)); }) }, t("test_connection"))), testOut,
      h("h3", {}, t("ai_usage")), table([t("type"), t("total"), t("applied"), t("rejected")], Object.entries(ai.usage_30d).map(([k, v]) => [k, v.total, v.applied || 0, v.rejected || 0]), t("none")),
      ai.recent_failures.length ? [h("h3", {}, t("ai_failures")), table([t("time"), t("reason")], ai.recent_failures.map(f => [String(f.ts).replace("T", " ").slice(0, 19), f.reason || ""]))] : null);
    mount(root, h("h1", {}, t("nav_config")), aiCard, h("div", { class: "grid2" }, cards));
  }
  await render();
}
