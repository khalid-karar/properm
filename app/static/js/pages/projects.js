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
    const tabs = ["overview", "progress", "risks", "costs"];
    const body = h("div");
    mount(root,
      h("p", {}, h("a", { href: "#/projects" }, `← ${t("projects")}`)),
      h("h1", {}, `${p.number} · ${p.name} `, badge(t(p.state), "gold")),
      h("div", { class: "tabs", role: "tablist" }, tabs.filter(x => x !== "costs" || canManage).map(x =>
        h("button", { class: tab === x ? "active" : "", role: "tab", onClick: () => { tab = x; render(); } }, t(`tab_${x}`)))),
      body);
    try {
      if (tab === "overview") await overview(body, p);
      else if (tab === "progress") await progress(body, p);
      else if (tab === "risks") await risks(body, p);
      else await costs(body, p);
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
    mount(body,
      h("div", { class: "grid", style: "margin-bottom:16px" }, stat(t("state"), t(p.state)), stat(t("baseline_version"), p.baseline_version), stat(t("planned_start"), p.planned_start || "—"), stat(t("planned_end"), p.planned_end || "—")),
      canManage ? h("div", { class: "card" }, h("div", { class: "row" }, moves,
        p.state === "planning" ? h("button", { class: "btn gold small", onClick: guarded(null, async () => { if (!confirm(t("confirm_lock"))) return; await api("POST", `/projects/${pid}/baseline/lock`); toast(t("baseline_locked")); await render(); }) }, t("lock_baseline")) : null)) : null,
      h("div", { class: "card" }, h("h2", {}, t("activities")),
        table([t("code"), t("name"), t("planned_hours"), p.activities.some(a => "baseline_cost" in a) ? t("baseline_cost") : null, t("planned_start"), t("planned_end"), t("locked")].filter(x => x !== null),
          acts.filter(a => a.phase === "execution").map(a => [a.code, a.name, num(a.planned_hours), ..."baseline_cost" in a ? [num(a.baseline_cost, 0)] : [], a.planned_start || "—", a.planned_end || "—", a.locked ? "✓" : ""]), t("none"))),
      canManage && p.state === "planning" ? h("div", { class: "card" }, h("h2", {}, t("add_activity")),
        h("div", { class: "row" }, field(t("code"), code), field(t("name"), name), field(t("planned_hours"), hrs), field(t("baseline_cost"), bc), field(t("planned_start"), ps), field(t("planned_end"), pe), add), err) : null,
      canManage ? h("div", { class: "card" }, h("h2", {}, t("assigned_staff")), h("div", { class: "row" }, field(t("staff"), who), assignBtn)) : null);
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
    const st = h("select", {}, ["invoiced", "paid", "committed"].map(s => h("option", { value: s }, st(s))));
    const err = h("div");
    const btn = h("button", { class: "btn", type: "button" }, t("add_cost"));
    btn.addEventListener("click", guarded(btn, async () => { mount(err); try { await api("POST", `/projects/${pid}/costs`, { category: cat.value.trim(), amount: Number(amt.value), entry_date: date.value, vendor: vendor.value.trim() || null, cost_status: st.value, currency: p.currency }); await render(); } catch (e) { mount(err, errorBox(e)); } }));
    const approve = (c) => ["PMO", "ADMIN"].includes(me.role) && c.approval === "pending" ? h("button", { class: "btn small", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/costs/${c.id}/approve`); await render(); }) }, t("approve")) : "";
    mount(body, h("div", { class: "card" }, h("h2", {}, t("evm")),
      evm.available ? h("div", { class: "grid" }, ["BAC", "PV", "EV", "AC", "CPI", "SPI", "EAC", "VAC"].map(k => stat(k, num(evm[k], k === "CPI" || k === "SPI" ? 2 : 0)))) : h("p", { class: "muted" }, `${t("not_available")}: ${evm.reason || ""}`),
      (evm.warnings || []).length ? h("div", { class: "warn" }, h("ul", {}, evm.warnings.map(w => h("li", {}, w)))) : null),
      h("div", { class: "card" }, h("h2", {}, t("costs")), table([t("date"), t("category"), t("vendor"), t("amount"), t("cost_status"), t("approval"), ""], list.map(c => [c.entry_date, c.category, c.vendor || "", `${num(c.amount, 0)} ${c.currency}`, st(c.cost_status), badge(c.approval === "pending" ? t("pending") : t("approved"), c.approval === "pending" ? "warning" : "approved"), approve(c)]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("category"), cat), field(t("vendor"), vendor), field(t("amount"), amt), field(t("date"), date), field(t("cost_status"), st), btn), err));
  }
  await render();
}
