// Start a project from its book: drop the file, check the pre-filled number, name, dates and phases, confirm, and land on the draft plan.
import { api, fileToB64 } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, table, toast } from "../ui.js";

export function bookStartCard() {
  const file = h("input", { type: "file", id: "bk-file", accept: ".pdf,.docx,.doc,.txt,.md,.png,.jpg,.jpeg" });
  const text = h("textarea", { id: "bk-text", rows: 4, dir: "auto", class: "ta", style: "width:100%", placeholder: t("bk_paste_ph") });
  const err = h("div"), out = h("div", { id: "bk-out" });
  let payload = null;
  const read = h("button", { class: "btn", type: "button", id: "bk-read" }, t("bk_read"));
  read.addEventListener("click", guarded(read, async () => {
    mount(err); mount(out);
    const fl = file.files[0];
    if (!fl && text.value.trim().length < 40) { mount(err, errorBox({ message: t("bk_need_input") })); return; }
    payload = fl ? { filename: fl.name, content_b64: await fileToB64(fl) } : { text: text.value };
    try { review(await api("POST", "/project-intake/book/preview", payload)); } catch (e) { mount(err, errorBox(e)); }
  }));
  const review = (pv) => {
    const num = h("input", { id: "bk-number", value: pv.number }), name = h("input", { id: "bk-name", value: pv.name, dir: "auto", style: "min-width:260px" });
    const start = h("input", { type: "date", id: "bk-start", value: String(pv.planned_start).slice(0, 10) }), end = h("input", { type: "date", id: "bk-end", value: String(pv.planned_end).slice(0, 10) });
    const e2 = h("div");
    const go = h("button", { class: "btn gold", type: "button", id: "bk-create" }, t("bk_create"));
    go.addEventListener("click", guarded(go, async () => {
      mount(e2);
      if (!name.value.trim() || !num.value.trim()) { mount(e2, errorBox({ message: t("bk_need_name") })); name.focus(); return; }
      try {
        const r = await api("POST", "/project-intake/book/confirm", { ...payload, number: num.value.trim(), name: name.value.trim(), planned_start: start.value, planned_end: end.value });
        toast(t("bk_created"));
        try { sessionStorage.setItem("properm.opentab", "brief"); } catch { /* ignore */ }
        location.hash = `#/projects/${r.project_id}`;
      } catch (e) { mount(e2, errorBox(e)); }
    }));
    mount(out, h("div", { class: "card", style: "margin-top:12px" }, h("h3", {}, t("bk_check")),
      h("p", { class: "muted small" }, `${pv.language === "ar" ? "العربية" : "English"} · ${pv.pages} p · ${pv.counts.activities} ${t("brief_tasks")} · ${pv.counts.requirements} ${t("requirements")} · ${pv.counts.deliverables} ${t("brief_deliverables")}`,
        pv.number_from_book ? ` · ${t("bk_number_from_book")}` : ""),
      ...(pv.warnings || []).map(w => h("p", { class: "warn" }, w)),
      h("div", { class: "row" }, field(t("number"), num), field(t("name"), name), field(t("planned_start"), start), field(t("planned_end"), end)),
      pv.phases.length ? table([t("brief_phase"), t("name"), t("brief_from_month"), t("brief_to_month")], pv.phases.map(ph => [ph.n, ph.name, ph.start_month, ph.end_month])) : null,
      h("p", { class: "muted small" }, t("bk_note")), go, e2));
  };
  return h("div", { class: "card", id: "book-start" }, h("h2", {}, t("bk_title")), h("p", { class: "muted small" }, t("bk_intro")),
    h("div", { class: "row" }, field(t("file"), file), read), h("details", { style: "margin-top:8px" }, h("summary", { class: "small" }, t("bk_or_paste")), text), err, out);
}
