// Project "Brief" tab: upload the project book (Arabic or English; text, DOCX, PDF or scan), review what the AI read, then apply it as a plan.
import { api, fileToB64 } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, num, stat, table, toast } from "../ui.js";

const SECTIONS = ["requirements", "deliverables", "activities", "milestones", "risks", "compliance", "charter", "assumptions"];

export async function briefTab(body, p, { pid, dir, canManage, render }) {
  const out = h("div", { id: "brief-out" });
  if (!canManage) return body.append(h("p", { class: "muted" }, t("none")));
  if (!["tendering", "planning"].includes(p.state)) return body.append(h("div", { class: "card" }, h("p", { class: "muted" }, t("brief_state"))));
  const [docs, drafts] = await Promise.all([api("GET", `/projects/${pid}/documents`), api("GET", `/projects/${pid}/brief`)]);
  const sel = h("select", { id: "brief-doc" }, h("option", { value: "" }, "—"), ...docs.map(d => h("option", { value: d.id }, d.filename)));
  const file = h("input", { type: "file", id: "brief-file", accept: ".pdf,.docx,.txt,.md,.png,.jpg" });
  const text = h("textarea", { id: "brief-text", rows: 5, placeholder: t("brief_paste") });
  const err = h("div");
  const go = guarded(null, async () => {
    mount(err);
    try {
      let document_id = sel.value ? Number(sel.value) : null;
      if (file.files[0]) {
        const d = await api("POST", `/projects/${pid}/documents`, { kind: "scope", filename: file.files[0].name, content_b64: await fileToB64(file.files[0]) });
        document_id = d.id;
      }
      const r = await api("POST", `/projects/${pid}/brief/analyze`, document_id ? { document_id } : { text: text.value });
      toast(t("brief_done"));
      await review(r.draft_id);
    } catch (e) { mount(err, errorBox(e)); }
  });

  async function review(did) {
    const r = await api("GET", `/projects/${pid}/brief/${did}`);
    const dr = r.draft, st = r.staffing;
    const staff = dir.filter(u => ["STAFF", "PM"].includes(u.role) && u.active !== false);
    const rows = dr.activities.map(a => {
      const pr = st[a.code] || {};
      const who = h("select", { "aria-label": a.code }, h("option", { value: "" }, t("brief_unassigned")),
        ...staff.map(u => h("option", { value: u.id, selected: u.id === pr.user_id }, u.full_name)));
      who.value = pr.user_id ? String(pr.user_id) : "";
      return { a, pr, who, name: h("input", { value: a.name, style: "width:100%" }), hrs: h("input", { type: "number", min: 1, value: a.planned_hours, style: "width:80px" }), role: h("input", { value: a.role || "", style: "width:130px" }) };
    });
    const start = h("input", { type: "date", id: "brief-start", value: String(r.start).slice(0, 10) });
    const chk = Object.fromEntries(SECTIONS.map(s => [s, h("input", { type: "checkbox", checked: true, id: `brief-sec-${s}` })]));
    const c = (k) => (dr[k] || []).length;
    const unas = rows.filter(x => !x.pr.user_id).length;
    const aerr = h("div"), res = h("div", { id: "brief-result" });
    const apply = guarded(null, async () => {
      mount(aerr);
      try {
        const draft = { ...dr, activities: rows.map(x => ({ ...x.a, name: x.name.value.trim(), planned_hours: Number(x.hrs.value), role: x.role.value.trim() })) };
        const assignments = Object.fromEntries(rows.map(x => [x.a.code, x.who.value ? Number(x.who.value) : null]));
        const o = await api("POST", `/projects/${pid}/brief/${did}/apply`, { draft, start: start.value, assignments, sections: SECTIONS.filter(s => chk[s].checked) });
        toast(t("brief_applied"));
        mount(res, h("div", { class: "card ok" }, h("h3", {}, t("brief_applied")), table([t("type"), t("rows")], Object.entries(o.created || o).filter(([, v]) => typeof v === "number").map(([k, v]) => [k, num(v, 0)]))));
      } catch (e) { mount(aerr, errorBox(e)); }
    });
    mount(out,
      h("div", { class: "card", id: "brief-review" }, h("h2", {}, dr.meta.name || t("brief_review")),
        h("p", { class: "muted small" }, `${dr.meta.language === "ar" ? "العربية" : "English"} · ${dr.meta.pages} p · ${dr.meta.source?.method || ""} · ${r.status}`),
        ...(dr.warnings || []).map(w => h("p", { class: "warn" }, w)), ...(dr.notes || []).map(w => h("p", { class: "muted small" }, w)),
        h("div", { class: "stats" }, stat(t("requirements"), c("requirements")), stat(t("brief_deliverables"), c("deliverables")), stat(t("brief_tasks"), c("activities")), stat(t("brief_unassigned"), unas), stat(t("brief_phases"), c("phases"))),
        h("p", { class: "muted small" }, (dr.assumptions || []).join(" "))),
      h("div", { class: "card" }, h("h3", {}, t("brief_phases")), table([t("name"), t("brief_months"), t("brief_page")], dr.phases.map(x => [x.name, `${x.start_month}–${x.end_month}`, x.source_page]))),
      h("div", { class: "card" }, h("h3", {}, t("brief_tasks")), h("div", { style: "overflow-x:auto" },
        table([t("code"), t("name"), t("role"), t("planned_hours"), t("brief_page"), t("assignee"), ""], rows.map(x => [x.a.code, x.name, x.role, x.hrs, x.a.page, x.who, x.pr.user_id ? "" : badge(t("brief_unassigned"), "warning")]), t("none")))),
      h("div", { class: "card" }, h("h3", {}, t("requirements")), table([t("code"), t("title"), t("brief_page")], dr.requirements.slice(0, 200).map(x => [x.code, x.title, x.page]), t("none"))),
      h("div", { class: "card" }, h("h3", {}, t("brief_also")), table([t("type"), t("title")], [...dr.team.map(x => [t("tab_team"), `${x.title}${x.min_years ? ` · ${x.min_years}y` : ""}`]), ...dr.risks.map(x => [t("risks"), x.title]), ...dr.compliance.map(x => [x.framework, x.title]), ...dr.terms.map(x => [x.kind, x.text])])),
      h("div", { class: "card" }, h("h3", {}, t("brief_apply")),
        h("div", { class: "row" }, field(t("planned_start"), start), ...SECTIONS.map(s => h("label", { class: "small" }, chk[s], ` ${s}`))),
        p.state !== "planning" ? h("p", { class: "warn" }, t("brief_need_planning")) : null,
        h("button", { class: "btn", id: "brief-apply", type: "button", disabled: p.state !== "planning", onClick: apply }, t("brief_apply")),
        h("button", { class: "btn secondary", type: "button", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/brief/${did}/reject`); mount(out); toast(t("brief_rejected")); }) }, t("brief_reject")), aerr),
      res);
  }

  body.append(h("div", { class: "card", id: "brief-card" }, h("h2", {}, t("tab_brief")), h("p", { class: "muted small" }, t("brief_note")),
    h("div", { class: "row" }, field(t("brief_pick"), sel), field(t("brief_upload"), file)), field(t("brief_or_paste"), text),
    h("button", { class: "btn", id: "brief-go", type: "button", onClick: go }, t("brief_analyze")), err),
    out);
  const open = drafts.find(d => d.status === "draft");
  if (open) await review(open.id);
}
