// Project "Documents" tab: every file of the project in one place, with category, version, uploader, history, search and download.
import { api, fileToB64, saveDocument } from "../api.js";
import { t } from "../i18n.js";
import { versionsButton } from "./projdepth.js";
import { errorBox, field, guarded, h, modal, mount, table, toast } from "../ui.js";

export const DOC_KINDS = ["tender_book", "proposal", "contract", "charter", "scope", "minutes", "report", "correspondence", "other"];
const fmtSize = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

export async function documentsTab(body, p, { pid, canManage, render }) {
  const q = h("input", { type: "search", id: "doc-q", style: "min-width:320px", placeholder: t("doc_search_ph"), "aria-label": t("search") });
  const cat = h("select", { id: "doc-cat", "aria-label": t("category") }, h("option", { value: "" }, t("doc_all")), DOC_KINDS.map(k => h("option", { value: k }, t(`doc_${k}`))));
  const list = h("div", { id: "doc-list" });
  const history = async (d) => {
    const ev = await api("GET", `/projects/${pid}/documents/${d.id}/history`);
    modal({ title: `${t("cl_history")}: ${d.filename}`, body: ev.length ? h("ul", { class: "dashlist" }, ev.map(x => h("li", {}, h("span", {}, t(`dh_${x.action.split(".")[1]}`)), h("span", { class: "muted small" }, ` ${x.by || "—"} · ${String(x.at).slice(0, 16).replace("T", " ")}`)))) : h("p", {}, t("none")),
      actions: [{ label: t("close"), onClick: (c) => c() }] });
  };
  const load = async () => {
    const qs = new URLSearchParams(); if (q.value.trim()) qs.set("q", q.value.trim()); if (cat.value) qs.set("kind", cat.value);
    const docs = await api("GET", `/projects/${pid}/documents${qs.toString() ? "?" + qs : ""}`);
    mount(list, table([t("category"), t("file"), t("doc_version"), t("doc_uploader"), t("date"), t("size"), ""], docs.map(d => [t(`doc_${d.kind}`),
      h("span", {}, d.filename, d.description ? h("div", { class: "muted small" }, d.description) : null), `v${d.version}`, d.uploader || "—", String(d.uploaded_at).slice(0, 10), fmtSize(d.size),
      h("span", { class: "row", style: "gap:6px" },
        h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, () => saveDocument(`/projects/${pid}/documents/${d.id}/content`, d.filename)) }, t("download")),
        versionsButton(pid, d, { canManage, render }),
        h("button", { class: "btn small secondary", type: "button", "data-act": "doc-history", onClick: guarded(null, () => history(d)) }, t("cl_history")),
        canManage ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/projects/${pid}/documents/${d.id}`); await load(); }) }, t("remove")) : null)]), t("none")));
  };
  q.addEventListener("input", () => { clearTimeout(q._t); q._t = setTimeout(() => load().catch(() => {}), 250); });
  cat.addEventListener("change", () => load().catch(() => {}));
  const kind = h("select", { id: "doc-kind", "aria-label": t("category") }, DOC_KINDS.map(k => h("option", { value: k }, t(`doc_${k}`))));
  const file = h("input", { type: "file", id: "doc-file", accept: ".pdf,.docx,.doc,.txt,.md,.png,.jpg,.jpeg,.xlsx" });
  const desc = h("input", { id: "doc-desc", maxlength: 500, placeholder: t("doc_desc_ph"), style: "min-width:220px" }), err = h("div");
  const up = h("button", { class: "btn", type: "button", id: "doc-upload" }, t("upload"));
  up.addEventListener("click", guarded(up, async () => {
    mount(err);
    const fl = file.files[0];
    if (!fl) { mount(err, h("div", { class: "err" }, t("choose_file"))); return; }
    try { await api("POST", `/projects/${pid}/documents`, { kind: kind.value, filename: fl.name, content_b64: await fileToB64(fl), description: desc.value.trim() || null }); toast(t("saved")); file.value = ""; desc.value = ""; await load(); } catch (e) { mount(err, errorBox(e)); }
  }));
  mount(body, h("div", { class: "card", id: "documents-card" }, h("h2", {}, t("documents")), h("p", { class: "muted small" }, t("doc_area_note")),
    h("div", { class: "row", style: "margin-bottom:10px" }, q, cat), list,
    canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("category"), kind), field(t("file"), file), field(t("description"), desc), up) : null, err));
  await load();
}
