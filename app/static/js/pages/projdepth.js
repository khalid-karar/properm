// Project depth cards: risk response plans and opportunities, reserves, quality log, stakeholder engagement, document versions.
import { api, fileToB64, saveDocument } from "../api.js";
import { t } from "../i18n.js";
import { askText, badge, errorBox, field, guarded, h, modal, mount, num, table, toast } from "../ui.js";
import { formFor, registerCard } from "../register.js";

const STRAT = ["avoid", "mitigate", "transfer", "accept", "escalate"];
const OPP = ["exploit", "enhance", "share", "accept"];
const LEVELS = ["unaware", "resistant", "neutral", "supportive", "leading"];
const so = (pref, list) => list.map(x => [x, t(`${pref}_${x}`)]);
const sev = (s) => (s >= 15 ? "RED" : s >= 8 ? "AMBER" : "GREEN");

export async function riskResponseCards({ pid, dir, canManage, render, p }) {
  const [rr, opps] = await Promise.all([api("GET", `/projects/${pid}/risk-responses`), api("GET", `/projects/${pid}/opportunities`)]);
  const editable = canManage && p.state !== "archived";
  const edit = (r) => {
    const fields = [{ k: "strategy", label: t("response_strategy"), type: "select", options: so("rs_strat", STRAT), def: r.strategy || "mitigate" }, { k: "plan", label: t("response_plan"), type: "textarea" }, { k: "trigger", label: t("trigger") },
      { k: "contingency_amount", label: t("contingency_amount"), type: "number" }, { k: "residual_probability", label: t("residual_probability"), type: "number" }, { k: "residual_impact", label: t("residual_impact"), type: "number" }, { k: "owner_id", label: t("owner"), type: "user" }];
    const f = formFor(fields, r, dir), err = h("div");
    modal({ title: r.title, body: h("div", {}, err, ...f.nodes),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("save"), onClick: async (c) => {
        try { await api("PUT", `/projects/${pid}/risks/${r.risk_id}/response`, f.read()); c(); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } } }] });
  };
  const respCard = h("div", { class: "card", id: "responses-card" }, h("h2", {}, t("risk_responses")), h("p", { class: "muted small" }, t("responses_note")),
    h("p", {}, `${t("exposure")}: ${rr.exposure} → ${t("residual_exposure")}: ${rr.residual_exposure}`, rr.without_response.length ? badge(`${rr.without_response.length} ${t("need_response")}`, "RED") : null),
    table([t("title"), t("score"), t("response_strategy"), t("trigger"), t("contingency_amount"), t("residual"), t("owner"), ""], rr.risks.map(r => [r.title, badge(r.score, sev(r.score)), r.strategy ? t(`rs_strat_${r.strategy}`) : (r.needs_response ? badge(t("no_response"), "RED") : "—"),
      r.trigger || "—", r.contingency_amount == null ? "—" : num(r.contingency_amount, 0), r.residual_score == null ? "—" : badge(r.residual_score, sev(r.residual_score)), r.owner || "—",
      editable ? h("button", { class: "btn small secondary", type: "button", onClick: () => edit(r) }, r.strategy ? t("edit") : t("plan_response")) : ""]), t("none")));
  const oppCard = registerCard({ id: "opps-card", title: t("opportunities"), note: t("opps_note"), base: `/projects/${pid}/opportunities`, rows: opps, canManage: editable, render, dir,
    fields: [{ k: "title", label: t("title"), req: true }, { k: "probability", label: t("probability"), type: "number", def: 3 }, { k: "impact", label: t("impact"), type: "number", def: 3 },
      { k: "strategy", label: t("response_strategy"), type: "select", options: so("os", OPP), def: "enhance" }, { k: "status", label: t("status"), type: "select", options: so("ost", ["open", "pursuing", "realized", "closed"]), def: "open" },
      { k: "owner_id", label: t("owner"), type: "user" }, { k: "note", label: t("note"), type: "textarea" }],
    columns: [{ h: t("title"), f: r => r.title }, { h: t("score"), f: r => badge(r.score, r.score >= 15 ? "GREEN" : "GREY") }, { h: t("response_strategy"), f: r => t(`os_${r.strategy}`) }, { h: t("owner"), f: r => r.owner || "—" }, { h: t("status"), f: r => t(`ost_${r.status}`) }] });
  return [respCard, oppCard];
}

