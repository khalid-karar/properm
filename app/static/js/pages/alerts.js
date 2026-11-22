import { api, downloadCsv } from "../api.js";
import { getLang, st, t } from "../i18n.js";
import { askText, badge, errorBox, field, guarded, h, modal, mount, table, toast } from "../ui.js";

const STEPS = {
  open: ["acknowledge", "assign", "escalate", "dismiss"],
  acknowledged: ["assign", "escalate", "dismiss"],
  assigned: ["resolve", "assign", "escalate", "dismiss"],
  resolved: ["verify", "reject_verification"],
};
const LABEL = { acknowledge: "acknowledge_a", assign: "assign", escalate: "escalate", dismiss: "dismiss", resolve: "resolve", verify: "verify", reject_verification: "reject_verification" };

export default async function (root, { me }) {
  const [dir, projs] = await Promise.all([api("GET", "/directory"), api("GET", "/projects")]);
  const pnum = (id) => (projs.find(p => p.id === id) || {}).number || `#${id}`;
  const name = (id) => (dir.find(u => u.id === id) || {}).full_name || (id ? `#${id}` : "—");
  const F = { status: "", severity: "", active: false };

  async function render() {
    const q = new URLSearchParams();
    if (F.status) q.set("status", F.status);
    if (F.severity) q.set("severity", F.severity);
    if (F.active) q.set("active_only", "true");
    const rows = await api("GET", `/alerts?${q}`);

    async function act(a, action) {
      const body = { action };
      if (action === "assign") {
        const sel = h("select", {}, dir.map(u => h("option", { value: u.id }, `${u.full_name} (${u.role})`)));
        const due = h("input", { type: "date" });
        const ok = await new Promise((res) => modal({ title: t("assign"), body: h("div", { class: "row" }, field(t("assignee"), sel), field(t("due_date"), due)),
          actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => { c(); res(false); } }, { label: t("assign"), onClick: (c) => { if (!due.value) return; c(); res(true); } }] }));
        if (!ok) return;
        body.assignee_id = Number(sel.value); body.due_date = due.value;
      } else if (action === "dismiss" || action === "reject_verification") {
        const n = await askText(t(LABEL[action]), t("reason")); if (n === null) return; body.note = n;
      }
      try { await api("POST", `/alerts/${a.id}/actions`, body); toast(t("saved")); await render(); } catch (e) { toast(e.lines().join(" · "), "error"); }
    }
    async function suggest(a) {
      const d = await api("POST", `/ai/alerts/${a.id}/suggest`, { lang: getLang() });
      modal({ title: t("ai_suggestion"), body: h("div", {}, h("p", { class: "muted small" }, d.mode === "stub" ? t("ai_stub_note") : `${d.model} · ${t("ai_draft_note")}`), h("p", {}, d.output.text)),
        actions: [{ label: t("close"), class: "secondary", onClick: (c) => c() }] });
    }
    async function showHistory(a) {
      const hist = await api("GET", `/alerts/${a.id}/history`);
      modal({ title: t("history"), body: table([t("date"), t("staff"), t("status"), t("note")], hist.map(x => [String(x.at).slice(0, 16).replace("T", " "), name(x.actor_id), x.action, x.note || ""]), t("none")), actions: [{ label: t("close"), class: "secondary", onClick: (c) => c() }] });
    }
    const status = h("select", { value: F.status, onChange: (e) => { F.status = e.target.value; render(); } }, h("option", { value: "" }, t("all")), ["open", "acknowledged", "assigned", "resolved", "closed", "dismissed"].map(s => h("option", { value: s }, st(s))));
    const sev = h("select", { value: F.severity, onChange: (e) => { F.severity = e.target.value; render(); } }, h("option", { value: "" }, t("all")), ["critical", "warning", "info"].map(s => h("option", { value: s }, st(s))));
    const act_ = h("input", { type: "checkbox", checked: F.active ? true : null, onChange: (e) => { F.active = e.target.checked; render(); } });
    const evalBtn = ["PM", "PMO", "ADMIN"].includes(me.role) ? h("button", { class: "btn gold", type: "button", onClick: guarded(null, async () => {
      let r;
      if (["PMO", "ADMIN"].includes(me.role)) r = await api("POST", "/alerts/evaluate");
      else {                                            // a PM evaluates the projects they manage
        r = { created: 0, updated: 0, cleared: 0 };
        for (const p of projs.filter(p => ["execution", "closing"].includes(p.state))) {
          const x = await api("POST", `/projects/${p.id}/alerts/evaluate`);
          r.created += x.created; r.updated += x.updated; r.cleared += x.cleared;
        }
      }
      toast(`${t("evaluated")}: +${r.created} / ${r.updated} / −${r.cleared}`); await render();
    }) }, t("evaluate")) : null;
    mount(root, h("h1", {}, t("alerts")),
      h("p", {}, h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => downloadCsv("/export/alerts.csv", "alerts.csv")) }, t("export_csv"))),
      h("div", { class: "card" }, h("div", { class: "row" }, field(t("status"), status), field(t("severity"), sev), h("label", { style: "flex-direction:row;align-items:center;gap:6px" }, act_, t("active_only")), h("span", { class: "right" }, evalBtn))),
      h("div", { class: "card" }, table([t("severity"), t("project"), t("cause"), t("suggested_action"), t("status"), t("assignee"), ""],
        rows.map(a => [badge(st(a.severity), a.severity), pnum(a.project_id), h("div", {}, a.cause, a.active ? null : h("div", { class: "small muted" }, `✓ ${t("cleared")}`)), h("span", { class: "small" }, a.suggested_action),
          h("span", {}, badge(st(a.status), a.status === "closed" ? "closed" : a.status === "dismissed" ? "dismissed" : "gold"), a.escalated ? " ▲" : ""), a.assignee_id ? `${name(a.assignee_id)}${a.due_date ? ` · ${a.due_date}` : ""}` : "—",
          h("div", { class: "row", style: "gap:4px" }, (STEPS[a.status] || []).map(s => h("button", { class: "btn secondary small", onClick: guarded(null, () => act(a, s)) }, t(LABEL[s]))), h("button", { class: "btn secondary small", onClick: guarded(null, () => showHistory(a)) }, t("history")), ["PM", "PMO", "ADMIN"].includes(me.role) ? h("button", { class: "btn secondary small", onClick: guarded(null, () => suggest(a)) }, t("ai_suggest")) : null)]), t("none"))));
  }
  await render();
}
