// Upload an Excel / CSV (or MS Project XML) file, preview it row by row, then save. Also a small "Export Excel" button helper.
import { api, fileToB64, saveDocument } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, table, toast } from "../ui.js";

export const xlsxBtn = (path, filename) =>
  h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => saveDocument(path + (path.includes("?") ? "&" : "?") + "b64=true", filename)) }, t("export_excel"));

// Header row plus one example row per import, so people can download, fill in and upload. Leave password empty to have one generated.
const TEMPLATES = {
  staff: [["staff_id", "full_name", "role", "job_title", "department", "email", "capacity_hours_week", "password"], ["STAFF2", "Example Name", "STAFF", "Analyst", "", "name@example.com", "40", ""]],
  timesheets: [["staff_id", "date", "hours", "project", "activity", "nonproject_code", "description", "status"], ["STAFF2", "2026-11-23", "8", "PRJ-001", "A1", "", "Design work", "approved"]],
  costs: [["project", "date", "amount", "currency", "category", "vendor", "reference", "status"], ["PRJ-001", "2026-11-23", "1500", "SAR", "Hardware", "Supplier name", "INV-1001", "invoiced"]],
  plan: [["code", "name", "planned_hours", "planned_start", "planned_end"], ["A1", "Example task", "40", "2026-12-01", "2026-12-10"]],
};
const templateBtn = (kind) => !TEMPLATES[kind] ? null : h("button", { class: "btn secondary small", type: "button", id: `imp-template-${kind}`, onClick: () => {
  const csv = "\ufeff" + TEMPLATES[kind].map(r => r.map(c => /[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c).join(",")).join("\r\n") + "\r\n";
  const a = h("a", { href: URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" })), download: `${kind}_template.csv` });
  document.body.appendChild(a); a.click(); a.remove();
} }, t("imp_template"));

export function importCard(kind, url, { accept = ".xlsx,.csv", after, extra } = {}) {
  const file = h("input", { type: "file", id: `imp-file-${kind}`, accept });
  const skip = h("input", { type: "checkbox", id: `imp-skip-${kind}` });
  const out = h("div", { id: `imp-out-${kind}` });
  const run = (commit) => guarded(null, async () => {
    mount(out);
    if (!file.files[0]) return toast(t("imp_pick"));
    try {
      const r = await api("POST", typeof url === "function" ? url() : url, { filename: file.files[0].name, content_b64: await fileToB64(file.files[0]), commit, skip_errors: skip.checked });
      const pw = Object.entries(r.generated_passwords || {});
      mount(out,
        h("p", { class: r.errors ? "warn" : "ok" }, `${t("imp_ok")}: ${r.ok} · ${t("imp_errors")}: ${r.errors} · ${t("imp_dups")}: ${r.duplicates}`),
        r.counts ? h("p", { class: "small", id: `imp-counts-${kind}` }, `${t("imp_acts")}: ${r.counts.activities} · ${t("imp_miles")}: ${r.counts.milestones} · ${t("imp_links")}: ${r.counts.links}${r.file_project ? ` · ${r.file_project}` : ""}`) : null,
        (r.notes || []).length ? h("ul", { class: "small warn", id: `imp-notes-${kind}` }, r.notes.map(n => h("li", {}, n))) : null,
        r.blocked ? h("p", { class: "warn" }, t("imp_blocked")) : null,
        r.committed ? h("p", { class: "ok", id: `imp-done-${kind}` }, `${t("imp_saved")}: ${r.saved}`) : null,
        pw.length ? h("div", { class: "card" }, h("p", { class: "small" }, t("imp_pw")), table([t("staff_id"), t("password")], pw)) : null,
        h("div", { style: "max-height:320px;overflow:auto" }, table([t("line"), t("name"), t("status"), t("detail")], r.rows.map(x => [x.line, x.key, badge(x.status, x.status === "ok" ? "ok" : x.status === "error" ? "RED" : "GREY"), x.message]))));
      if (commit && r.committed) toast(`${t("imp_saved")}: ${r.saved}`);
      if (commit && r.committed && after) await after();
    } catch (e) { mount(out, errorBox(e)); }
  });
  return h("div", { class: "card", id: `imp-${kind}` }, h("h2", {}, t(`imp_${kind}`)), h("p", { class: "muted small" }, t(`imp_${kind}_note`)),
    h("div", { class: "row" }, field(t("brief_upload"), file), h("label", { class: "check small" }, skip, ` ${t("imp_skip")}`), templateBtn(kind), extra || null),
    h("div", { class: "row" }, h("button", { class: "btn secondary", type: "button", id: `imp-preview-${kind}`, onClick: run(false) }, t("preview")),
      h("button", { class: "btn", type: "button", id: `imp-commit-${kind}`, onClick: run(true) }, t("imp_commit"))), out);
}
