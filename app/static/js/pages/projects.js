import { xlsxBtn } from "./importer.js";
import { api, downloadCsv, openReport } from "../api.js";
import { getLang, st, t } from "../i18n.js";
import { details } from "./details.js";
import { plan } from "./plan.js";
import { control } from "./control.js";
import { requestCard, team } from "./team.js";
import { decide, decisionList, outcomeBadge } from "../decide.js";
import { scope } from "./scope.js";
import { agile } from "./agile.js";
import { engagementCard, reservesCard, riskResponseCards } from "./projdepth.js";
import { procurement } from "./projprocurement.js";
import { compliance } from "./projcompliance.js";
import { briefTab } from "./brief.js";
import { askText, badge, modal, errorBox, field, guarded, h, mount, num, stat, table, toast, today } from "../ui.js";

const MANAGE = ["PM", "PMO", "ADMIN"];
const NEXT = { tendering: ["planning", "archived"], execution: ["closing", "on_hold"], closing: ["archived"], planning: ["on_hold"], on_hold: [] };

export default async function (root, { me, arg }) {
  if (arg) return detail(root, me, Number(arg));
  const canManage = MANAGE.includes(me.role);
  async function render() {
    const [all, dirAll, progs, gov] = await Promise.all([api("GET", "/projects"), api("GET", "/directory"), me.role === "STAFF" ? [] : api("GET", "/programs").catch(() => []), api("GET", "/config/governance")]);
    const viaIntake = gov.intake_required && me.role === "PM";
    const F = (render.F = render.F || { state: "", pm: "", program: "" });
    const list = all.filter(p => (!F.state || p.state === F.state) && (!F.pm || String(p.pm_id) === F.pm) && (!F.program || String(p.program_id) === F.program));
    const sel = (key, opts) => h("select", { onChange: (ev) => { F[key] = ev.target.value; render(); } }, h("option", { value: "" }, t("all")), opts.map(([v, l]) => h("option", { value: v, selected: F[key] === String(v) }, l)));
    const pmName = (id) => (dirAll.find(u => u.id === id) || {}).full_name || "—";
    const num_ = h("input", { required: true }), name = h("input", { required: true, style: "min-width:220px" });
    const state = h("select", {}, h("option", { value: "planning" }, t("planning")), h("option", { value: "tendering" }, t("tendering")));
    const start = h("input", { type: "date" }), end = h("input", { type: "date" });
    const budget = h("input", { type: "number", min: "0", style: "width:130px" });
    const client = h("input"), sponsor = h("input");
    const ccy = h("input", { value: "SAR", maxlength: "3", style: "width:70px" });
    const err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("create"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try {
        await api("POST", "/projects", { number: num_.value.trim(), name: name.value.trim(), state: state.value, planned_start: start.value || null,
          planned_end: end.value || null, budget_ceiling: budget.value ? Number(budget.value) : null, currency: ccy.value.toUpperCase(), client: client.value.trim() || null, sponsor: sponsor.value.trim() || null });
        toast(t("saved")); await render();
      } catch (e) { mount(err, errorBox(e)); }
    }));
    mount(root, h("h1", {}, t("projects")),
      viaIntake ? h("div", { class: "card" }, h("h2", {}, t("new_project")), h("p", {}, t("intake_note"), " ", h("a", { class: "btn small", href: "#/proposals" }, t("submit_proposal")))) : null,
      canManage && !viaIntake ? h("div", { class: "card" }, h("h2", {}, t("new_project")),
        h("div", { class: "row" }, field(t("number"), num_), field(t("name"), name), field(t("state"), state), field(t("planned_start"), start), field(t("planned_end"), end), field(t("budget"), budget), field(t("currency"), ccy), field(t("client"), client), field(t("sponsor"), sponsor), btn), err) : null,
      me.role === "STAFF" ? null : h("div", { class: "card" }, h("div", { class: "row" }, field(t("filter_state"), sel("state", [...new Set(all.map(p => p.state))].map(x => [x, t(x)]))),
        field(t("filter_pm"), sel("pm", [...new Set(all.map(p => p.pm_id))].map(x => [x, pmName(x)]))), progs.length ? field(t("filter_program"), sel("program", progs.map(g => [g.id, g.code]))) : null,
        h("button", { class: "btn secondary small", type: "button", onClick: () => { render.F = { state: "", pm: "", program: "" }; render(); } }, t("clear_filters")))),
      h("div", { class: "card" }, table([t("number"), t("name"), t("manager"), t("state"), t("planned_start"), t("planned_end"), ""],
        list.map(p => [p.number, p.name, pmName(p.pm_id), badge(t(p.state), "gold"), p.planned_start || "—", p.planned_end || "—",
          h("span", {}, h("a", { href: `#/projects/${p.id}` }, t("open")), " ", ["execution", "closing"].includes(p.state) && me.role !== "STAFF" ? h("a", { href: `#/dashboard/${p.id}` }, t("nav_dashboard")) : null)]), t("none"))));
  }
  await render();
}

