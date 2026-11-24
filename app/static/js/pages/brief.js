// Project "Brief" tab: upload the project book (Arabic or English; text, DOCX, PDF or scan), review what the AI read, then apply it as a plan.
import { api, fileToB64 } from "../api.js";
import { aiLabel } from "../aistatus.js";
import { withProgress } from "../progress.js";
import { getLang, t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, num, stat, table, toast } from "../ui.js";

const SECTIONS = ["requirements", "deliverables", "activities", "milestones", "risks", "compliance", "charter", "assumptions", "domains"];

export async function briefTab(body, p, { pid, dir, canManage, render }) {
  const out = h("div", { id: "brief-out" });
  if (!canManage) return body.append(h("p", { class: "muted" }, t("none")));
  if (!["tendering", "planning"].includes(p.state)) return body.append(h("div", { class: "card" }, h("p", { class: "muted" }, t("brief_state"))));
  const [docs, drafts] = await Promise.all([api("GET", `/projects/${pid}/documents`), api("GET", `/projects/${pid}/brief`)]);
  const sel = h("select", { id: "brief-doc" }, h("option", { value: "" }, "—"), ...docs.map(d => h("option", { value: d.id }, d.filename)));
  const file = h("input", { type: "file", id: "brief-file", accept: ".pdf,.docx,.txt,.md,.png,.jpg" });
  const text = h("textarea", { id: "brief-text", rows: 5, placeholder: t("brief_paste") });
  const err = h("div"), progBox = h("div", { id: "brief-progress" });
  const go = guarded(null, async () => {
    mount(err);
    try {
      let document_id = sel.value ? Number(sel.value) : null;
      if (file.files[0]) {
        const d = await api("POST", `/projects/${pid}/documents`, { kind: "tender_book", filename: file.files[0].name, content_b64: await fileToB64(file.files[0]) });
        document_id = d.id;
      }
      const r = await withProgress(progBox, (hd) => api("POST", `/projects/${pid}/brief/analyze`, document_id ? { document_id } : { text: text.value }, hd));
      toast(t("brief_done"));
      await review(r.draft_id);
    } catch (e) { mount(err, errorBox(e)); }
  });

  function domainsCard(did, dr) {
    const box = h("div", { class: "card", id: "brief-domains" }, h("h3", {}, t("dom_title")), h("p", { class: "muted small" }, t("dom_note")));
    const COLS = { stakeholders: ["name", "organisation", "role", "power", "interest", "engagement"], communication: ["audience", "information", "method", "frequency"],
      quality: ["title", "kind", "note"], cost: ["name", "hours", "note"], procurement: ["kind", "text"], change: ["text"] };
    const NUM = new Set(["power", "interest", "hours"]);
    const names = Object.keys(COLS);
    const drawOne = (name) => {
      const dom = dr.domains[name];
      const rows = dom.items.map(it => ({ it, inp: COLS[name].map(k => { let i; if (NUM.has(k)) { i = h("input", { value: it[k] ?? "", "aria-label": k, type: "number" }); } else { i = h("textarea", { rows: 1, dir: "auto", class: "ta", "aria-label": k, style: "width:100%" }); i.value = it[k] ?? ""; i.addEventListener("input", () => autosize(i)); requestAnimationFrame(() => autosize(i)); } return [k, i]; }) }));
      const fb = h("input", { placeholder: t("dom_feedback"), id: `dom-fb-${name}`, style: "width:100%" });
      const hist = dom.history.slice(-3).reverse();
      const post = async (action, extra = {}) => {
        const r = await api("POST", `/projects/${pid}/brief/${did}/domains/${name}`, { action, ...extra });
        dr.domains[name] = { status: r.status, items: r.items, history: r.history };
        wrap.replaceWith(drawOne(name));
      };
      const wrap = h("details", { class: "dom", id: `dom-${name}`, open: dom.status === "proposed" },
        h("summary", {}, `${t("dom_" + name)} · `, badge(t("dom_s_" + dom.status), dom.status === "proposed" ? "warning" : "ok"), ` · ${dom.items.length}`),
        h("div", {}, ...(rows.length ? rows.map(r => h("div", { class: "item" }, ...r.inp.map(([k, i]) => h("label", { class: `f f-${NUM.has(k) ? "s" : ["engagement", "information", "text", "note"].includes(k) ? "xl" : "m"}` }, h("span", { class: "fl" }, t("dom_f_" + k)), i)))) : [h("p", { class: "muted small" }, t("none"))])),
        h("div", { class: "row" },
          h("button", { class: "btn small", type: "button", id: `dom-accept-${name}`, onClick: guarded(null, () => post("accept")) }, t("dom_accept")),
          h("button", { class: "btn small secondary", type: "button", id: `dom-save-${name}`, onClick: guarded(null, () => post("modify", { items: rows.map(r => Object.fromEntries(r.inp.map(([k, i]) => [k, NUM.has(k) ? Number(i.value) : i.value]))) })) }, t("dom_save"))),
        h("div", { class: "row" }, fb, h("button", { class: "btn small secondary", type: "button", id: `dom-reject-${name}`, onClick: guarded(null, async () => { if (!fb.value.trim()) return toast(t("dom_need_feedback")); await post("reject", { feedback: fb.value.trim() }); }) }, t("dom_reject"))),
        ...hist.map(x => h("details", { class: "small muted" }, h("summary", {}, `${x.at.slice(0, 16).replace("T", " ")} · ${x.action}${x.feedback ? " · " + x.feedback : ""}`), h("pre", { class: "diff" }, (x.diff || []).join("\n") || "—"))));
      return wrap;
    };
    names.forEach(n => box.append(drawOne(n)));
    return box;
  }

  // ---- editable lists: every item is a card with wrapped text boxes (Arabic reads right-to-left), plus add / delete ----
  const autosize = (el) => { if (!el.offsetParent) return; el.style.height = "auto"; el.style.height = Math.min(400, el.scrollHeight + 2) + "px"; };
  // translation of an extracted field into the viewer's language (only shown while the original text is unchanged)
  let TR = {};
  const trLine = (key, value) => { const x = TR[key]; return x && x.src === value && x.t ? h("div", { class: "tr muted small", dir: "auto" }, "↳ ", x.t) : null; };
  function editList(dr, key, fields, blank, { title, addLabel, onChange } = {}) {
    const box = h("div", { class: "elist", id: `el-${key}` });
    const draw = () => {
      const items = dr[key] || (dr[key] = []);
      mount(box,
        h("div", { class: "row", style: "justify-content:space-between;align-items:center" }, h("h3", {}, `${title} · ${items.length}`),
          h("button", { class: "btn small secondary", type: "button", id: `el-add-${key}`, onClick: () => { items.push(blank(items)); onChange?.(); draw(); } }, `+ ${addLabel}`)),
        items.length ? null : h("p", { class: "muted small" }, t("none")),
        ...items.map((it, i) => h("div", { class: "item", "data-i": i },
          ...fields.map(([k, lbl, size, kind, opts]) => {
            let inp;
            if (kind === "select") {
              inp = h("select", { "aria-label": t(lbl) }, ...opts(dr).map(([v, txt]) => h("option", { value: v, selected: String(it[k] ?? "") === String(v) }, txt)));
              inp.value = String(it[k] ?? "");
              inp.addEventListener("change", () => { it[k] = isNaN(Number(inp.value)) || inp.value === "" ? inp.value : Number(inp.value); onChange?.(); });
            } else if (kind === "num") {
              inp = h("input", { type: "number", min: 0, step: "any", value: it[k] ?? "", "aria-label": t(lbl) });
              inp.addEventListener("input", () => { it[k] = inp.value === "" ? null : Number(inp.value); onChange?.(); });
            } else {
              inp = h("textarea", { rows: 1, dir: "auto", "aria-label": t(lbl), class: "ta" }); inp.value = it[k] ?? "";
              inp.addEventListener("input", () => { it[k] = inp.value; autosize(inp); });
              requestAnimationFrame(() => autosize(inp));
            }
            return h("label", { class: `f f-${size}` }, h("span", { class: "fl" }, t(lbl)), inp, kind === "num" || kind === "select" ? null : trLine(`${key}.${i}.${k}`, it[k] ?? ""));
          }),
          h("button", { class: "btn small danger del", type: "button", "aria-label": t("delete"), onClick: () => { items.splice(i, 1); onChange?.(); draw(); } }, t("delete")))));
    };
    draw();
    return box;
  }
  const phaseOpts = (dr) => [["", "—"], ...(dr.phases || []).map(p => [p.n, `${p.n}. ${p.name}`])];
  const nextCode = (items, pre) => { let n = items.length + 1; const have = new Set(items.map(x => x.code)); while (have.has(`${pre}${String(n).padStart(2, "0")}`)) n++; return `${pre}${String(n).padStart(2, "0")}`; };

  async function review(did) {
    const r = await api("GET", `/projects/${pid}/brief/${did}`);
    const dr = r.draft, st = { ...r.staffing };
    const vl = getLang(), docLang = dr.meta.language === "ar" ? "ar" : "en";
    TR = (dr.translations || {})[vl] || {};
    const trBox = h("div", { id: "tr-box", class: "small" });
    const staff = dir.filter(u => ["STAFF", "PM"].includes(u.role) && u.active !== false);
    const start = h("input", { type: "date", id: "brief-start", value: String(r.start).slice(0, 10) });
    const chk = Object.fromEntries(SECTIONS.map(s => [s, h("input", { type: "checkbox", checked: true, id: `brief-sec-${s}` })]));
    const c = (k) => (dr[k] || []).length;
    const aerr = h("div"), res = h("div", { id: "brief-result" });
    const assign = {};                                     // task code -> user id chosen by the reviewer (null = unassigned)
    (dr.activities || []).forEach(a => { assign[a.code] = (st[a.code] || {}).user_id || null; });
    const stats = h("div", { class: "grid" });
    const redrawStats = () => mount(stats, stat(t("requirements"), c("requirements")), stat(t("brief_deliverables"), c("deliverables")), stat(t("brief_tasks"), c("activities")),
      stat(t("brief_unassigned"), (dr.activities || []).filter(a => !assign[a.code]).length), stat(t("brief_phases"), c("phases")));
    redrawStats();
    const taskBox = h("div", { id: "task-box" });
    const drawTasks = () => {
      const items = dr.activities || [];
      mount(taskBox,
        h("div", { class: "row", style: "justify-content:space-between;align-items:center" }, h("h3", {}, `${t("brief_tasks")} · ${items.length}`),
          h("span", { class: "row", style: "gap:8px" },
            h("button", { class: "btn small secondary", type: "button", id: "brief-resuggest", onClick: guarded(null, async () => {
              const pr = await api("POST", `/projects/${pid}/brief/${did}/staffing`, { activities: items, start: start.value });
              items.forEach(a => { assign[a.code] = (pr[a.code] || {}).user_id || null; st[a.code] = pr[a.code] || {}; }); drawTasks(); redrawStats(); toast(t("brief_resuggested"));
            }) }, t("brief_resuggest")),
            h("button", { class: "btn small secondary", type: "button", id: "el-add-activities", onClick: () => {
              const ph = (dr.phases || [])[0] || { n: 1, start_month: 0, end_month: 1 };
              items.push({ code: nextCode(items, `P${ph.n}-`), name: "", description: "", phase: ph.n, planned_hours: 40, start_month: ph.start_month, end_month: ph.end_month, role: "", page: null, estimate: true });
              drawTasks(); redrawStats();
            } }, `+ ${t("brief_add_task")}`))),
        items.length ? null : h("p", { class: "muted small" }, t("none")),
        ...items.map((a, i) => {
          const who = h("select", { "aria-label": t("assignee") }, h("option", { value: "" }, t("brief_unassigned")), ...staff.map(u => h("option", { value: u.id }, u.full_name)));
          who.value = assign[a.code] ? String(assign[a.code]) : "";
          who.addEventListener("change", () => { assign[a.code] = who.value ? Number(who.value) : null; redrawStats(); });
          const field_ = (k, lbl, size, kind) => {
            const inp = kind === "num" ? h("input", { type: "number", min: 0, step: "any", value: a[k] ?? "" }) : h("textarea", { rows: 1, dir: "auto", class: "ta" });
            if (kind !== "num") { inp.value = a[k] ?? ""; requestAnimationFrame(() => autosize(inp)); }
            inp.setAttribute("aria-label", t(lbl));
            inp.addEventListener("input", () => { a[k] = kind === "num" ? Number(inp.value) : inp.value; if (kind !== "num") autosize(inp); });
            return h("label", { class: `f f-${size}` }, h("span", { class: "fl" }, t(lbl)), inp, kind === "num" ? null : trLine(`activities.${i}.${k}`, a[k] ?? ""));
          };
          const ph = h("select", { "aria-label": t("brief_phase") }, ...phaseOpts(dr).slice(1).map(([v, txt]) => h("option", { value: v }, txt)));
          ph.value = String(a.phase);
          ph.addEventListener("change", () => { a.phase = Number(ph.value); const p0 = dr.phases.find(x => x.n === a.phase); if (p0) { a.start_month = p0.start_month; a.end_month = p0.end_month; } });
          return h("div", { class: "item", "data-i": i },
            h("label", { class: "f f-s" }, h("span", { class: "fl" }, t("code")), h("input", { value: a.code, "aria-label": t("code"), onInput: (e) => { const old = a.code; a.code = e.target.value.trim(); assign[a.code] = assign[old]; } })),
            field_("name", "name", "l", "text"), field_("role", "role", "m", "text"), field_("planned_hours", "planned_hours", "s", "num"),
            h("label", { class: "f f-m" }, h("span", { class: "fl" }, t("brief_phase")), ph),
            h("label", { class: "f f-m" }, h("span", { class: "fl" }, t("assignee")), who),
            h("span", { class: "f f-s muted small" }, a.page ? `${t("brief_page")} ${a.page}` : ""),
            h("button", { class: "btn small danger del", type: "button", "aria-label": t("delete"), onClick: () => { items.splice(i, 1); drawTasks(); redrawStats(); } }, t("delete")));
        }));
    };
    drawTasks();
    const apply = guarded(null, async () => {
      mount(aerr);
      try {
        const assignments = Object.fromEntries((dr.activities || []).map(x => [x.code, assign[x.code] || null]));
        const o = await api("POST", `/projects/${pid}/brief/${did}/apply`, { draft: dr, start: start.value, assignments, sections: SECTIONS.filter(s => chk[s].checked) });
        toast(t("brief_applied"));
        mount(res, h("div", { class: "card ok" }, h("h3", {}, t("brief_applied")), table([t("type"), t("rows")], Object.entries(o.created || o).filter(([, v]) => typeof v === "number").map(([k, v]) => [k, num(v, 0)]))));
      } catch (e) { mount(aerr, errorBox(e)); }
    });
    const trBanner = () => {
      if (vl === docLang) return null;
      const have = Object.keys(TR).length > 0;
      return h("div", { class: "card", id: "tr-note", style: "margin:8px 0" }, h("p", { class: "small" }, have ? t("tr_have") : t("tr_none").replace("{lang}", docLang === "ar" ? "العربية" : "English")),
        h("button", { class: "btn small secondary", type: "button", id: "tr-go", onClick: guarded(null, async () => {
          const x = await api("POST", `/projects/${pid}/brief/${did}/translate`, { target: vl });
          if (x.status !== "ok") { mount(trBox, h("p", { class: "warn" }, `${t("tr_unavailable")} ${x.reason || ""}`)); return; }
          dr.translations = x.translations; TR = x.translations[vl] || {}; toast(t("tr_done")); await review(did);
        }) }, t("tr_translate")), trBox);
    };
    const PRI = () => [["must", t("brief_must")], ["should", t("brief_should")]];
    const sec = (id, titleKey, ...kids) => h("details", { class: "card sec", id, open: id === "sec-tasks" && (dr.activities || []).length <= 15 }, h("summary", {}, h("h3", { style: "display:inline" }, t(titleKey))), ...kids);
    out.addEventListener("toggle", (ev) => { if (ev.target.open) ev.target.querySelectorAll("textarea.ta").forEach(autosize); }, true);
    mount(out,
      h("div", { class: "card", id: "brief-review" }, h("h2", {}, dr.meta.name || t("brief_review")), h("p", {}, aiLabel(), " ", h("span", { class: "muted small" }, t("ai_rules_note"))),
        h("p", { class: "muted small" }, `${t(dr.meta.language === "ar" ? "lang_name_ar" : "lang_name_en")} · ${dr.meta.pages} ${t("bk_pages")} · ${dr.meta.source?.method || ""} · ${r.status}`),
        ...(dr.warnings || []).map(w => h("p", { class: "warn" }, w)), ...(dr.notes || []).map(w => h("p", { class: "muted small" }, w)),
        trBanner(), stats, h("p", { class: "muted small" }, t("brief_edit_hint")), h("p", { class: "muted small" }, (dr.assumptions || []).join(" "))),
      sec("sec-phases", "brief_phases", editList(dr, "phases", [["name", "name", "l", "text"], ["start_month", "brief_from_month", "s", "num"], ["end_month", "brief_to_month", "s", "num"]],
        (items) => ({ n: Math.max(0, ...items.map(x => x.n)) + 1, name: "", start_month: 0, end_month: 1, months: 1, source_page: null }), { title: t("brief_phases"), addLabel: t("brief_add_phase"), onChange: () => { (dr.phases || []).forEach(p => { p.months = Math.max(1, (p.end_month || 0) - (p.start_month || 0)); }); redrawStats(); } })),
      sec("sec-tasks", "brief_tasks", taskBox),
      sec("sec-req", "requirements", editList(dr, "requirements", [["code", "code", "s", "text"], ["title", "title", "l", "text"], ["priority", "brief_priority", "m", "select", PRI], ["phase", "brief_phase", "m", "select", phaseOpts], ["text", "description", "xl", "text"]],
        (items) => ({ code: `R-${String(items.length + 1).padStart(3, "0")}`, title: "", text: "", page: null, priority: "should", phase: null, section: "added" }), { title: t("requirements"), addLabel: t("brief_add_req"), onChange: redrawStats })),
      sec("sec-deliv", "brief_deliverables", editList(dr, "deliverables", [["code", "code", "s", "text"], ["name", "name", "l", "text"], ["phase", "brief_phase", "m", "select", phaseOpts], ["description", "description", "xl", "text"]],
        (items) => ({ code: `D${(items.length + 1)}`, name: "", description: "", phase: ((dr.phases || [])[0] || {}).n || 1, page: null }), { title: t("brief_deliverables"), addLabel: t("brief_add_deliv"), onChange: redrawStats })),
      sec("sec-risks", "risks", editList(dr, "risks", [["title", "title", "l", "text"], ["category", "category", "m", "text"], ["probability", "probability", "s", "num"], ["impact", "impact", "s", "num"], ["response", "brief_response", "xl", "text"]],
        () => ({ title: "", category: "", probability: 3, impact: 3, response: "" }), { title: t("risks"), addLabel: t("brief_add_risk") })),
      sec("sec-team", "tab_team", editList(dr, "team", [["title", "role", "l", "text"], ["min_years", "brief_min_years", "s", "num"]], () => ({ title: "", min_years: null, location: null }), { title: t("tab_team"), addLabel: t("brief_add_role") })),
      sec("sec-comp", "compliance", editList(dr, "compliance", [["framework", "brief_framework", "m", "text"], ["title", "title", "l", "text"]], () => ({ framework: "", title: "", page: null }), { title: t("compliance"), addLabel: t("brief_add_comp") })),
      domainsCard(did, dr),
      h("div", { class: "card" }, h("h3", {}, t("brief_apply")),
        h("div", { class: "row" }, field(t("planned_start"), start), ...SECTIONS.map(s => h("label", { class: "small check" }, chk[s], ` ${s}`))),
        p.state !== "planning" ? h("p", { class: "warn" }, t("brief_need_planning")) : null,
        h("button", { class: "btn", id: "brief-apply", type: "button", disabled: p.state !== "planning", onClick: apply }, t("brief_apply")),
        h("button", { class: "btn secondary", type: "button", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/brief/${did}/reject`); mount(out); toast(t("brief_rejected")); }) }, t("brief_reject")), aerr),
      res);
  }

  body.append(h("div", { class: "card", id: "brief-card" }, h("h2", {}, t("tab_brief")), h("p", { class: "muted small" }, t("brief_note")),
    h("div", { class: "row" }, field(t("brief_pick"), sel), field(t("brief_upload"), file)), field(t("brief_or_paste"), text),
    h("button", { class: "btn", id: "brief-go", type: "button", onClick: go }, t("brief_analyze")), err, progBox),
    out);
  const open = drafts.find(d => d.status === "draft");
  if (open) await review(open.id);
}
