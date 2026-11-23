// Project "Control" tab: baseline vs forecast per activity, action log, lessons learned.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, modal, mount, num, table, toast } from "../ui.js";

const RAG = { green: "GREEN", amber: "AMBER", red: "RED" };
export const LESSON_CATS = ["scope", "schedule", "cost", "quality", "resources", "stakeholders", "procurement", "risk", "technical", "other"];

export async function control(body, p, { pid, me, dir, canManage, render }) {
  const [v, acts, les] = await Promise.all([api("GET", `/projects/${pid}/variance`), api("GET", `/projects/${pid}/actions`), api("GET", `/projects/${pid}/lessons`)]);
  const cost = v.currency != null && v.rows.some(r => "baseline_cost" in r);
  const sign = (x, d = 1) => (x == null ? "—" : h("span", { class: x < 0 ? "neg" : "" }, num(x, d)));

  const editFc = (r) => {
    const end = h("input", { type: "date", value: r.forecast_end || "" }), note = h("textarea", { rows: 2 }, r.forecast_note || ""), err = h("div");
    modal({ title: `${t("forecast")}: ${r.code}`, body: h("div", {}, err, field(t("forecast_end"), end), field(t("note"), note), h("p", { class: "muted small" }, t("etc_where"))),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("save"), onClick: async (c) => {
        try { await api("PUT", `/projects/${pid}/activities/${r.activity_id}/forecast`, { forecast_end: end.value || null, note: note.value.trim() || null }); c(); toast(t("saved")); await render(); }
        catch (e) { mount(err, errorBox(e)); } } }] });
  };
  const vcard = h("div", { class: "card", id: "variance-card" }, h("h2", {}, t("variance_title")), h("p", { class: "muted small" }, t("variance_note")),
    table([t("activity"), t("baseline_h"), t("actual_h"), "%", t("etc_hours"), t("eac_h"), t("var_h"), cost ? t("eac_cost") : null, cost ? t("cost_var") : null, t("baseline_end_h"), t("forecast_end"), t("slip_days"), "", canManage ? "" : null].filter(x => x !== null),
      [...v.rows.map(r => [`${r.code} · ${r.name}`, num(r.baseline_hours), num(r.actual_hours), `${num(r.pct_complete, 0)}%`, h("span", { title: t(`etc_${r.etc_source}`) }, num(r.etc_hours), " ", h("span", { class: "muted small" }, t(`etc_${r.etc_source}`))),
        num(r.eac_hours), sign(r.hours_variance), ...(cost ? [num(r.eac_cost, 0), sign(r.cost_variance, 0)] : []), r.baseline_end || "—",
        h("span", { title: r.forecast_note || "" }, r.forecast_end || "—"), r.slip_days ? sign(-r.slip_days, 0) : "0", badge(t(`rag_${RAG[r.status]}`), RAG[r.status]),
        ...(canManage ? [h("button", { class: "btn small secondary", type: "button", onClick: () => editFc(r) }, t("forecast"))] : [])]),
      [h("strong", {}, t("total")), num(v.totals.baseline_hours), num(v.totals.actual_hours), "", num(v.totals.etc_hours), num(v.totals.eac_hours), sign(v.totals.hours_variance),
        ...(cost ? [num(v.totals.eac_cost, 0), sign(v.totals.cost_variance, 0)] : []), "", "", "", "", ...(canManage ? [""] : [])]], t("none")));

  // action log
  const a = { title: h("input", { style: "min-width:240px" }), owner: h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id }, u.full_name))), due: h("input", { type: "date" }), src: h("input", { placeholder: t("action_source_ph") }) };
  const aerr = h("div");
  const setStatus = (x, status) => guarded(null, async () => { await api("PATCH", `/projects/${pid}/actions/${x.id}`, { status }); await render(); });
  const acard = h("div", { class: "card", id: "actions-card" }, h("h2", {}, t("action_log")),
    table([t("title"), t("owner"), t("due_date"), t("source"), t("status"), ""], acts.map(x => [x.title, x.owner || "—", x.due_date ? h("span", { class: x.overdue ? "neg" : "" }, x.due_date) : "—", x.source || "", badge(t(`act_${x.status}`), x.status === "done" ? "GREEN" : x.overdue ? "RED" : "GREY"),
      h("span", { class: "row", style: "gap:6px" }, x.status === "open" && (canManage || x.owner_id === me.id) ? h("button", { class: "btn small", type: "button", onClick: setStatus(x, "done") }, t("mark_done")) : null,
        x.status !== "open" && canManage ? h("button", { class: "btn small secondary", type: "button", onClick: setStatus(x, "open") }, t("reopen")) : null,
        canManage ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { if (!confirm(t("confirm_delete"))) return; await api("DELETE", `/projects/${pid}/actions/${x.id}`); await render(); }) }, t("remove")) : null)]), t("none")),
    canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("title"), a.title), field(t("owner"), a.owner), field(t("due_date"), a.due), field(t("source"), a.src),
      h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(aerr); try { await api("POST", `/projects/${pid}/actions`, { title: a.title.value.trim(), owner_id: a.owner.value ? Number(a.owner.value) : null, due_date: a.due.value || null, source: a.src.value.trim() || null }); toast(t("saved")); await render(); } catch (e) { mount(aerr, errorBox(e)); } }) }, t("add"))) : null, aerr);

  // lessons
  const l = { cat: h("select", {}, LESSON_CATS.map(c => h("option", { value: c }, t(`lc_${c}`)))), imp: h("select", {}, ["negative", "positive"].map(x => h("option", { value: x }, t(`li_${x}`)))), what: h("textarea", { rows: 2 }), rec: h("textarea", { rows: 2 }) };
  const lerr = h("div");
  const lcard = h("div", { class: "card", id: "lessons-card" }, h("h2", {}, t("lessons_title")), h("p", { class: "muted small" }, t("lessons_note"), " ", h("a", { href: "#/lessons" }, t("nav_lessons"))),
    table([t("category"), t("impact_h"), t("what_happened"), t("recommendation"), t("recorded_by"), ""], les.map(x => [t(`lc_${x.category}`), badge(t(`li_${x.impact}`), x.impact === "positive" ? "GREEN" : "AMBER"), x.what_happened, x.recommendation, x.created_by || "",
      canManage ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { if (!confirm(t("confirm_delete"))) return; await api("DELETE", `/projects/${pid}/lessons/${x.id}`); await render(); }) }, t("remove")) : ""]), t("none")),
    h("div", { class: "row", style: "margin-top:12px" }, field(t("category"), l.cat), field(t("impact_h"), l.imp)),
    field(t("what_happened"), l.what), field(t("recommendation"), l.rec),
    h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(lerr); try { await api("POST", `/projects/${pid}/lessons`, { category: l.cat.value, impact: l.imp.value, what_happened: l.what.value.trim(), recommendation: l.rec.value.trim() }); toast(t("saved")); await render(); } catch (e) { mount(lerr, errorBox(e)); } }) }, t("add_lesson")), lerr);

  mount(body, p.state === "execution" || p.state === "closing" ? vcard : null, acard, lcard);
}
