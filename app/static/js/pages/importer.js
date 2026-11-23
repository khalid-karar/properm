// Upload an Excel / CSV (or MS Project XML) file, preview it row by row, then save. Also a small "Export Excel" button helper.
import { api, fileToB64, saveDocument } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, table, toast } from "../ui.js";

export const xlsxBtn = (path, filename) =>
  h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => saveDocument(path + (path.includes("?") ? "&" : "?") + "b64=true", filename)) }, t("export_excel"));

export function importCard(kind, url, { accept = ".xlsx,.csv", after } = {}) {
  const file = h("input", { type: "file", id: `imp-file-${kind}`, accept });
  const skip = h("input", { type: "checkbox", id: `imp-skip-${kind}` });
  const out = h("div", { id: `imp-out-${kind}` });
  const run = (commit) => guarded(null, async () => {
    mount(out);
    if (!file.files[0]) return toast(t("imp_pick"));
    try {
      const r = await api("POST", url, { filename: file.files[0].name, content_b64: await fileToB64(file.files[0]), commit, skip_errors: skip.checked });
      const pw = Object.entries(r.generated_passwords || {});
      mount(out,
        h("p", { class: r.errors ? "warn" : "ok" }, `${t("imp_ok")}: ${r.ok} · ${t("imp_errors")}: ${r.errors} · ${t("imp_dups")}: ${r.duplicates}`),
        r.blocked ? h("p", { class: "warn" }, t("imp_blocked")) : null,
        r.committed ? h("p", { class: "ok", id: `imp-done-${kind}` }, `${t("imp_saved")}: ${r.saved}`) : null,
        pw.length ? h("div", { class: "card" }, h("p", { class: "small" }, t("imp_pw")), table([t("staff_id"), t("password")], pw)) : null,
        h("div", { style: "max-height:320px;overflow:auto" }, table([t("line"), t("name"), t("status"), t("detail")], r.rows.map(x => [x.line, x.key, badge(x.status, x.status === "ok" ? "ok" : x.status === "error" ? "RED" : "GREY"), x.message]))));
      if (commit && r.committed) toast(`${t("imp_saved")}: ${r.saved}`);
      if (commit && r.committed && after) await after();
    } catch (e) { mount(out, errorBox(e)); }
  });
  return h("div", { class: "card", id: `imp-${kind}` }, h("h2", {}, t(`imp_${kind}`)), h("p", { class: "muted small" }, t(`imp_${kind}_note`)),
    h("div", { class: "row" }, field(t("brief_upload"), file), h("label", { class: "check small" }, skip, ` ${t("imp_skip")}`)),
    h("div", { class: "row" }, h("button", { class: "btn secondary", type: "button", id: `imp-preview-${kind}`, onClick: run(false) }, t("preview")),
      h("button", { class: "btn", type: "button", id: `imp-commit-${kind}`, onClick: run(true) }, t("imp_commit"))), out);
}
