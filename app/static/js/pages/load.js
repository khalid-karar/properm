import { api } from "../api.js";
import { t } from "../i18n.js";
import { askText, badge, bar, field, guarded, h, modal, mount, num, stat, table, toast, today } from "../ui.js";

export default async function (root, { me }) {
  const wk = h("input", { type: "date", value: today() });
  async function render() {
    const r = await api("GET", `/allocations/load?week_of=${wk.value}`);
    const rows = r.staff.map(s => [h("div", {}, s.full_name || s.staff_id, s.leave_days ? h("div", { class: "muted small" }, `${t("leave_short")}: ${s.leave_days} ${t("days_h")}`) : null, s.by_project && s.by_project.length > 1 ? h("div", { class: "muted small" }, s.by_project.map(b => `${b.project}: ${num(b.hours)} h`).join(" · ")) : null), num(s.capacity), num(s.planned), h("div", {}, num(s.actual), bar(s.capacity ? (s.actual / s.capacity) * 100 : 0, s.actual > s.capacity)), s.over_allocated ? badge(t("over_allocated"), "critical") : ""]);
    const rq = ["PMO", "ADMIN"].includes(me.role) ? await api("GET", "/resource-requests") : [];
    const people = rq.length ? (await api("GET", "/directory")).filter(u => ["STAFF", "PM"].includes(u.role)) : [];
    const rqCard = rq.length ? h("div", { class: "card", id: "rr-queue" }, h("h2", {}, t("resource_requests")),
      table([t("project"), t("rr_skill"), t("department"), t("hours_per_week"), t("from"), t("to"), t("requested_by"), ""], rq.map(x => {
        const sel = h("select", {}, people.map(u => h("option", { value: u.id }, u.full_name)));
        return [x.project, x.skill, x.department || "—", num(x.hours_per_week), x.start, x.end, x.requested_by, h("span", { class: "row", style: "gap:6px;flex-wrap:nowrap" }, h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, () => showMatches(x, render)) }, t("best_matches")), sel,
          h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { await api("POST", `/resource-requests/${x.id}/decision`, { approve: true, user_id: Number(sel.value) }); toast(t("saved")); await render(); }) }, t("assign")),
          h("button", { class: "btn small danger", type: "button", onClick: guarded(null, async () => { const r = await askText(t("reject"), t("reason")); if (r === null) return; await api("POST", `/resource-requests/${x.id}/decision`, { approve: false, reason: r }); await render(); }) }, t("reject")))];
      }))) : null;
    mount(root, h("h1", {}, t("load_title")), rqCard,
      h("div", { class: "card" }, h("div", { class: "row" }, field(t("week_of"), wk)), h("p", { class: "muted" }, `${t("week_of")} ${r.week_start}`)),
      h("div", { class: "grid" }, stat(t("over_allocated"), r.staff.filter(s => s.over_allocated).length), stat(t("staff"), r.staff.length)),
      h("div", { class: "card" }, table([t("staff"), t("capacity"), t("planned"), t("actual"), ""], rows, t("no_load"))));
  }
  wk.addEventListener("change", render);
  await render();
}

async function showMatches(x, render) {
  const r = await api("GET", `/resource-requests/${x.id}/matches`);
  let close = () => {};
  const assign = (u) => guarded(null, async () => { await api("POST", `/resource-requests/${x.id}/decision`, { approve: true, user_id: u.id }); close(); toast(t("saved")); await render(); });
  close = modal({ title: `${t("best_matches")}: ${x.skill}`, body: h("div", { id: "matches" }, h("p", { class: "muted small" }, t("matches_note")),
    table([t("name"), t("skill"), t("level"), t("certifications"), t("free_hours"), ""], r.candidates.map(u => [u.name, u.skill || "—", u.level ? t(`lv_${u.level}`) : "—", u.certs.join(", ") || "—",
      h("span", { class: u.fits ? "" : "neg" }, `${num(u.min_free_hours)} / ${num(r.request.hours_per_week)}`),
      h("button", { class: "btn small", type: "button", onClick: assign(u) }, t("assign"))]), t("no_matches"))),
    actions: [{ label: t("close"), class: "secondary", onClick: (c) => c() }] });
}