export async function reservesCard({ pid, me, p, render, canManage }) {
  const r = await api("GET", `/projects/${pid}/reserves`);
  const exec = ["PMO", "ADMIN", "DECISION_MAKER"].includes(me.role);
  const canSetCont = (canManage && p.baseline_version === 0) || ["PMO", "ADMIN"].includes(me.role);
  const live = ["execution", "closing"].includes(p.state);
  const set = (kind) => {
    const f = formFor([{ k: "v", label: t(`reserve_${kind}`), type: "number", def: r[kind] }], {}), err = h("div");
    modal({ title: t(`reserve_${kind}`), body: h("div", {}, err, ...f.nodes),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("save"), onClick: async (c) => { try { await api("PUT", `/projects/${pid}/reserves`, { [kind]: f.read().v ?? 0 }); c(); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } } }] });
  };
  const draw = (kind) => {
    const f = formFor([{ k: "amount", label: t("amount"), type: "number", req: true }, { k: "reason", label: t("reason"), type: "textarea", req: true }]), err = h("div");
    modal({ title: t(`draw_${kind}`), body: h("div", {}, err, h("p", { class: "muted small" }, t(`draw_${kind}_note`)), ...f.nodes),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("submit"), onClick: async (c) => { try { const v = f.read(); await api("POST", `/projects/${pid}/reserves/drawdowns`, { kind, amount: v.amount, reason: v.reason }); c(); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } } }] });
  };
  const line = (kind) => h("div", { class: "stat" }, h("div", { class: "v" }, num(r[`${kind}_remaining`], 0)), h("div", { class: "l" }, `${t(`reserve_${kind}`)} (${num(r[kind], 0)} ${t("set")}, ${num(r[`${kind}_drawn`], 0)} ${t("drawn")}${r[`${kind}_pending`] ? `, ${num(r[`${kind}_pending`], 0)} ${t("pending")}` : ""})`));
  return h("div", { class: "card", id: "reserves-card" }, h("h2", {}, t("reserves")), h("p", { class: "muted small" }, t("reserves_note")),
    h("div", { class: "stats" }, line("contingency"), line("management")),
    h("p", { class: "row" }, canSetCont ? h("button", { class: "btn small secondary", type: "button", onClick: () => set("contingency") }, t("set_contingency")) : null, exec ? h("button", { class: "btn small secondary", type: "button", onClick: () => set("management") }, t("set_management")) : null,
      canManage && live ? h("button", { class: "btn small", type: "button", onClick: () => draw("contingency") }, t("draw_contingency")) : null, canManage && live ? h("button", { class: "btn small", type: "button", onClick: () => draw("management") }, t("draw_management")) : null),
    table([t("date"), t("type"), t("amount"), t("reason"), t("requested_by"), t("status"), ""], r.drawdowns.map(d => [d.created_on, t(`reserve_${d.kind}`), num(d.amount, 0), d.reason, d.requested_by || "", badge(t(`dd_${d.status}`), d.status === "approved" ? "GREEN" : d.status === "rejected" ? "RED" : "AMBER"),
      exec && d.status === "requested" ? h("span", { class: "row", style: "gap:6px" },
        h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/reserves/drawdowns/${d.id}/decision`, { approve: true }); await render(); }) }, t("approve")),
        h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { const n = await askText(t("reject"), t("reason")); if (n === null) return; await api("POST", `/projects/${pid}/reserves/drawdowns/${d.id}/decision`, { approve: false, note: n }); await render(); }) }, t("reject"))) : ""]), t("none")));
}

export async function qualityCard({ pid, dir, canManage, render, p, wbs }) {
  const [rows, sum] = await Promise.all([api("GET", `/projects/${pid}/quality`), api("GET", `/projects/${pid}/quality-summary`)]);
  const editable = canManage && p.state !== "archived";
  return registerCard({ id: "quality-card", title: t("quality_log"), note: t("quality_note"), base: `/projects/${pid}/quality`, rows, canManage: editable, render, dir,
    head: h("p", {}, `${t("open_defects")}: ${sum.open_defects}/${sum.defects}`, " ", ["critical", "high"].map(s => sum.open_by_severity[s] ? badge(`${sum.open_by_severity[s]} ${t(`sv_${s}`)}`, s === "critical" ? "RED" : "AMBER") : null), sum.closure_rate_pct != null ? ` · ${t("closure_rate")}: ${sum.closure_rate_pct}%` : ""),
    fields: [{ k: "kind", label: t("type"), type: "select", options: so("qk", ["defect", "inspection", "audit", "test"]), def: "defect" }, { k: "title", label: t("title"), req: true },
      { k: "severity", label: t("severity"), type: "select", options: so("sv", ["low", "medium", "high", "critical"]), def: "medium" }, { k: "status", label: t("status"), type: "select", options: so("qs", ["open", "fixed", "verified", "closed"]), def: "open" },
      { k: "deliverable_id", label: t("wk_deliverable"), type: "select", num: true, options: [["", "—"], ...wbs.filter(x => x.kind === "deliverable").map(x => [x.id, `${x.code} · ${x.name}`])] },
      { k: "found_on", label: t("found_on"), type: "date" }, { k: "owner_id", label: t("owner"), type: "user" }, { k: "note", label: t("note"), type: "textarea" }],
    columns: [{ h: t("type"), f: r => t(`qk_${r.kind}`) }, { h: t("title"), f: r => r.title }, { h: t("severity"), f: r => badge(t(`sv_${r.severity}`), r.severity === "critical" ? "RED" : r.severity === "high" ? "AMBER" : "GREY") }, { h: t("wk_deliverable"), f: r => r.deliverable || "—" }, { h: t("owner"), f: r => r.owner || "—" }, { h: t("status"), f: r => t(`qs_${r.status}`) }] });
}

export async function engagementCard({ pid, canManage, render, p }) {
  const rows = await api("GET", `/projects/${pid}/engagement`);
  const editable = canManage && p.state !== "archived";
  const edit = (r) => {
    const f = formFor([{ k: "current", label: t("eng_current"), type: "select", options: so("el", LEVELS), def: r.current || "neutral" }, { k: "desired", label: t("eng_desired"), type: "select", options: so("el", LEVELS), def: r.desired || "supportive" }, { k: "plan", label: t("eng_plan"), type: "textarea" }], r), err = h("div");
    modal({ title: r.name, body: h("div", {}, err, ...f.nodes),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("save"), onClick: async (c) => { try { await api("PUT", `/projects/${pid}/stakeholders/${r.stakeholder_id}/engagement`, f.read()); c(); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } } }] });
  };
  return h("div", { class: "card", id: "engagement-card" }, h("h2", {}, t("engagement_matrix")), h("p", { class: "muted small" }, t("engagement_note")),
    table([t("name"), t("power"), t("eng_current"), t("eng_desired"), t("eng_gap"), t("eng_plan"), ""], rows.map(r => [r.name, r.power, r.current ? t(`el_${r.current}`) : "—", r.desired ? t(`el_${r.desired}`) : "—",
      r.gap == null ? badge(t("not_assessed"), "GREY") : r.gap > 0 ? badge(`+${r.gap}`, r.gap >= 2 ? "RED" : "AMBER") : badge("0", "GREEN"), r.plan || "—",
      editable ? h("button", { class: "btn small secondary", type: "button", onClick: () => edit(r) }, t("assess")) : ""]), t("none")));
}

export function versionsButton(pid, d, { canManage, render }) {
  return h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => {
    const vs = await api("GET", `/projects/${pid}/documents/${d.id}/versions`);
    const file = h("input", { type: "file", accept: ".pdf,.docx,.doc,.txt,.md,.png,.jpg,.jpeg,.xlsx" }), note = h("input"), err = h("div");
    const close = modal({ title: `${d.filename}: ${t("versions")}`, body: h("div", { id: "versions" }, err,
      table([t("version"), t("file"), t("date"), t("uploaded_by"), ""], vs.map(v => [`v${v.version}${v.current ? ` (${t("current")})` : ""}`, v.filename, String(v.uploaded_at).slice(0, 10), v.uploaded_by || "",
        v.current ? "" : h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, () => saveDocument(`/projects/${pid}/documents/${d.id}/versions/${v.id}/content`, v.filename)) }, t("download"))]), t("none")),
      canManage ? h("div", { class: "row", style: "margin-top:12px" }, field(t("file"), file), field(t("note"), note)) : null),
      actions: [{ label: t("close"), class: "secondary", onClick: (c) => c() }, ...(canManage ? [{ label: t("upload_new_version"), onClick: async (c) => {
        const fl = file.files[0]; if (!fl) { mount(err, h("div", { class: "err" }, t("choose_file"))); return; }
        try { await api("POST", `/projects/${pid}/documents/${d.id}/versions`, { filename: fl.name, content_b64: await fileToB64(fl), note: note.value.trim() || null }); c(); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } } }] : [])] });
  }) }, `${t("versions")} (v${d.version || 1})`);
}
