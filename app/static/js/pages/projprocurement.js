// Project "Procurement" tab: contracts, payment milestones to invoice and payment, vendor reviews.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { askText, badge, guarded, h, mount, num } from "../ui.js";
import { registerCard } from "../register.js";

const CS = { draft: "GREY", active: "GREEN", completed: "GREY", terminated: "RED" };
const PS = { planned: "GREY", achieved: "AMBER", invoiced: "AMBER", paid: "GREEN" };
const stars = (n) => "★".repeat(Math.round(n)) + "☆".repeat(5 - Math.round(n));

export async function procurement(body, p, { pid, dir, canManage, render }) {
  const [cons, pays, revs] = await Promise.all([api("GET", `/projects/${pid}/contracts`), api("GET", `/projects/${pid}/payments`), api("GET", `/projects/${pid}/vendor-reviews`)]);
  const editable = canManage && p.state !== "archived";
  const copts = [["", "—"], ...cons.map(c => [c.id, `${c.number} · ${c.vendor}`])];
  const score = (k) => ({ k, label: t(`vr_${k}`), type: "select", num: true, req: true, def: 3, options: [1, 2, 3, 4, 5].map(n => [n, String(n)]) });
  const totals = cons.reduce((a, c) => ({ v: a.v + (c.value || 0), i: a.i + c.invoiced, pd: a.pd + c.paid }), { v: 0, i: 0, pd: 0 });

  const cCard = registerCard({ id: "contracts-card", title: t("contracts"), note: t("contracts_note"), base: `/projects/${pid}/contracts`, rows: cons, canManage: editable, render, dir,
    head: cons.length ? h("div", { class: "stats" }, h("div", { class: "stat" }, h("div", { class: "v" }, num(totals.v, 0)), h("div", { class: "l" }, t("contract_value"))),
      h("div", { class: "stat" }, h("div", { class: "v" }, num(totals.i, 0)), h("div", { class: "l" }, t("invoiced"))), h("div", { class: "stat" }, h("div", { class: "v" }, num(totals.pd, 0)), h("div", { class: "l" }, t("paid")))) : null,
    fields: [{ k: "number", label: t("number"), req: true }, { k: "title", label: t("title"), req: true }, { k: "vendor", label: t("vendor"), req: true }, { k: "value", label: t("contract_value"), type: "number" }, { k: "currency", label: t("currency"), def: "SAR" },
      { k: "start_date", label: t("planned_start"), type: "date" }, { k: "end_date", label: t("planned_end"), type: "date" },
      { k: "status", label: t("status"), type: "select", options: ["draft", "active", "completed", "terminated"].map(x => [x, t(`ct_${x}`)]), def: "draft" }, { k: "owner_id", label: t("owner"), type: "user" }, { k: "note", label: t("note"), type: "textarea" }],
    columns: [{ h: t("number"), f: c => c.number }, { h: t("vendor"), f: c => h("span", { title: c.title }, c.vendor) }, { h: t("contract_value"), f: c => c.value == null ? "—" : `${num(c.value, 0)} ${c.currency}` },
      { h: t("invoiced"), f: c => c.value ? `${num(c.invoiced, 0)} (${c.pct_invoiced}%)` : num(c.invoiced, 0) },
      { h: t("ledger_cost"), f: c => h("span", { class: c.ledger_cost > (c.value || Infinity) ? "neg" : "", title: t("ledger_note") }, num(c.ledger_cost, 0)) },
      { h: t("ends"), f: c => c.end_date ? h("span", { class: c.expires_in != null && c.expires_in <= 30 ? "neg" : "" }, c.end_date) : "—" },
      { h: t("vendor_rating"), f: c => c.rating ? h("span", { title: String(c.rating) }, stars(c.rating)) : "—" },
      { h: t("status"), f: c => h("span", {}, badge(t(`ct_${c.status}`), CS[c.status]), c.overdue_payments ? badge(`${c.overdue_payments} ${t("overdue")}`, "RED") : null, c.unscheduled > 0.5 && c.value ? h("div", { class: "muted small" }, `${t("unscheduled")}: ${num(c.unscheduled, 0)}`) : null) }] });

  const next = { planned: "achieved", achieved: "invoiced", invoiced: "paid" };
  const advance = (r) => guarded(null, async () => {
    const to = next[r.status];
    const body = { status: to };
    if (to === "invoiced") { const no = await askText(t("pm_to_invoiced"), t("invoice_no")); if (!no) return; body.invoice_no = no; }
    await api("PATCH", `/projects/${pid}/payments/${r.id}`, body); await render();
  });
  const pCard = registerCard({ id: "payments-card", title: t("payment_milestones"), note: t("payments_note"), base: `/projects/${pid}/payments`, rows: pays, canManage: editable, render, dir,
    fields: [{ k: "contract_id", label: t("contract"), type: "select", num: true, req: true, options: copts.slice(1) }, { k: "name", label: t("name"), req: true }, { k: "amount", label: t("amount"), type: "number", req: true }, { k: "due_date", label: t("due_date"), type: "date" },
      { k: "status", label: t("status"), type: "select", options: ["planned", "achieved", "invoiced", "paid"].map(x => [x, t(`pm_${x}`)]), def: "planned" }, { k: "invoice_no", label: t("invoice_no") }],
    columns: [{ h: t("contract"), f: r => r.contract }, { h: t("name"), f: r => r.name }, { h: t("amount"), f: r => num(r.amount, 0) }, { h: t("due_date"), f: r => h("span", { class: r.overdue ? "neg" : "" }, r.due_date || "—") },
      { h: t("invoice_no"), f: r => r.invoice_no || "—" }, { h: t("status"), f: r => badge(t(`pm_${r.status}`), PS[r.status]) }],
    actions: (r) => editable && next[r.status] ? [h("button", { class: "btn small", type: "button", onClick: advance(r) }, t(`pm_to_${next[r.status]}`))] : [] });

  const rCard = registerCard({ id: "reviews-card", title: t("vendor_reviews"), note: t("reviews_note"), base: `/projects/${pid}/vendor-reviews`, rows: revs, canManage: editable, render, dir,
    fields: [{ k: "contract_id", label: t("contract"), type: "select", num: true, req: true, options: copts.slice(1) }, { k: "review_date", label: t("date"), type: "date", req: true, def: new Date().toISOString().slice(0, 10) }, score("quality"), score("schedule"), score("communication"), { k: "note", label: t("note"), type: "textarea" }],
    columns: [{ h: t("date"), f: r => r.review_date }, { h: t("contract"), f: r => r.contract }, { h: t("vr_quality"), f: r => r.quality }, { h: t("vr_schedule"), f: r => r.schedule }, { h: t("vr_communication"), f: r => r.communication }, { h: t("average"), f: r => stars(r.average) }, { h: t("note"), f: r => r.note || "" }] });

  mount(body, cCard, pCard, rCard);
}
