// Configuration (ADMIN): maintained lists and AI administration.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { usageCard } from "../aiusage.js";
import { badge, errorBox, field, guarded, h, mount, num, table, toast } from "../ui.js";

const LISTS = ["nonproject_code", "risk_category", "kpi_template", "closure_item", "department", "skill"];

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
    // ---- AI model per tenant: default for ALL tenants + an optional override for one tenant ----
    const ms = await api("GET", "/admin/ai/settings");
    const modelForm = (scope, cur, title, note) => {
      const url = h("input", { type: "text", value: cur?.base_url || "", placeholder: "https://ai.example.sa/v1", style: "min-width:260px", dir: "ltr" });
      const model = h("input", { type: "text", value: cur?.model || "qwen", style: "width:160px", dir: "ltr" });
      const key = h("input", { type: "password", value: "", autocomplete: "new-password", placeholder: cur?.has_key ? t("ai_key_saved") : t("ai_key_none"), style: "width:200px", dir: "ltr" });
      const on = h("input", { type: "checkbox", checked: cur ? cur.enabled : true });
      const out = h("div");
      const body = () => ({ base_url: url.value, model: model.value, api_key: key.value || null, enabled: on.checked });
      return h("div", { class: "card", style: "margin-top:12px" }, h("h3", {}, title), h("p", { class: "muted small" }, note), 
        h("div", { class: "row", style: "align-items:end" }, field(t("ai_model_url"), url), field(t("model"), model), field(t("ai_api_key"), key),
          h("label", { style: "flex-direction:row;align-items:center;gap:8px" }, on, t("active"))),
        h("div", { class: "row", style: "margin-top:8px" },
          h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { await api("PUT", `/admin/ai/settings/${scope}`, body()); toast(t("saved")); await render(); }) }, t("save")),
          h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, async () => {
            const r = await api("POST", "/admin/ai/test-scope", { scope: String(scope), base_url: url.value || null, model: model.value || null, api_key: key.value || null });
            mount(out, r.ok ? h("div", { class: "ok" }, `${t("test_ok")}: ${r.sample}`) : h("div", { class: "err" }, r.error)); }) }, t("test_connection")),
          cur ? h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/admin/ai/settings/${scope}`); toast(t("saved")); await render(); }) }, scope === "global" ? t("remove") : t("ai_remove_override")) : null), out);
    };
    const tName = h("input", { type: "text", placeholder: t("ai_tenant_name") });
    const tSlug = h("input", { type: "text", placeholder: "acme", dir: "ltr", style: "width:120px" });
    const tErr = h("div"), taErr = h("div");
    const taSel = h("select", {}, ...ms.tenants.map(x => h("option", { value: x.id }, x.name)));
    const taSid = h("input", { type: "text", dir: "ltr", style: "width:130px" }), taName = h("input", { type: "text" });
    const taPw = h("input", { type: "password", autocomplete: "new-password", style: "width:150px" });
    const modelsCard = h("div", { class: "card", id: "ai-models-card" }, h("h2", {}, t("ai_models")), h("p", { class: "muted small" }, t("ai_models_note")),
      ms.platform_owner ? modelForm("global", ms.global, t("ai_default_all"), ms.env_default ? t("ai_default_all_note_env") : t("ai_default_all_note")) : null,
      ...ms.tenants.map(x => modelForm(x.id, x.override, `${t("ai_tenant")}: ${x.name}`, x.override ? t("ai_override_on") : t("ai_override_off"))),
      ms.platform_owner ? h("div", { class: "card", style: "margin-top:12px" }, h("h3", {}, t("ai_tenants")), 
        table([t("name"), t("code"), t("users"), t("active"), ""], ms.tenants.map(x => [x.name, x.slug, x.users, x.active ? t("yes") : t("no"),
          h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, async () => { await api("PATCH", `/admin/tenants/${x.id}`, { active: !x.active }); await render(); }) }, x.active ? t("ai_tenant_off") : t("ai_tenant_on"))]), t("none")),
        h("div", { class: "row", style: "margin-top:8px;align-items:end" }, field(t("name"), tName), field(t("code"), tSlug),
          h("button", { class: "btn small", type: "button", onClick: guarded(tErr, async () => { await api("POST", "/admin/tenants", { name: tName.value, slug: tSlug.value }); await render(); }) }, t("add"))), tErr,
        h("h3", { style: "margin-top:12px" }, t("ten_new_admin")),
        h("div", { class: "row", style: "align-items:end" }, field(t("ten_pick"), taSel), field(t("staff_id"), taSid), field(t("full_name"), taName), field(t("password"), taPw),
          h("button", { class: "btn small", type: "button", onClick: guarded(taErr, async () => { await api("POST", `/admin/tenants/${taSel.value}/admins`, { staff_id: taSid.value, full_name: taName.value, password: taPw.value }); toast(t("saved")); await render(); }) }, t("add"))), taErr,
        h("p", { class: "muted small" }, t("ai_tenants_note"))) : null);
    const gov = await api("GET", "/config/governance");
    const tg = (k) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: gov[k], onChange: guarded(null, (ev) => setSetting(k, ev.target.checked ? 1 : 0)) }), " ", t(`gov_${k}`));
    const govCard = h("div", { class: "card", id: "gov-card" }, h("h2", {}, t("governance")), h("p", { class: "muted small" }, t("governance_note")), tg("intake_required"), tg("stage_gates"));
    mount(root, h("h1", {}, t("nav_config")), govCard, aiCard, await usageCard(), modelsCard, h("div", { class: "grid2" }, cards));
  }
  await render();
}