async function detail(root, me, pid) {
  let tab = "overview";
  const canManage = MANAGE.includes(me.role);
  const dir = await api("GET", "/directory");
  const dirById = Object.fromEntries(dir.map(u => [u.id, u]));

  async function render() {
    const p = await api("GET", `/projects/${pid}`);
    const tabs = ["overview", "details", "scope", "agile", "compliance", "procurement", "team", "brief", "plan", "progress", "control", "risks", "costs", "changes", "allocations", "benefits", "closure", "ai", "reports"];
    const show = (x) => (x === "costs" || x === "allocations" || x === "procurement") ? (me.role !== "STAFF") : x === "closure" ? ["closing", "archived"].includes(p.state) : x === "ai" ? canManage : x === "brief" ? canManage && ["tendering", "planning"].includes(p.state) : x === "agile" ? p.project_type !== "predictive" : true;
    const body = h("div");
    mount(root,
      h("p", {}, h("a", { href: "#/projects" }, `← ${t("projects")}`)),
      h("h1", {}, `${p.number} · ${p.name} `, badge(t(p.state), "gold")),
      h("p", {}, h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => openReport(`/projects/${pid}/report.html`)) }, t("print_report"))),
      h("div", { class: "tabs", role: "tablist" }, tabs.filter(show).map(x =>
        h("button", { class: tab === x ? "active" : "", role: "tab", onClick: () => { tab = x; render(); } }, t(`tab_${x}`)))),
      body);
    try {
      if (tab === "overview") await overview(body, p);
      else if (tab === "details") { await details(body, p, { pid, me, dir, canManage, render }); body.append(await engagementCard({ pid, canManage, render, p })); }
      else if (tab === "scope") await scope(body, p, { pid, me, dir, canManage, render });
      else if (tab === "compliance") await compliance(body, p, { pid, dir, canManage, render });
      else if (tab === "procurement") await procurement(body, p, { pid, dir, canManage, render });
      else if (tab === "agile") await agile(body, p, { pid, me, dir, canManage, render });
      else if (tab === "team") await team(body, p, { pid, me, dir, canManage, render });
      else if (tab === "brief") await briefTab(body, p, { pid, dir, canManage, render });
      else if (tab === "plan") await plan(body, p, { pid, dir, canManage, render });
      else if (tab === "progress") await progress(body, p);
      else if (tab === "control") await control(body, p, { pid, me, dir, canManage, render });
      else if (tab === "risks") { await risks(body, p); body.append(...await riskResponseCards({ pid, dir, canManage, render, p })); }
      else if (tab === "costs") { await costs(body, p); body.append(await reservesCard({ pid, me, p, render, canManage })); }
      else if (tab === "changes") await changes(body, p);
      else if (tab === "allocations") await allocations(body, p);
      else if (tab === "benefits") await benefits(body, p);
      else if (tab === "closure") await closure(body, p);
      else if (tab === "ai") await aiTab(body, p);
      else await reports(body, p);
    } catch (e) { mount(body, errorBox(e)); }
  }

  async function overview(body, p) {
    const acts = p.activities;
    const code = h("input", { style: "width:100px" }), name = h("input"), hrs = h("input", { type: "number", min: "1", style: "width:90px" });
    const bc = h("input", { type: "number", min: "0", style: "width:120px" }), ps = h("input", { type: "date" }), pe = h("input", { type: "date" });
    const err = h("div");
    const add = h("button", { class: "btn", type: "button" }, t("add"));
    add.addEventListener("click", guarded(add, async () => {
      mount(err);
      try {
        await api("POST", `/projects/${pid}/activities`, { code: code.value.trim(), name: name.value.trim(), planned_hours: Number(hrs.value),
          baseline_cost: bc.value ? Number(bc.value) : null, planned_start: ps.value || null, planned_end: pe.value || null });
        toast(t("activity_added")); await render();
      } catch (e) { mount(err, errorBox(e)); }
    }));
    const who = h("select", {}, dir.map(u => h("option", { value: u.id }, `${u.full_name} (${u.staff_id})`)));
    const assignBtn = h("button", { class: "btn secondary", type: "button" }, t("assign_staff"));
    assignBtn.addEventListener("click", guarded(assignBtn, async () => {
      try { await api("POST", `/projects/${pid}/assignments`, { user_id: Number(who.value) }); toast(t("staff_assigned")); } catch (e) { toast(e.lines().join(" · "), "error"); }
    }));
    const moves = (NEXT[p.state] || []).map(s => h("button", { class: "btn secondary small", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/transition`, { to_state: s }); toast(t("state_changed")); await render(); }) }, `${t("transition")} ${t(s)}`));
    let progCard = null;
    if (["PMO", "ADMIN"].includes(me.role)) {
      const progs = await api("GET", "/programs");
      const sel = h("select", {}, h("option", { value: "" }, t("no_program")), progs.map(g => h("option", { value: g.id, selected: g.id === p.program_id }, `${g.code} · ${g.name}`)));
      progCard = h("div", { class: "card" }, h("h2", {}, t("program")), h("div", { class: "row" }, sel,
        h("button", { class: "btn secondary small", onClick: guarded(null, async () => { await api("PUT", `/projects/${pid}/program`, { program_id: sel.value ? Number(sel.value) : null }); toast(t("saved")); }) }, t("save"))));
    }
    const gates = await api("GET", `/projects/${pid}/gates`);
    const tpls = canManage && ["tendering", "planning"].includes(p.state) ? await api("GET", "/templates").catch(() => []) : [];
    const tsel = h("select", {}, tpls.filter(x => x.active).map(x => h("option", { value: x.id }, `${x.code} · ${x.name}`))), terr = h("div");
    const tplCard = tpls.some(x => x.active) ? h("div", { class: "card", id: "apply-template" }, h("h2", {}, t("apply_template")), h("p", { class: "muted small" }, t("apply_template_note")),
      h("div", { class: "row" }, field(t("template"), tsel), h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(terr); try { const r = await api("POST", `/projects/${pid}/apply-template/${tsel.value}`); toast(`${t("saved")}: ${r.activities} ${t("activities")}, ${r.milestones} ${t("milestones")}, ${r.risks} ${t("risks")}`); await render(); } catch (e) { mount(terr, errorBox(e)); } }) }, t("apply"))), terr) : null;
    const log_ = await api("GET", `/decision-log?project_id=${pid}`);
    const gerr = h("div"), gnote = h("textarea", { rows: 2 });
    const pendingG = gates.reviews.find(r => r.gate === gates.next_gate && ["pending", "deferred"].includes(r.status));
    const gateCard = (gates.next_gate || gates.reviews.length) ? h("div", { class: "card", id: "gate-card" }, h("h2", {}, t("stage_gate"), " ", gates.required ? badge(t("required"), "AMBER") : badge(t("optional"), "GREY")),
      gates.next_gate ? [h("p", {}, h("strong", {}, t(`gate_${gates.next_gate}`)), " ", gates.next_passed ? badge(t("ps_approved"), "GREEN") : pendingG ? outcomeBadge(pendingG.status) : null),
        h("ul", { class: "checks" }, gates.preview.map(c => h("li", { class: c.ok ? "ok" : "bad" }, `${c.ok ? "✓" : "✗"} ${t(`gc_${c.key}`)}${c.detail ? ` (${c.detail})` : ""}`))),
        canManage && !gates.next_passed && !pendingG ? h("div", {}, field(t("note"), gnote), h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(gerr); try { await api("POST", `/projects/${pid}/gates`, { note: gnote.value.trim() || null }); toast(t("saved")); await render(); } catch (e) { mount(gerr, errorBox(e)); } }) }, t("request_gate")), gerr) : null] : null,
      gates.reviews.length ? [h("h3", {}, t("gate_history")), gates.reviews.map(r => h("div", { class: "small", style: "margin-bottom:8px" }, h("strong", {}, t(`gate_${r.gate}`)), " ", outcomeBadge(r.status), ` · ${r.requested_by || ""} · ${(r.created_at || "").slice(0, 10)}`, decisionList(r.decisions)))] : null) : null;
    const logCard = log_.length ? h("div", { class: "card", id: "decision-log" }, h("h2", {}, t("decision_log")),
      table([t("date"), t("title"), t("outcome"), t("rationale"), t("conditions"), t("decided_by")], log_.map(r => [(r.decided_at || "").slice(0, 10), r.title, t(`oc_${r.outcome}`), r.rationale || "", r.conditions || "", r.decided_by || ""]))) : null;
    mount(body,
      h("div", { class: "grid", style: "margin-bottom:16px" }, stat(t("state"), t(p.state)), stat(t("baseline_version"), p.baseline_version), stat(t("planned_start"), p.planned_start || "—"), stat(t("planned_end"), p.planned_end || "—")),
      progCard, tplCard, gateCard,
      canManage ? h("div", { class: "card" }, h("div", { class: "row" }, moves,
        p.state === "planning" ? h("button", { class: "btn gold small", onClick: guarded(null, async () => { if (!confirm(t("confirm_lock"))) return; await api("POST", `/projects/${pid}/baseline/lock`); toast(t("baseline_locked")); await render(); }) }, t("lock_baseline")) : null)) : null,
      h("div", { class: "card" }, h("h2", {}, t("activities")),
        table([t("code"), t("name"), t("planned_hours"), p.activities.some(a => "baseline_cost" in a) ? t("baseline_cost") : null, t("planned_start"), t("planned_end"), t("locked"), canManage && p.state === "planning" ? "" : null].filter(x => x !== null),
          acts.filter(a => a.phase === "execution").map(a => [a.code, a.name, num(a.planned_hours), ..."baseline_cost" in a ? [num(a.baseline_cost, 0)] : [], a.planned_start || "—", a.planned_end || "—", a.locked ? "✓" : "",
            ...(canManage && p.state === "planning" ? [a.locked ? "" : h("span", { class: "row", style: "gap:6px" }, h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, () => editActivity(a)) }, t("edit")),
              h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { if (!confirm(t("confirm_delete"))) return; await api("DELETE", `/projects/${pid}/activities/${a.id}`); await render(); }) }, t("remove")))] : [])]), t("none"))),
      canManage && p.state === "planning" ? h("div", { class: "card" }, h("h2", {}, t("add_activity")),
        h("div", { class: "row" }, field(t("code"), code), field(t("name"), name), field(t("planned_hours"), hrs), field(t("baseline_cost"), bc), field(t("planned_start"), ps), field(t("planned_end"), pe), add), err) : null,
      canManage ? h("div", { class: "card" }, h("h2", {}, t("assigned_staff")), h("div", { class: "row" }, field(t("staff"), who), assignBtn)) : null, logCard);
  }

  async function editActivity(a) {
    const n = h("input", { value: a.name }), hr = h("input", { type: "number", min: "1", value: a.planned_hours }), bcst = h("input", { type: "number", min: "0", value: a.baseline_cost ?? "" });
    const ps = h("input", { type: "date", value: a.planned_start || "" }), pe = h("input", { type: "date", value: a.planned_end || "" }), e = h("div");
    modal({ title: `${t("edit")} ${a.code}`, body: h("div", {}, h("div", { class: "row" }, field(t("name"), n), field(t("planned_hours"), hr), field(t("baseline_cost"), bcst)), h("div", { class: "row", style: "margin-top:10px" }, field(t("planned_start"), ps), field(t("planned_end"), pe)), e),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() },
        { label: t("save"), onClick: async (c) => { try { await api("PATCH", `/projects/${pid}/activities/${a.id}`, { name: n.value.trim(), planned_hours: Number(hr.value), baseline_cost: bcst.value === "" ? null : Number(bcst.value), planned_start: ps.value || null, planned_end: pe.value || null }); c(); toast(t("saved")); await render(); } catch (x) { mount(e, errorBox(x)); } } }] });
  }

  async function aiTab(body, p) {
    const [stt, drafts] = await Promise.all([api("GET", "/ai/status"), api("GET", `/ai/drafts?project_id=${pid}`)]);
    const banner = stt.mode === "stub" ? h("div", { class: "warn" }, t("ai_stub_banner"))
      : h("div", { class: stt.in_kingdom ? "card" : "warn" }, `${stt.model} @ ${stt.host} · ${stt.in_kingdom ? t("ai_in_kingdom") : t("ai_not_in_kingdom")}`);
    const brief = h("textarea", { rows: "6", style: "width:100%", placeholder: t("ai_brief_ph") });
    const area = h("div"), err = h("div");
    const gen = h("button", { class: "btn", type: "button" }, t("ai_generate_plan"));
    gen.addEventListener("click", guarded(gen, async () => {
      mount(err);
      try { const d = await api("POST", "/ai/plans", { project_id: pid, brief: brief.value, lang: getLang() }); showPlan(d); } catch (e) { mount(err, errorBox(e)); }
    }));
    function showPlan(d) {
      const rows = d.output.activities.map(a => ({ inc: h("input", { type: "checkbox", checked: true }), code: h("input", { value: a.code, style: "width:80px" }), name: h("input", { value: a.name, style: "min-width:260px" }), hrs: h("input", { type: "number", min: "1", value: a.planned_hours, style: "width:90px" }) }));
      const e2 = h("div");
      mount(area, h("div", { class: "card" }, h("h2", {}, t("ai_review_plan")), h("p", { class: "muted small" }, d.mode === "stub" ? t("ai_stub_note") : t("ai_draft_note")),
        table(["", t("code"), t("name"), t("planned_hours")], rows.map(r => [r.inc, r.code, r.name, r.hrs]), t("none")),
        (d.output.assumptions || []).length ? h("ul", {}, d.output.assumptions.map(x => h("li", {}, x))) : null,
        h("div", { class: "row" },
          h("button", { class: "btn", type: "button", onClick: guarded(null, async () => {
            mount(e2);
            try { await api("POST", `/ai/drafts/${d.id}/apply`, { activities: rows.filter(r => r.inc.checked).map(r => ({ code: r.code.value.trim(), name: r.name.value.trim(), planned_hours: Number(r.hrs.value) })) }); toast(t("ai_applied")); tab = "overview"; await render(); }
            catch (e) { mount(e2, errorBox(e)); }
          }) }, t("ai_apply")),
          h("button", { class: "btn secondary", type: "button", onClick: guarded(null, async () => { await api("POST", `/ai/drafts/${d.id}/reject`); mount(area); await render(); }) }, t("reject"))), e2));
    }
    const nar = h("div");
    const narBtn = h("button", { class: "btn secondary", type: "button" }, t("ai_generate_narrative"));
    narBtn.addEventListener("click", guarded(narBtn, async () => {
      const d = await api("POST", "/ai/narrative", { project_id: pid, lang: getLang() });
      mount(nar, h("textarea", { rows: "5", style: "width:100%", readonly: true }, d.output.text), h("p", { class: "muted small" }, d.mode === "stub" ? t("ai_stub_note") : t("ai_draft_note")));
    }));
    mount(body, banner,
      p.state === "planning" ? h("div", { class: "card" }, h("h2", {}, t("ai_plan_from_brief")), brief, h("div", { class: "row", style: "margin-top:8px" }, gen), err) : null, area,
      h("div", { class: "card" }, h("h2", {}, t("ai_status_narrative")), narBtn, nar),
      h("div", { class: "card" }, h("h2", {}, t("ai_history")), table([t("date"), t("type"), t("status"), t("model")], drafts.map(d => [String(d.created_at).slice(0, 16).replace("T", " "), d.kind, d.status, `${d.model} (${d.mode})`]), t("none"))));
  }

  async function closure(body, p) {
    const c = await api("GET", `/projects/${pid}/closure`);
    const editable = canManage && p.state === "closing";
    mount(body, h("div", { class: "card" }, h("h2", {}, t("closure")),
      h("p", {}, badge(c.ready ? t("closure_ready") : t("closure_not_ready"), c.ready ? "GREEN" : "AMBER")),
      table(["", t("closure"), t("note")], c.items.map(i => [
        i.auto ? h("span", { title: t("system_checked") }, i.satisfied ? "✓" : "✗")
          : h("input", { type: "checkbox", checked: i.done, disabled: !editable, "aria-label": i.label || t(`ci_${i.key}`),
            onChange: guarded(null, async (e) => { await api("PUT", `/projects/${pid}/closure/${i.key}`, { done: e.target.checked }); await render(); }) }),
        h("span", {}, i.label || t(`ci_${i.key}`), i.auto ? h("span", { class: "muted" }, ` (${t("system_checked")})`) : null),
        i.detail || i.note || ""]), t("none"))));
  }

  async function benefits(body, p) {
    const list = await api("GET", `/projects/${pid}/benefits`);
    const title = h("input"), metric = h("input"), unit = h("input", { style: "width:80px" });
    const base = h("input", { type: "number", step: "any", style: "width:100px" }), target = h("input", { type: "number", step: "any", style: "width:100px" });
    const due = h("input", { type: "date" }), err = h("div");
    const add = h("button", { class: "btn", type: "button" }, t("add"));
    add.addEventListener("click", guarded(add, async () => {
      mount(err);
      try {
        await api("POST", `/projects/${pid}/benefits`, { title: title.value.trim(), metric: metric.value.trim() || null, unit: unit.value.trim() || null,
          baseline: base.value === "" ? null : Number(base.value), target: target.value === "" ? null : Number(target.value), due_date: due.value || null });
        toast(t("saved")); await render();
      } catch (e) { mount(err, errorBox(e)); }
    }));
    const ST = ["planned", "on_track", "at_risk", "realized", "missed"];
    const actual = (b) => canManage ? h("input", { type: "number", step: "any", value: b.actual ?? "", style: "width:90px", "aria-label": t("actual"),
      onChange: guarded(null, async (e) => { await api("PATCH", `/projects/${pid}/benefits/${b.id}`, { actual: e.target.value === "" ? null : Number(e.target.value) }); await render(); }) }) : num(b.actual);
    const status = (b) => canManage ? h("select", { "aria-label": t("status"), onChange: guarded(null, async (e) => { await api("PATCH", `/projects/${pid}/benefits/${b.id}`, { status: e.target.value }); await render(); }) },
      ST.map(x => h("option", { value: x, selected: x === b.status }, t(`st_${x}`)))) : t(`st_${b.status}`);
    mount(body, h("div", { class: "card" }, h("h2", {}, t("benefits")), h("p", {}, h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => downloadCsv(`/projects/${pid}/export/benefits.csv`, `${p.number}-benefits.csv`)) }, t("export_csv")), xlsxBtn(`/projects/${pid}/export/benefits.xlsx`, `${p.number}-benefits.xlsx`)),
      table([t("title"), t("metric"), t("baseline"), t("target"), t("actual"), t("realization"), t("status")],
        list.map(b => [b.title, `${b.metric || ""} ${b.unit || ""}`.trim() || "—", num(b.baseline), num(b.target), actual(b), b.realization_pct == null ? "—" : `${num(b.realization_pct, 0)}%`, status(b)]), t("none"))),
      canManage ? h("div", { class: "card" }, h("h2", {}, t("add_benefit")),
        h("div", { class: "row" }, field(t("title"), title), field(t("metric"), metric), field(t("unit"), unit), field(t("baseline"), base), field(t("target"), target), field(t("due_date"), due), add), err) : null);
  }

  async function progress(body, p) {
    const rows = await api("GET", `/projects/${pid}/progress`);
    const week = h("input", { type: "date", value: today() });
    const inputs = rows.map(r => ({ r, pct: h("input", { type: "number", min: "0", max: "100", value: r.pct_complete, style: "width:80px" }), etc: h("input", { type: "number", min: "0", value: r.etc_hours ?? "", style: "width:90px" }), why: h("input", { placeholder: t("reason") }) }));
    const err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("save_progress"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try {
        await api("PUT", `/projects/${pid}/progress`, { week_of: week.value, updates: inputs.map(i => ({ activity_id: i.r.activity_id, pct_complete: Number(i.pct.value), etc_hours: i.etc.value === "" ? null : Number(i.etc.value), reason: i.why.value.trim() || null })) });
        toast(t("progress_saved")); await render();
      } catch (e) { mount(err, errorBox(e)); }
    }));
    mount(body, h("div", { class: "card" },
      table([t("activity"), t("progress_pct"), t("etc_hours"), t("reason"), ""], inputs.map(i => [i.r.code, canManage ? i.pct : num(i.r.pct_complete), canManage ? i.etc : num(i.r.etc_hours), canManage ? i.why : "", i.r.stale ? badge(t("stale"), "warning") : ""]), t("none")),
      canManage && inputs.length ? h("div", { class: "row", style: "margin-top:12px" }, field(t("week_of"), week), btn) : null, err));
  }

  async function risks(body, p) {
    const [rs, is, lists, cl] = await Promise.all([api("GET", `/projects/${pid}/risks`), api("GET", `/projects/${pid}/issues`), api("GET", "/config/lists"), api("GET", `/projects/${pid}/closures`)]);
    const who = (id) => (dir.find(u => u.id === id) || {}).full_name || "—";
    const ownerSel = (v) => h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id, selected: u.id === v }, u.full_name)));
    const rcat = h("select", {}, h("option", { value: "" }, "—"), lists.risk_category.map(x => h("option", { value: x.code }, x.label)));
    const rt = h("input"), rp = h("input", { type: "number", min: "1", max: "5", value: "3", style: "width:70px" }), ri = h("input", { type: "number", min: "1", max: "5", value: "3", style: "width:70px" });
    const it = h("input"), isv = h("select", {}, ["low", "medium", "high", "critical"].map(s => h("option", { value: s }, st(s)))), idue = h("input", { type: "date" });
    const rown = ownerSel(null), iown = ownerSel(null);
    const err = h("div");
    const addR = h("button", { class: "btn", type: "button" }, t("add_risk")), addI = h("button", { class: "btn", type: "button" }, t("add_issue"));
    addR.addEventListener("click", guarded(addR, async () => { mount(err); try { await api("POST", `/projects/${pid}/risks`, { title: rt.value.trim(), probability: Number(rp.value), impact: Number(ri.value), category: rcat.value || null, owner_id: rown.value ? Number(rown.value) : null }); await render(); } catch (e) { mount(err, errorBox(e)); } }));
    addI.addEventListener("click", guarded(addI, async () => { mount(err); try { await api("POST", `/projects/${pid}/issues`, { title: it.value.trim(), severity: isv.value, due_date: idue.value || null, owner_id: iown.value ? Number(iown.value) : null }); await render(); } catch (e) { mount(err, errorBox(e)); } }));
    const editItem = (kind, item) => {
      const f = { title: h("input", { value: item.title }), owner: ownerSel(item.owner_id) };
      const extra = kind === "risks"
        ? { cat: h("select", {}, h("option", { value: "" }, "—"), lists.risk_category.map(x => h("option", { value: x.code, selected: x.code === item.category }, x.label))), p: h("input", { type: "number", min: "1", max: "5", value: item.probability }), i: h("input", { type: "number", min: "1", max: "5", value: item.impact }), resp: h("textarea", { rows: 3 }, item.response || "") }
        : { sev: h("select", {}, ["low", "medium", "high", "critical"].map(s => h("option", { value: s, selected: s === item.severity }, st(s)))), due: h("input", { type: "date", value: item.due_date || "" }), desc: h("textarea", { rows: 3 }, item.description || "") };
      const e2 = h("div");
      modal({ title: t("edit"), body: h("div", {}, e2, h("div", { class: "row" }, field(t("title"), f.title), field(t("owner"), f.owner),
        kind === "risks" ? [field(t("category"), extra.cat), field(t("probability"), extra.p), field(t("impact"), extra.i), field(t("response"), extra.resp)] : [field(t("severity"), extra.sev), field(t("due_date"), extra.due), field(t("description"), extra.desc)])),
        actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("save"), onClick: async (c) => {
          const body = { title: f.title.value.trim(), owner_id: f.owner.value ? Number(f.owner.value) : null };
          if (kind === "risks") Object.assign(body, { category: extra.cat.value || null, probability: Number(extra.p.value), impact: Number(extra.i.value), response: extra.resp.value.trim() || null });
          else Object.assign(body, { severity: extra.sev.value, due_date: extra.due.value || null, description: extra.desc.value.trim() || null });
          try { await api("PATCH", `/projects/${pid}/${kind}/${item.id}`, body); c(); await render(); } catch (e) { mount(e2, errorBox(e)); } } }] });
    };
    const editBtn = (kind, item) => canManage ? h("button", { class: "btn small secondary", type: "button", onClick: () => editItem(kind, item) }, t("edit")) : "";
    const notesOf = (kind, item) => cl.filter(n => n.kind === kind.slice(0, -1) && n.item_id === item.id);
    const area = (rows = 3) => h("textarea", { rows, dir: "auto", class: "ta", style: "width:100%" });
    const closeDlg = (kind, item) => {
      const a = area(), b = area(), c_ = area(), lesson = h("input", { type: "checkbox", id: "cl-lesson" }), e2 = h("div");
      const stSel = kind === "issues" ? h("select", { id: "cl-status" }, ["resolved", "closed"].map(x => h("option", { value: x }, st(x)))) : null;
      a.id = "cl-what"; b.id = "cl-how"; c_.id = "cl-outcome";
      modal({ title: `${t("close_item")}: ${item.title}`, body: h("div", {}, e2, field(t("cl_what"), a), field(t("cl_how"), b), field(t("cl_outcome"), c_),
        stSel ? field(t("status"), stSel) : null, h("label", { class: "small check" }, lesson, ` ${t("cl_lesson")}`)),
        actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("close_item"), onClick: async (c) => {
          if ([a, b, c_].some(x => x.value.trim().length < 3)) { mount(e2, errorBox({ message: t("cl_need_all") })); return; }
          try { await api("POST", `/projects/${pid}/${kind}/${item.id}/close`, { what_happened: a.value.trim(), how_handled: b.value.trim(), outcome: c_.value.trim(), lesson: lesson.checked, status: stSel ? stSel.value : "closed" }); c(); toast(t("cl_done")); await render(); } catch (e) { mount(e2, errorBox(e)); } } }] });
    };
    const reopenDlg = (kind, item) => {
      const r = area(); r.id = "cl-reason"; const e2 = h("div");
      modal({ title: `${t("cl_reopen")}: ${item.title}`, body: h("div", {}, e2, field(t("reason"), r)),
        actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("cl_reopen"), onClick: async (c) => {
          if (r.value.trim().length < 3) { mount(e2, errorBox({ message: t("cl_need_all") })); return; }
          try { await api("POST", `/projects/${pid}/${kind}/${item.id}/reopen`, { reason: r.value.trim() }); c(); await render(); } catch (e) { mount(e2, errorBox(e)); } } }] });
    };
    const historyDlg = (kind, item) => modal({ title: `${t("cl_history")}: ${item.title}`, body: h("div", {}, ...notesOf(kind, item).map(n => h("div", { class: "card", style: "margin:8px 0" },
      h("b", {}, n.event === "closed" ? t("cl_closed_by") : t("cl_reopened_by")), ` ${n.by || "—"} · ${String(n.at).slice(0, 16).replace("T", " ")}`,
      n.event === "closed" ? h("div", {}, h("p", {}, h("b", {}, `${t("cl_what")}: `), n.what_happened), h("p", {}, h("b", {}, `${t("cl_how")}: `), n.how_handled), h("p", {}, h("b", {}, `${t("cl_outcome")}: `), n.outcome), n.lesson ? badge(t("cl_lesson_badge"), "info") : null)
        : h("p", {}, h("b", {}, `${t("reason")}: `), n.reason)))), actions: [{ label: t("close"), onClick: (c) => c() }] });
    const lifecycle = (kind, item, options) => {
      const done = item.status === "closed" || item.status === "resolved";
      const hasNotes = notesOf(kind, item).length > 0;
      if (!canManage) return h("span", {}, st(item.status), hasNotes ? h("button", { class: "btn small secondary", type: "button", style: "margin-inline-start:6px", onClick: () => historyDlg(kind, item) }, t("cl_history")) : null);
      return h("span", { class: "row", style: "gap:6px;flex-wrap:nowrap" },
        done ? badge(st(item.status), "ok") : h("select", { "aria-label": t("status"), onChange: guarded(null, async (ev) => { await api("PATCH", `/projects/${pid}/${kind}/${item.id}`, { status: ev.target.value }); await render(); }) }, options.filter(o => o !== "closed" && o !== "resolved").map(o => h("option", { value: o, selected: o === item.status }, st(o)))),
        done ? h("button", { class: "btn small secondary", type: "button", "data-act": "reopen", onClick: () => reopenDlg(kind, item) }, t("cl_reopen")) : h("button", { class: "btn small", type: "button", "data-act": "close", onClick: () => closeDlg(kind, item) }, t("close_item")),
        hasNotes ? h("button", { class: "btn small secondary", type: "button", "data-act": "history", onClick: () => historyDlg(kind, item) }, t("cl_history")) : null);
    };
    mount(body,
      h("div", { class: "card" }, h("h2", {}, t("risks")), table([t("title"), t("category"), t("owner"), t("probability"), t("impact"), t("score"), t("status"), ""], rs.map(r => [r.title, r.category || "—", who(r.owner_id), r.probability, r.impact, badge(r.score, r.score >= 20 ? "critical" : r.score >= 15 ? "warning" : "info"), lifecycle("risks", r, ["open", "mitigating", "occurred", "closed"]), editBtn("risks", r)]), t("none")),
        canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("title"), rt), field(t("category"), rcat), field(t("owner"), rown), field(t("probability"), rp), field(t("impact"), ri), addR) : null),
      h("div", { class: "card" }, h("h2", {}, t("issues")), table([t("title"), t("severity"), t("owner"), t("due_date"), t("status"), ""], is.map(i => [i.title, badge(st(i.severity), i.severity === "critical" ? "critical" : i.severity === "high" ? "warning" : "info"), who(i.owner_id), i.due_date || "—", lifecycle("issues", i, ["open", "in_progress", "resolved", "closed"]), editBtn("issues", i)]), t("none")),
        canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("title"), it), field(t("severity"), isv), field(t("due_date"), idue), field(t("owner"), iown), addI) : null), err);
  }

  async function costs(body, p) {
    const [evm, list] = await Promise.all([api("GET", `/projects/${pid}/evm`), api("GET", `/projects/${pid}/costs`)]);
    const cat = h("input", { required: true }), amt = h("input", { type: "number", min: "0", style: "width:130px" }), date = h("input", { type: "date", value: today() }), vendor = h("input");
    const stSel = h("select", {}, ["invoiced", "paid", "committed"].map(s => h("option", { value: s }, st(s))));
    const err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("add_cost"));
    btn.addEventListener("click", guarded(btn, async () => { mount(err); try { await api("POST", `/projects/${pid}/costs`, { category: cat.value.trim(), amount: Number(amt.value), entry_date: date.value, vendor: vendor.value.trim() || null, cost_status: stSel.value, currency: p.currency }); await render(); } catch (e) { mount(err, errorBox(e)); } }));
    const approve = (c) => ["PMO", "ADMIN"].includes(me.role) && c.approval === "pending" ? h("button", { class: "btn small", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/costs/${c.id}/approve`); await render(); }) }, t("approve")) : "";
    mount(body, h("div", { class: "card" }, h("h2", {}, t("evm")),
      evm.available ? h("div", { class: "grid" }, ["BAC", "PV", "EV", "AC", "CV", "SV", "CPI", "SPI", "TCPI", "EAC", "VAC"].map(k => stat(k, num(evm[k], ["CPI", "SPI", "TCPI"].includes(k) ? 2 : 0)))) : h("p", { class: "muted" }, `${t("not_available")}: ${evm.reason || ""}`),
      (evm.warnings || []).length ? h("div", { class: "warn" }, h("ul", {}, evm.warnings.map(w => h("li", {}, w)))) : null),
      h("div", { class: "card" }, h("h2", {}, t("costs")), h("p", {}, h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => downloadCsv(`/projects/${pid}/export/costs.csv`, `${p.number}-costs.csv`)) }, t("export_csv")), xlsxBtn(`/projects/${pid}/export/costs.xlsx`, `${p.number}-costs.xlsx`)), table([t("date"), t("category"), t("vendor"), t("amount"), t("cost_status"), t("approval"), ""], list.map(c => [c.entry_date, c.category, c.vendor || "", `${num(c.amount, 0)} ${c.currency}`, st(c.cost_status), badge(c.approval === "pending" ? t("pending") : t("approved"), c.approval === "pending" ? "warning" : "approved"), approve(c)]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("category"), cat), field(t("vendor"), vendor), field(t("amount"), amt), field(t("date"), date), field(t("cost_status"), stSel), btn), err));
  }
  async function changes(body, p) {
    const list = await api("GET", `/projects/${pid}/changes`);
    const decideOk = me.is_ccb || ["PMO", "ADMIN"].includes(me.role);
    const type = h("select", {}, ["scope", "schedule", "cost", "risk", "other"].map(x => h("option", { value: x }, t(`ct_${x}`))));
    const desc = h("textarea"), hd = h("input", { type: "number", step: "any", style: "width:100px" }), cd = h("input", { type: "number", step: "any", style: "width:120px" }), sd = h("input", { type: "number", step: "1", style: "width:90px" });
    const err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("request"));
    const optNum = (i) => (i.value === "" ? null : Number(i.value));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try { await api("POST", `/projects/${pid}/changes`, { change_type: type.value, description: desc.value.trim(), impact_hours_delta: optNum(hd), impact_cost_delta: optNum(cd), impact_schedule_days: optNum(sd) }); toast(t("saved")); await render(); }
      catch (e) { mount(err, errorBox(e)); }
    }));
    const decideC = (c) => ["requested", "deferred"].includes(c.status) && decideOk && c.requested_by !== me.id
      ? h("button", { class: "btn small", type: "button", onClick: () => decide(c.description.slice(0, 80), async (v) => { await api("POST", `/projects/${pid}/changes/${c.id}/decision`, { outcome: v.outcome, reason: v.rationale, conditions: v.conditions }); toast(t("saved")); await render(); }) }, t("decide"))
      : ["info_requested", "deferred"].includes(c.status) && canManage ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { const r = await askText(t("resubmit"), t("your_response")); if (r === null) return; await api("POST", `/projects/${pid}/changes/${c.id}/resubmit`, { note: r }); toast(t("saved")); await render(); }) }, t("resubmit"))
      : (c.decision_reason || "");
    const showCost = list.some(c => "impact_cost_delta" in c);
    mount(body, h("div", { class: "card" }, h("h2", {}, t("changes")),
      table([t("change_type"), t("description"), t("hours_delta"), showCost ? t("cost_delta") : null, t("schedule_days"), t("requested_by"), t("status"), t("baseline_rev"), t("decision")].filter(x => x !== null),
        list.map(c => [t(`ct_${c.change_type}`), c.description, num(c.impact_hours_delta), ...(showCost ? [num(c.impact_cost_delta, 0)] : []), num(c.impact_schedule_days, 0), (dirById[c.requested_by] || {}).full_name || c.requested_by, badge(st(c.status), c.status === "approved" ? "approved" : c.status === "rejected" ? "critical" : "warning"), c.new_baseline_version ?? "—", decideC(c)]), t("none"))),
      canManage && p.state === "execution" ? h("div", { class: "card" }, h("h2", {}, t("new_change")),
        h("div", { class: "row" }, field(t("change_type"), type), field(t("hours_delta"), hd), field(t("cost_delta"), cd), field(t("schedule_days"), sd)),
        h("div", { style: "margin-top:10px" }, field(t("description"), desc)), h("div", { style: "margin-top:10px" }, btn), err) : null);
  }

  async function allocations(body, p) {
    const rows = await api("GET", `/projects/${pid}/allocations`);
    const ids = p.assigned_user_ids || [];
    const who = h("select", {}, ids.map(id => h("option", { value: id }, (dirById[id] || {}).full_name || id)));
    const wk = h("input", { type: "date", value: today() }), hrs = h("input", { type: "number", min: "0", max: "80", step: "any", style: "width:90px" });
    const err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("set_allocation"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try {
        const r = await api("PUT", `/projects/${pid}/allocations`, { user_id: Number(who.value), week_of: wk.value, hours: Number(hrs.value) });
        toast(t("saved")); if ((r.warnings || []).length) toast(r.warnings.join(" · "), "error"); await render();
      } catch (e) { mount(err, errorBox(e)); }
    }));
    const weeks = [...new Set(rows.map(r => r.week_start))].sort();
    const users = [...new Set(rows.map(r => r.user_id))];
    const cell = (u, w) => { const r = rows.find(x => x.user_id === u && x.week_start === w); return r ? num(r.hours) : ""; };
    mount(body, h("div", { class: "card" }, h("h2", {}, t("allocations")),
      users.length ? h("div", { style: "overflow-x:auto" }, table([t("staff"), ...weeks], users.map(u => [(dirById[u] || {}).full_name || u, ...weeks.map(w => cell(u, w))]))) : h("p", { class: "muted" }, t("none")),
      canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("staff"), who), field(t("week_of"), wk), field(t("hours"), hrs), btn) : null, err),
      await requestCard(pid, canManage, render));
  }

  async function reports(body, p) {
    const list = await api("GET", `/projects/${pid}/reports/weekly`);
    const wk = h("input", { type: "date", value: today() }), acc = h("textarea"), nxt = h("textarea"), esc = h("textarea");
    const err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("submit_report"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try { await api("POST", `/projects/${pid}/reports/weekly`, { week_of: wk.value, accomplishments: acc.value.trim(), next_week: nxt.value.trim(), escalations: esc.value.trim() || null }); toast(t("report_saved")); await render(); }
      catch (e) { mount(err, errorBox(e)); }
    }));
    const snap = (r) => { const s = r.snapshot || {}; return h("div", { class: "grid", style: "margin:8px 0" },
      stat(t("overall_pct"), s.overall_pct_complete == null ? "—" : `${s.overall_pct_complete}%`), stat(t("approved_hours"), num(s.hours?.approved)), stat(t("submitted_hours"), num(s.hours?.submitted)),
      stat(t("open_risks"), `${s.open_risks ?? 0}${s.top_risk_score ? ` (${t("max")} ${s.top_risk_score})` : ""}`), stat(t("open_issues"), `${s.open_issues ?? 0}${s.critical_issues ? ` · ${s.critical_issues} ${t("critical_short")}` : ""}`),
      s.evm ? [stat("CPI", num(s.evm.CPI, 2)), stat("SPI", num(s.evm.SPI, 2))] : null); };
    mount(body,
      canManage && ["execution", "closing"].includes(p.state) ? h("div", { class: "card" }, h("h2", {}, t("new_report")),
        h("div", { class: "row" }, field(t("week_of"), wk)),
        h("div", { style: "margin-top:10px" }, field(t("accomplishments"), acc)), h("div", { style: "margin-top:10px" }, field(t("next_week"), nxt)), h("div", { style: "margin-top:10px" }, field(t("escalations"), esc)),
        h("div", { style: "margin-top:10px" }, btn), err) : null,
      list.length ? list.map(r => h("div", { class: "card" }, h("h2", {}, `${t("week_of")} ${r.week_start} · ${(dirById[r.pm_id] || {}).full_name || ""}`), snap(r),
        h("p", {}, h("strong", {}, `${t("accomplishments")}: `), r.narrative.accomplishments), h("p", {}, h("strong", {}, `${t("next_week")}: `), r.narrative.next_week),
        r.narrative.escalations ? h("p", {}, h("strong", {}, `${t("escalations")}: `), r.narrative.escalations) : null)) : h("div", { class: "card" }, h("p", { class: "muted" }, t("none"))));
  }
  await render();
}
