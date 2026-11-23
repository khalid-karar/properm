// Program detail: roadmap of projects and milestones, cross-project dependencies, program-level risks.
import { api, openReport } from "../api.js";
import { gantt } from "../charts.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, modal, mount, num, stat, table, toast } from "../ui.js";

const DST = { met: "GREEN", on_track: "GREY", conflict: "AMBER", late: "RED" };

export default async function (root, { me, gid }) {
  const dir = await api("GET", "/directory");
  async function render() {
    const [rm, risks, issues, bud, bplan] = await Promise.all([api("GET", `/programs/${gid}/roadmap`), api("GET", `/programs/${gid}/risks`), api("GET", `/programs/${gid}/issues`),
      api("GET", `/programs/${gid}/budget`), api("GET", `/programs/${gid}/benefits-plan`)]);
    const can = rm.can_manage;
    const rowsWithDates = rm.projects.filter(p => p.start && p.end);
    const idx = Object.fromEntries(rowsWithDates.map((p, i) => [p.project_id, i]));
    const chart = rowsWithDates.length ? gantt({
      rows: rowsWithDates.map(p => ({ label: `${p.number} ${p.name}`, start: p.start, end: p.end, pct: p.progress_pct, marks: p.milestones.map(m => ({ label: m.name, date: m.due_date, done: !!m.achieved_on })) })),
      links: rm.dependencies.filter(d => d.project_id in idx && d.predecessor_id in idx && d.delivers_on).map(d => ({ fromRow: idx[d.predecessor_id], fromDate: d.delivers_on, toRow: idx[d.project_id], toDate: d.needed_by, bad: ["conflict", "late"].includes(d.status), label: `${d.predecessor} → ${d.project}` })),
      todayLabel: t("today") }) : h("p", { class: "muted" }, t("timeline_empty"));

    // dependency form
    const projSel = (list) => h("select", {}, list.map(p => h("option", { value: p.project_id ?? p.id }, `${p.number} · ${p.name}`)));
    const allProjects = can ? await api("GET", "/projects") : [];
    const f = { succ: projSel(rm.projects), pred: h("select"), ms: h("select"), need: h("input", { type: "date" }), desc: h("input", { style: "min-width:220px" }) };
    const fillPred = () => { mount(f.pred, allProjects.filter(p => String(p.id) !== f.succ.value).map(p => h("option", { value: p.id }, `${p.number} · ${p.name}`))); fillMs(); };
    const fillMs = async () => { if (!f.pred.value) return; const ms = await api("GET", `/projects/${f.pred.value}/milestones`).catch(() => []); mount(f.ms, h("option", { value: "" }, t("project_finish")), ms.map(m => h("option", { value: m.id }, `${m.name} (${m.due_date})`))); };
    f.succ.addEventListener("change", fillPred); f.pred.addEventListener("change", fillMs);
    if (can) fillPred();
    const derr = h("div");

    // risk form
    const r = { title: h("input", { style: "min-width:240px" }), p: h("input", { type: "number", min: "1", max: "5", value: "3", style: "width:70px" }), i: h("input", { type: "number", min: "1", max: "5", value: "3", style: "width:70px" }),
      owner: h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id }, u.full_name))), resp: h("input", { style: "min-width:200px" }) };
    const rerr = h("div");
    const editRisk = (x) => {
      const st = h("select", {}, ["open", "mitigating", "occurred", "closed"].map(s => h("option", { value: s, selected: s === x.status }, t(`st_${s}`) || s)));
      const resp = h("textarea", { rows: 3 }, x.response || ""), e2 = h("div");
      modal({ title: x.title, body: h("div", {}, e2, field(t("status"), st), field(t("response"), resp)), actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("save"), onClick: async (c) => {
        try { await api("PATCH", `/programs/${gid}/risks/${x.id}`, { status: st.value, response: resp.value.trim() || null }); c(); await render(); } catch (e) { mount(e2, errorBox(e)); } } }] });
    };

    const canEnv = ["PMO", "ADMIN", "DECISION_MAKER"].includes(me.role);
    const env = h("input", { type: "number", min: "0", value: bud.envelope ?? "", style: "width:150px" }), envErr = h("div");
    const money = (v) => (v == null ? "—" : `${num(v, 0)} ${bud.currency}`);
    const budCard = h("div", { class: "card", id: "envelope" }, h("h2", {}, t("program_budget")),
      h("div", { class: "grid" }, stat(t("envelope"), money(bud.envelope)), stat(t("budgets_total"), money(bud.totals.budget)), stat(t("spent_total"), money(bud.totals.spent)), stat(t("forecast_total"), money(bud.totals.forecast)),
        bud.headroom != null ? stat(t("headroom"), h("span", { class: bud.headroom < 0 ? "neg" : "" }, money(bud.headroom))) : null),
      bud.excluded_other_currency.length ? h("p", { class: "muted small" }, `${t("excluded_ccy")}: ${bud.excluded_other_currency.join(", ")}`) : null,
      canEnv ? h("div", { class: "row", style: "margin-top:10px" }, field(t("envelope"), env), h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { mount(envErr); try { await api("PUT", `/programs/${gid}/budget`, { envelope: Number(env.value), currency: bud.currency }); toast(t("saved")); await render(); } catch (e) { mount(envErr, errorBox(e)); } }) }, t("save"))) : null, envErr);
    const isv = { title: h("input", { style: "min-width:240px" }), sev: h("select", {}, ["low", "medium", "high", "critical"].map(x => h("option", { value: x, selected: x === "medium" }, t(`st_${x}`) || x))), due: h("input", { type: "date" }),
      owner: h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id }, u.full_name))) }, ierr = h("div");
    const issCard = h("div", { class: "card", id: "pissues" }, h("h2", {}, t("program_level_issues")),
      table([t("title"), t("severity"), t("owner"), t("due_date"), t("status"), can ? "" : null].filter(x => x !== null), issues.map(x => [x.title, badge(t(`st_${x.severity}`), x.severity === "critical" ? "critical" : x.severity === "high" ? "warning" : "info"), x.owner || "—",
        x.due_date ? h("span", { class: x.overdue ? "neg" : "" }, x.due_date) : "—", t(`st_${x.status}`),
        ...(can ? [h("select", { onChange: guarded(null, async (e) => { await api("PATCH", `/programs/${gid}/issues/${x.id}`, { status: e.target.value }); await render(); }) }, ["open", "in_progress", "resolved", "closed"].map(s_ => h("option", { value: s_, selected: s_ === x.status }, t(`st_${s_}`))))] : [])]), t("none")),
      can ? h("div", { class: "row", style: "margin-top:12px" }, field(t("title"), isv.title), field(t("severity"), isv.sev), field(t("owner"), isv.owner), field(t("due_date"), isv.due),
        h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(ierr); try { await api("POST", `/programs/${gid}/issues`, { title: isv.title.value.trim(), severity: isv.sev.value, owner_id: isv.owner.value ? Number(isv.owner.value) : null, due_date: isv.due.value || null }); toast(t("saved")); await render(); } catch (e) { mount(ierr, errorBox(e)); } }) }, t("add_issue"))) : null, ierr);
    const BST = { planned: "GREY", on_track: "GREEN", at_risk: "AMBER", realized: "GREEN", missed: "RED" };
    const benCard = h("div", { class: "card", id: "benefits-plan" }, h("h2", {}, t("benefits_plan")), h("p", { class: "muted small" }, t("benefits_plan_note"), bplan.no_owner ? h("span", { class: "neg" }, ` ${bplan.no_owner} ${t("without_owner")}.`) : null),
      table([t("quarter"), t("project"), t("benefit"), t("metric"), t("baseline"), t("target"), t("actual"), t("realization"), t("owner"), t("status")], bplan.benefits.map(b => [b.quarter, b.project, b.title, `${b.metric || ""}${b.unit ? ` (${b.unit})` : ""}`, num(b.baseline), num(b.target), num(b.actual),
        b.realization_pct == null ? "—" : `${num(b.realization_pct, 0)}%`, b.owner || h("span", { class: "neg" }, "—"), badge(t(`st_${b.status}`), b.overdue ? "RED" : BST[b.status] || "GREY")]), t("none")));
    mount(root, h("p", {}, h("a", { href: "#/programs" }, `← ${t("programs")}`)),
      h("h1", {}, `${rm.program.code} · ${rm.program.name} `, rm.conflicts ? badge(`${rm.conflicts} ${t("dep_conflicts")}`, "RED") : null),
      rm.program.description ? h("p", { class: "muted" }, rm.program.description) : null,
      h("p", {}, h("button", { class: "btn small secondary", type: "button", onClick: () => openReport(`/reports/board-pack.html?program_id=${gid}`) }, t("board_pack"))),
      h("div", { class: "card", id: "roadmap" }, h("h2", {}, t("roadmap")), h("p", { class: "muted small" }, t("roadmap_note")), chart,
        table([t("project"), t("state"), "RAG", t("planned_start"), t("planned_end"), "%"], rm.projects.map(p => [h("a", { href: `#/projects/${p.project_id}` }, `${p.number} · ${p.name}`), t(p.state), badge(t(`rag_${p.rag}`), p.rag), p.start || "—", p.end || "—", p.progress_pct == null ? "—" : `${num(p.progress_pct, 0)}%`]), t("none"))),
      h("div", { class: "card", id: "xdeps" }, h("h2", {}, t("cross_deps")), h("p", { class: "muted small" }, t("cross_deps_note")),
        table([t("waiting_project"), t("delivering_project"), t("milestone"), t("delivers_on"), t("needed_by"), t("status"), t("description"), can ? "" : null].filter(x => x !== null),
          rm.dependencies.map(d => [d.project, d.predecessor, d.milestone || t("project_finish"), d.delivers_on || "—", d.needed_by, badge(t(`dep_${d.status}`) + (d.gap_days ? ` +${d.gap_days}d` : ""), DST[d.status]), d.description || "",
            ...(can ? [h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/programs/${gid}/dependencies/${d.id}`); await render(); }) }, t("remove"))] : [])]), t("none")),
        can && rm.projects.length ? h("div", {}, h("div", { class: "row", style: "margin-top:12px" }, field(t("waiting_project"), f.succ), field(t("delivering_project"), f.pred), field(t("milestone"), f.ms), field(t("needed_by"), f.need), field(t("description"), f.desc),
          h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(derr); try { await api("POST", `/programs/${gid}/dependencies`, { project_id: Number(f.succ.value), predecessor_id: Number(f.pred.value), milestone_id: f.ms.value ? Number(f.ms.value) : null, needed_by: f.need.value, description: f.desc.value.trim() || null }); toast(t("saved")); await render(); } catch (e) { mount(derr, errorBox(e)); } }) }, t("add"))), derr) : null),
      budCard,
      h("div", { class: "card", id: "prisks" }, h("h2", {}, t("program_level_risks")),
        table([t("title"), t("owner"), t("score"), t("status"), t("response"), can ? "" : null].filter(x => x !== null), risks.map(x => [x.title, x.owner || "—", badge(x.score, x.score >= 20 ? "critical" : x.score >= 15 ? "warning" : "info"), t(`st_${x.status}`), x.response || "",
          ...(can ? [h("button", { class: "btn small secondary", type: "button", onClick: () => editRisk(x) }, t("edit"))] : [])]), t("none")),
        can ? h("div", {}, h("div", { class: "row", style: "margin-top:12px" }, field(t("title"), r.title), field(t("probability"), r.p), field(t("impact"), r.i), field(t("owner"), r.owner), field(t("response"), r.resp),
          h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(rerr); try { await api("POST", `/programs/${gid}/risks`, { title: r.title.value.trim(), probability: Number(r.p.value), impact: Number(r.i.value), owner_id: r.owner.value ? Number(r.owner.value) : null, response: r.resp.value.trim() || null }); toast(t("saved")); await render(); } catch (e) { mount(rerr, errorBox(e)); } }) }, t("add_risk"))), rerr) : null), issCard, benCard);
  }
  await render();
}
