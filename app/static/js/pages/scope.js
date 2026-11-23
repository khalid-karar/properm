// Project "Scope" tab: charter, WBS with acceptance, requirements with traceability, assumption log.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { askText, badge, errorBox, field, guarded, h, mount, stat, toast } from "../ui.js";
import { objectivePicker, registerCard } from "../register.js";
import { qualityCard } from "./projdepth.js";

const ACCEPT = ["PMO", "ADMIN", "DECISION_MAKER"];
const CH = ["purpose", "objectives", "success_criteria", "in_scope", "out_of_scope", "key_risks", "approval_requirements"];
const DST = { planned: "GREY", in_progress: "AMBER", submitted: "AMBER", accepted: "GREEN", rejected: "RED" };
const opts = (pref, list) => list.map(x => [x, t(`${pref}_${x}`)]);

export async function scope(body, p, { pid, me, dir, canManage, render }) {
  const [objs, sum, ch, wbs, reqs, asm] = await Promise.all([api("GET", `/projects/${pid}/objectives`), api("GET", `/projects/${pid}/scope-summary`), api("GET", `/projects/${pid}/charter`),
    api("GET", `/projects/${pid}/wbs`), api("GET", `/projects/${pid}/requirements`), api("GET", `/projects/${pid}/assumptions`)]);
  const who = (id) => (dir.find(u => u.id === id) || {}).full_name || "—";
  const editable = canManage && p.state !== "archived";
  const canAccept = ACCEPT.includes(me.role);

  // summary
  const d = sum.deliverables, rq = sum.requirements;
  const stats = h("div", { class: "stats" }, stat(t("charter"), t(`ch_${sum.charter}`)), stat(t("sc_accepted"), d.total ? `${d.accepted}/${d.total}` : "—"),
    stat(t("sc_verified"), rq.total ? `${rq.verified}/${rq.total}` : "—"), stat(t("sc_open_assumptions"), sum.assumptions.open),
    stat(t("sc_untraced"), rq.without_deliverable.length));

  // charter
  const inputs = Object.fromEntries(CH.map(k => [k, h("textarea", { rows: 3, disabled: !editable || ch.status === "approved" }, ch[k] || "")]));
  CH.forEach(k => { inputs[k].value = ch[k] || ""; });
  const cerr = h("div");
  const chBtn = (action, label, cls = "") => h("button", { class: `btn ${cls}`, type: "button", onClick: guarded(null, async () => { mount(cerr); try { await api("POST", `/projects/${pid}/charter/decision`, { action }); await render(); } catch (e) { mount(cerr, errorBox(e)); } }) }, label);
  const charter = h("div", { class: "card", id: "charter-card" }, h("h2", {}, t("charter"), " ", badge(t(`ch_${ch.status}`), ch.status === "approved" ? "GREEN" : "AMBER")),
    ch.approved_by ? h("p", { class: "muted small" }, `${t("approved_by")}: ${ch.approved_by} · ${ch.approved_on}`) : h("p", { class: "muted small" }, t("charter_note")),
    ...CH.map(k => field(t(`ch_${k}`), inputs[k])), cerr,
    h("p", { class: "row" },
      editable && ch.status !== "approved" ? h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(cerr); try { await api("PUT", `/projects/${pid}/charter`, Object.fromEntries(CH.map(k => [k, inputs[k].value]))); toast(t("saved")); await render(); } catch (e) { mount(cerr, errorBox(e)); } }) }, t("save")) : null,
      canAccept && ch.status !== "approved" ? chBtn("approve", t("approve"), "secondary") : null,
      (canAccept || canManage) && ch.status === "approved" && p.state !== "archived" ? chBtn("reopen", t("reopen"), "secondary") : null));

  // WBS
  const note = async (title, required) => { try { return await askText(title, t("note"), { required }); } catch { return null; } };
  const act = (r, what, payload) => guarded(null, async () => { await api("POST", `/projects/${pid}/wbs/${r.id}/${what}`, payload); await render(); });
  const wbsRows = [...wbs].sort((a, b) => a.code.localeCompare(b.code, undefined, { numeric: true }));
  const depth = (r) => { let n = 0, x = r; while (x && x.parent_id) { x = wbs.find(y => y.id === x.parent_id); n++; if (n > 8) break; } return n; };
  const wbsCard = registerCard({ id: "wbs-card", title: t("wbs"), note: t("wbs_note"), base: `/projects/${pid}/wbs`, rows: wbsRows, canManage: editable, render, dir,
    fields: [{ k: "code", label: t("code"), req: true }, { k: "name", label: t("name"), req: true },
      { k: "kind", label: t("kind"), type: "select", options: opts("wk", ["deliverable", "work_package"]), def: "deliverable" },
      { k: "parent_id", label: t("wbs_parent"), type: "select", num: true, options: [["", "—"], ...wbs.map(x => [x.id, `${x.code} · ${x.name}`])] },
      { k: "acceptance_criteria", label: t("acceptance_criteria"), type: "textarea" }, { k: "description", label: t("description"), type: "textarea" },
      { k: "activity_id", label: t("activity"), type: "select", num: true, options: [["", "—"], ...(p.activities || []).map(a => [a.id, `${a.code} · ${a.name}`])] },
      { k: "owner_id", label: t("owner"), type: "user" }, { k: "due_date", label: t("due_date"), type: "date" }],
    columns: [{ h: t("code"), f: r => h("span", { style: `padding-inline-start:${depth(r) * 16}px` }, r.code) }, { h: t("name"), f: r => h("span", { title: r.acceptance_criteria || "" }, r.name) },
      { h: t("kind"), f: r => t(`wk_${r.kind}`) }, { h: t("activity"), f: r => r.activity || "—" }, { h: t("owner"), f: r => r.owner || "—" }, { h: t("due_date"), f: r => r.due_date || "—" },
      { h: t("status"), f: r => h("span", {}, badge(t(`dl_${r.status}`), DST[r.status]), r.decision_note ? h("div", { class: "muted small" }, r.decision_note) : null) }],
    actions: (r) => r.kind !== "deliverable" ? [] : [
      editable && ["planned", "rejected"].includes(r.status) ? h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/wbs/${r.id}/${r.status === "planned" ? "start" : "submit"}`); await render(); }) }, r.status === "planned" ? t("start") : t("resubmit")) : null,
      editable && r.status === "in_progress" ? h("button", { class: "btn small", type: "button", onClick: act(r, "submit") }, t("submit_acceptance")) : null,
      canAccept && r.status === "submitted" ? h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { const n = await note(t("accept_deliverable"), false); if (n === null) return; await api("POST", `/projects/${pid}/wbs/${r.id}/decision`, { accept: true, note: n || null }); await render(); }) }, t("accept")) : null,
      canAccept && r.status === "submitted" ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { const n = await note(t("reject_deliverable"), true); if (!n) return; await api("POST", `/projects/${pid}/wbs/${r.id}/decision`, { accept: false, note: n }); await render(); }) }, t("reject")) : null] });

  // requirements
  const reqCard = registerCard({ id: "req-card", title: t("requirements"), note: t("req_note"), base: `/projects/${pid}/requirements`, rows: reqs, canManage: editable, render, dir,
    head: rq.without_deliverable.length ? h("p", { class: "warn small" }, `${t("sc_untraced")}: ${rq.without_deliverable.join(", ")}`) : null,
    fields: [{ k: "code", label: t("code"), req: true }, { k: "title", label: t("title"), req: true }, { k: "description", label: t("description"), type: "textarea" }, { k: "source", label: t("source") },
      { k: "priority", label: t("priority"), type: "select", options: opts("rp", ["must", "should", "could", "wont"]), def: "must" },
      { k: "status", label: t("status"), type: "select", options: opts("rs", ["proposed", "approved", "implemented", "verified", "dropped"]), def: "proposed" },
      { k: "deliverable_id", label: t("wk_deliverable"), type: "select", num: true, options: [["", "—"], ...wbs.filter(x => x.kind === "deliverable").map(x => [x.id, `${x.code} · ${x.name}`])] },
      { k: "test_ref", label: t("test_ref") }],
    columns: [{ h: t("code"), f: r => r.code }, { h: t("title"), f: r => r.title }, { h: t("priority"), f: r => t(`rp_${r.priority}`) }, { h: t("wk_deliverable"), f: r => r.deliverable || badge(t("untraced"), "AMBER") },
      { h: t("test_ref"), f: r => r.test_ref || "—" }, { h: t("status"), f: r => t(`rs_${r.status}`) }] });

  // assumptions
  const asmCard = registerCard({ id: "asm-card", title: t("assumption_log"), note: t("asm_note"), base: `/projects/${pid}/assumptions`, rows: asm, canManage: editable, render, dir,
    fields: [{ k: "kind", label: t("kind"), type: "select", options: opts("ak", ["assumption", "constraint", "dependency", "exclusion"]), def: "assumption" }, { k: "text", label: t("text"), type: "textarea", req: true },
      { k: "owner_id", label: t("owner"), type: "user" }, { k: "validate_by", label: t("validate_by"), type: "date" },
      { k: "status", label: t("status"), type: "select", options: opts("as", ["open", "validated", "invalid"]), def: "open" }, { k: "note", label: t("note"), type: "textarea" }],
    columns: [{ h: t("kind"), f: r => t(`ak_${r.kind}`) }, { h: t("text"), f: r => r.text }, { h: t("owner"), f: r => who(r.owner_id) },
      { h: t("validate_by"), f: r => h("span", { class: r.status === "open" && r.validate_by && r.validate_by < new Date().toISOString().slice(0, 10) ? "neg" : "" }, r.validate_by || "—") },
      { h: t("status"), f: r => badge(t(`as_${r.status}`), r.status === "validated" ? "GREEN" : r.status === "invalid" ? "RED" : "GREY") }] });

  const pick = objectivePicker(objs.available, objs.selected, !editable);
  const oerr = h("div");
  const objCard = h("div", { class: "card", id: "objectives-pick" }, h("h2", {}, t("nav_strategy")), h("p", { class: "muted small" }, t("project_objectives_note")), pick.node, oerr,
    editable ? h("p", {}, h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(oerr); try { await api("PUT", `/projects/${pid}/objectives`, { objective_ids: pick.ids() }); toast(t("saved")); } catch (e) { mount(oerr, errorBox(e)); } }) }, t("save"))) : null);

  mount(body, stats, charter, objCard, wbsCard, reqCard, await qualityCard({ pid, dir, canManage, render, p, wbs }), asmCard);
}
