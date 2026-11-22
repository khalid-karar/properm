import { api } from "../api.js";
import { st, t } from "../i18n.js";
import { askText, badge, errorBox, field, guarded, h, mount, num, stat, table, toast, today } from "../ui.js";

const MANAGE = ["PM", "PMO", "ADMIN"];
const NEXT = { tendering: ["planning", "archived"], execution: ["closing", "on_hold"], closing: ["archived"], planning: ["on_hold"], on_hold: [] };

export default async function (root, { me, arg }) {
  if (arg) return detail(root, me, Number(arg));
  const canManage = MANAGE.includes(me.role);
  async function render() {
    const list = await api("GET", "/projects");
    const num_ = h("input", { required: true }), name = h("input", { required: true, style: "min-width:220px" });
    const state = h("select", {}, h("option", { value: "planning" }, t("planning")), h("option", { value: "tendering" }, t("tendering")));
    const start = h("input", { type: "date" }), end = h("input", { type: "date" });
    const budget = h("input", { type: "number", min: "0", style: "width:130px" });
    const ccy = h("input", { value: "SAR", maxlength: "3", style: "width:70px" });
    const err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("create"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try {
        await api("POST", "/projects", { number: num_.value.trim(), name: name.value.trim(), state: state.value, planned_start: start.value || null,
          planned_end: end.value || null, budget_ceiling: budget.value ? Number(budget.value) : null, currency: ccy.value.toUpperCase() });
        toast(t("saved")); await render();
      } catch (e) { mount(err, errorBox(e)); }
    }));
    mount(root, h("h1", {}, t("projects")),
      canManage ? h("div", { class: "card" }, h("h2", {}, t("new_project")),
        h("div", { class: "row" }, field(t("number"), num_), field(t("name"), name), field(t("state"), state), field(t("planned_start"), start), field(t("planned_end"), end), field(t("budget"), budget), field(t("currency"), ccy), btn), err) : null,
      h("div", { class: "card" }, table([t("number"), t("name"), t("state"), t("planned_start"), t("planned_end"), ""],
        list.map(p => [p.number, p.name, badge(t(p.state), "gold"), p.planned_start || "—", p.planned_end || "—",
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
    const tabs = ["overview", "progress", "risks", "costs", "changes", "allocations", "benefits", "closure", "reports"];
    const show = (x) => (x === "costs" || x === "allocations") ? (me.role !== "STAFF") : x === "closure" ? ["closing", "archived"].includes(p.state) : true;
    const body = h("div");
    mount(root,
      h("p", {}, h("a", { href: "#/projects" }, `← ${t("projects")}`)),
      h("h1", {}, `${p.number} · ${p.name} `, badge(t(p.state), "gold")),
      h("div", { class: "tabs", role: "tablist" }, tabs.filter(show).map(x =>
        h("button", { class: tab === x ? "active" : "", role: "tab", onClick: () => { tab = x; render(); } }, t(`tab_${x}`)))),
      body);
    try {
      if (tab === "overview") await overview(body, p);
      else if (tab === "progress") await progress(body, p);
      else if (tab === "risks") await risks(body, p);
      else if (tab === "costs") await costs(body, p);
      else if (tab === "changes") await changes(body, p);
      else if (tab === "allocations") await allocations(body, p);
      else if (tab === "benefits") await benefits(body, p);
      else if (tab === "closure") await closure(body, p);
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
    mount(body,
      h("div", { class: "grid", style: "margin-bottom:16px" }, stat(t("state"), t(p.state)), stat(t("baseline_version"), p.baseline_version), stat(t("planned_start"), p.planned_start || "—"), stat(t("planned_end"), p.planned_end || "—")),
      progCard,
      canManage ? h("div", { class: "card" }, h("div", { class: "row" }, moves,
        p.state === "planning" ? h("button", { class: "btn gold small", onClick: guarded(null, async () => { if (!confirm(t("confirm_lock"))) return; await api("POST", `/projects/${pid}/baseline/lock`); toast(t("baseline_locked")); await render(); }) }, t("lock_baseline")) : null)) : null,
      h("div", { class: "card" }, h("h2", {}, t("activities")),
        table([t("code"), t("name"), t("planned_hours"), p.activities.some(a => "baseline_cost" in a) ? t("baseline_cost") : null, t("planned_start"), t("planned_end"), t("locked")].filter(x => x !== null),
          acts.filter(a => a.phase === "execution").map(a => [a.code, a.name, num(a.planned_hours), ..."baseline_cost" in a ? [num(a.baseline_cost, 0)] : [], a.planned_start || "—", a.planned_end || "—", a.locked ? "✓" : ""]), t("none"))),
      canManage && p.state === "planning" ? h("div", { class: "card" }, h("h2", {}, t("add_activity")),
        h("div", { class: "row" }, field(t("code"), code), field(t("name"), name), field(t("planned_hours"), hrs), field(t("baseline_cost"), bc), field(t("planned_start"), ps), field(t("planned_end"), pe), add), err) : null,
      canManage ? h("div", { class: "card" }, h("h2", {}, t("assigned_staff")), h("div", { class: "row" }, field(t("staff"), who), assignBtn)) : null);
  }

  async function closure(body, p) {
    const c = await api("GET", `/projects/${pid}/closure`);
    const editable = canManage && p.state === "closing";
    mount(body, h("div", { class: "card" }, h("h2", {}, t("closure")),
      h("p", {}, badge(c.ready ? t("closure_ready") : t("closure_not_ready"), c.ready ? "GREEN" : "AMBER")),
      table(["", t("closure"), t("note")], c.items.map(i => [
        i.auto ? h("span", { title: t("system_checked") }, i.satisfied ? "✓" : "✗")
          : h("input", { type: "checkbox", checked: i.done, disabled: !editable, "aria-label": t(`ci_${i.key}`),
            onChange: guarded(null, async (e) => { await api("PUT", `/projects/${pid}/closure/${i.key}`, { done: e.target.checked }); await render(); }) }),
        h("span", {}, t(`ci_${i.key}`), i.auto ? h("span", { class: "muted" }, ` (${t("system_checked")})`) : null),
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
    mount(body, h("div", { class: "card" }, h("h2", {}, t("benefits")),
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
    const [rs, is] = await Promise.all([api("GET", `/projects/${pid}/risks`), api("GET", `/projects/${pid}/issues`)]);
    const rt = h("input"), rp = h("input", { type: "number", min: "1", max: "5", value: "3", style: "width:70px" }), ri = h("input", { type: "number", min: "1", max: "5", value: "3", style: "width:70px" });
    const it = h("input"), isv = h("select", {}, ["low", "medium", "high", "critical"].map(s => h("option", { value: s }, st(s)))), idue = h("input", { type: "date" });
    const err = h("div");
    const addR = h("button", { class: "btn", type: "button" }, t("add_risk")), addI = h("button", { class: "btn", type: "button" }, t("add_issue"));
    addR.addEventListener("click", guarded(addR, async () => { mount(err); try { await api("POST", `/projects/${pid}/risks`, { title: rt.value.trim(), probability: Number(rp.value), impact: Number(ri.value) }); await render(); } catch (e) { mount(err, errorBox(e)); } }));
    addI.addEventListener("click", guarded(addI, async () => { mount(err); try { await api("POST", `/projects/${pid}/issues`, { title: it.value.trim(), severity: isv.value, due_date: idue.value || null }); await render(); } catch (e) { mount(err, errorBox(e)); } }));
    const statusSel = (kind, item, options) => canManage ? h("select", { value: item.status, onChange: guarded(null, async (ev) => { await api("PATCH", `/projects/${pid}/${kind}/${item.id}`, { status: ev.target.value }); await render(); }) }, options.map(o => h("option", { value: o }, st(o)))) : st(item.status);
    mount(body,
      h("div", { class: "card" }, h("h2", {}, t("risks")), table([t("title"), t("probability"), t("impact"), t("score"), t("status")], rs.map(r => [r.title, r.probability, r.impact, badge(r.score, r.score >= 20 ? "critical" : r.score >= 15 ? "warning" : "info"), statusSel("risks", r, ["open", "mitigating", "occurred", "closed"])]), t("none")),
        canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("title"), rt), field(t("probability"), rp), field(t("impact"), ri), addR) : null),
      h("div", { class: "card" }, h("h2", {}, t("issues")), table([t("title"), t("severity"), t("due_date"), t("status")], is.map(i => [i.title, badge(st(i.severity), i.severity === "critical" ? "critical" : i.severity === "high" ? "warning" : "info"), i.due_date || "—", statusSel("issues", i, ["open", "in_progress", "resolved", "closed"])]), t("none")),
        canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("title"), it), field(t("severity"), isv), field(t("due_date"), idue), addI) : null), err);
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
      evm.available ? h("div", { class: "grid" }, ["BAC", "PV", "EV", "AC", "CPI", "SPI", "EAC", "VAC"].map(k => stat(k, num(evm[k], k === "CPI" || k === "SPI" ? 2 : 0)))) : h("p", { class: "muted" }, `${t("not_available")}: ${evm.reason || ""}`),
      (evm.warnings || []).length ? h("div", { class: "warn" }, h("ul", {}, evm.warnings.map(w => h("li", {}, w)))) : null),
      h("div", { class: "card" }, h("h2", {}, t("costs")), table([t("date"), t("category"), t("vendor"), t("amount"), t("cost_status"), t("approval"), ""], list.map(c => [c.entry_date, c.category, c.vendor || "", `${num(c.amount, 0)} ${c.currency}`, st(c.cost_status), badge(c.approval === "pending" ? t("pending") : t("approved"), c.approval === "pending" ? "warning" : "approved"), approve(c)]), t("none")),
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
    const decide = (c) => c.status === "requested" && decideOk && c.requested_by !== me.id ? h("div", { class: "row", style: "flex-wrap:nowrap" },
      h("button", { class: "btn small", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/changes/${c.id}/decision`, { approve: true }); toast(t("saved")); await render(); }) }, t("approve")),
      h("button", { class: "btn danger small", onClick: guarded(null, async () => { const r = await askText(t("reject"), t("reason")); if (r === null) return; await api("POST", `/projects/${pid}/changes/${c.id}/decision`, { approve: false, reason: r }); await render(); }) }, t("reject"))) : (c.decision_reason || "");
    const showCost = list.some(c => "impact_cost_delta" in c);
    mount(body, h("div", { class: "card" }, h("h2", {}, t("changes")),
      table([t("change_type"), t("description"), t("hours_delta"), showCost ? t("cost_delta") : null, t("schedule_days"), t("requested_by"), t("status"), t("baseline_rev"), t("decision")].filter(x => x !== null),
        list.map(c => [t(`ct_${c.change_type}`), c.description, num(c.impact_hours_delta), ...(showCost ? [num(c.impact_cost_delta, 0)] : []), num(c.impact_schedule_days, 0), (dirById[c.requested_by] || {}).full_name || c.requested_by, badge(st(c.status), c.status === "approved" ? "approved" : c.status === "rejected" ? "critical" : "warning"), c.new_baseline_version ?? "—", decide(c)]), t("none"))),
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
      canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("staff"), who), field(t("week_of"), wk), field(t("hours"), hrs), btn) : null, err));
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
