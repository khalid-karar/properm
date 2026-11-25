// Admin: API keys for the data feeds (Power BI and others) and loading finance exports (SAP, Oracle, Odoo, any spreadsheet).
import { api } from "../api.js";
import { t } from "../i18n.js";
import { importCard } from "./importer.js";
import { badge, errorBox, field, guarded, h, mount, table, toast } from "../ui.js";

const FEEDS = ["projects", "evm", "forecast", "timesheets", "costs", "alerts", "risks"];

export async function apiKeysCard() {
  const out = h("div", { id: "ak-out" });
  const body = h("div", { id: "ak-list" });
  const name = h("input", { id: "ak-name", placeholder: t("ik_name_ph"), maxlength: 120 });
  const base = location.origin;
  async function load() {
    const keys = await api("GET", "/admin/api-keys");
    mount(body, table([t("name"), t("ik_prefix"), t("ik_last_used"), t("status"), ""], keys.map(k => [k.name, h("code", {}, k.prefix + "…"), k.last_used_at ? String(k.last_used_at).slice(0, 16).replace("T", " ") : t("ik_never"),
      badge(k.active ? t("active") : t("ik_revoked"), k.active ? "approved" : "GREY"),
      k.active ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { if (!confirm(t("ik_revoke_q"))) return; await api("DELETE", `/admin/api-keys/${k.id}`); await load(); }) }, t("ik_revoke")) : ""]), t("ik_none")));
  }
  const create = guarded(null, async () => {
    mount(out);
    if (name.value.trim().length < 2) return toast(t("ik_name_ph"));
    try {
      const r = await api("POST", "/admin/api-keys", { name: name.value.trim() });
      name.value = "";
      mount(out, h("div", { class: "card", style: "border-inline-start:4px solid var(--amber,#d97706)" }, h("p", { class: "warn" }, t("ik_copy_now")),
        h("div", { class: "row" }, h("code", { id: "ak-secret", dir: "ltr", style: "user-select:all;word-break:break-all" }, r.key),
          h("button", { class: "btn small", type: "button", onClick: () => { navigator.clipboard?.writeText(r.key); toast(t("ik_copied")); } }, t("ik_copy")))));
      await load();
    } catch (e) { mount(out, errorBox(e)); }
  });
  await load();
  return h("div", { class: "card", id: "api-keys" }, h("h2", {}, t("ik_title")), h("p", { class: "muted small" }, t("ik_note")),
    h("div", { class: "row" }, field(t("name"), name), h("button", { class: "btn", type: "button", id: "ak-create", onClick: create }, t("ik_create"))), out, body,
    h("details", { style: "margin-top:12px" }, h("summary", {}, t("ik_howto")),
      h("p", { class: "small" }, t("ik_feeds")), h("p", {}, FEEDS.map(f => h("code", { dir: "ltr", style: "margin-inline-end:8px" }, `/api/v1/${f}`))),
      h("p", { class: "small" }, t("ik_pbi")),
      h("pre", { dir: "ltr", class: "small", style: "overflow:auto;padding:8px;background:var(--bg2,#f3f4f6);border-radius:6px" },
        `let\n  Source = Csv.Document(Web.Contents("${base}/api/v1/evm?format=csv", [Headers=[#"X-API-Key"="prm_..."]]), [Encoding=65001]),\n  Table = Table.PromoteHeaders(Source)\nin\n  Table`),
      h("p", { class: "muted small" }, t("ik_scope"))));
}

export function costImportCard() {
  const src = h("select", { id: "ci-source", "aria-label": t("ci_source") }, ["generic", "sap", "oracle", "odoo"].map(v => h("option", { value: v }, t(`ci_${v}`))));
  const card = importCard("costs", () => `/import/costs?source=${src.value}`);
  card.insertBefore(h("div", { class: "row" }, field(t("ci_source"), src)), card.children[2]);
  return card;
}
