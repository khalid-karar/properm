// Leave: book time off ahead, see decisions; approvers decide; managers see who is away.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { askText, badge, errorBox, field, guarded, h, mount, table, toast, today } from "../ui.js";

const KINDS = ["annual", "sick", "training", "other"];
const CLS = { approved: "GREEN", requested: "AMBER", rejected: "RED", cancelled: "GREY" };

export default async function (root, { me }) {
  const isMgr = ["PM", "PMO", "ADMIN", "PROGRAM_MANAGER", "DECISION_MAKER"].includes(me.role);
  async function render() {
    const [mine, queue, cal] = await Promise.all([api("GET", "/me/leave"), api("GET", "/leave/queue"), isMgr ? api("GET", "/leave/calendar") : []]);
    const f = { s: h("input", { type: "date", value: today() }), e: h("input", { type: "date", value: today() }), k: h("select", {}, KINDS.map(k => h("option", { value: k }, t(`lk_${k}`)))), n: h("input", { style: "min-width:220px" }) };
    const err = h("div");
    const decide = (x, approve) => guarded(null, async () => {
      let reason = null;
      if (!approve) { reason = await askText(t("reject"), t("reason")); if (reason === null) return; }
      await api("POST", `/leave/${x.id}/decision`, { approve, reason }); toast(t("saved")); await render();
    });
    mount(root, h("h1", {}, t("nav_leave")), h("p", { class: "muted" }, t("leave_note")),
      queue.length ? h("div", { class: "card", id: "leave-queue" }, h("h2", {}, t("leave_requests")),
        table([t("staff"), t("from"), t("to"), t("days_h"), t("type"), t("note"), ""], queue.map(x => [x.user, x.start, x.end, x.working_days, t(`lk_${x.kind}`), x.note || "",
          h("span", { class: "row", style: "gap:6px" }, h("button", { class: "btn small", type: "button", onClick: decide(x, true) }, t("approve")), h("button", { class: "btn small danger", type: "button", onClick: decide(x, false) }, t("reject")))]))) : null,
      h("div", { class: "card", id: "leave-form" }, h("h2", {}, t("book_leave")),
        h("div", { class: "row" }, field(t("from"), f.s), field(t("to"), f.e), field(t("type"), f.k), field(t("note"), f.n),
          h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(err); try { await api("POST", "/leave", { start: f.s.value, end: f.e.value, kind: f.k.value, note: f.n.value.trim() || null }); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } }) }, t("request"))), err),
      h("div", { class: "card" }, h("h2", {}, t("my_leave")),
        table([t("from"), t("to"), t("days_h"), t("type"), t("status"), t("reason"), ""], mine.map(x => [x.start, x.end, x.working_days, t(`lk_${x.kind}`), badge(t(`lv_${x.status}`), CLS[x.status]), x.decision_reason || "",
          ["requested", "approved"].includes(x.status) && (x.status === "requested" || x.start > today()) ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/leave/${x.id}`); await render(); }) }, t("cancel")) : ""]), t("none"))),
      isMgr ? h("div", { class: "card" }, h("h2", {}, t("who_is_away")),
        table([t("staff"), t("from"), t("to"), t("days_h"), t("status")], cal.map(x => [x.user, x.start, x.end, x.working_days, badge(t(`lv_${x.status}`), CLS[x.status])]), t("none"))) : null);
  }
  await render();
}
