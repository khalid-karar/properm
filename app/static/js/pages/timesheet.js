import { xlsxBtn } from "./importer.js";
import { api, downloadCsv } from "../api.js";
import { t } from "../i18n.js";
import { addDays, badge, errorBox, field, fmtDate, guarded, h, modal, mount, num, parseDate, stat, bar, table, toast, today, warnBox, weekStart } from "../ui.js";

const PHASE = { tendering: "tendering", planning: "planning", execution: "execution", closing: "closing" };

export default async function (root, { me }) {
  const S = { week: weekStart(new Date()), editing: null, codes: {}, projects: [], actCache: {} };
  [S.codes, S.projects] = await Promise.all([api("GET", "/config/codes"), api("GET", "/projects")]);
  const bookable = S.projects.filter(p => PHASE[p.state]);

  async function activitiesOf(pid) {
    if (!S.actCache[pid]) S.actCache[pid] = await api("GET", `/projects/${pid}`);
    const p = S.actCache[pid];
    return p.activities.filter(a => a.phase === PHASE[p.state] && (a.phase !== "execution" || a.locked));
  }

  async function render() {
    const wk = fmtDate(S.week);
    const [entries, util, wkst] = await Promise.all([api("GET", `/timesheets/mine?week_of=${wk}`), api("GET", `/me/utilization?week_of=${wk}`), api("GET", `/me/week?week_of=${wk}`)]);
    const wnote = h("input", { placeholder: t("week_note_ph"), style: "min-width:260px" }), werr = h("div");
    const dayName = (iso) => new Date(iso + "T00:00:00").toLocaleDateString(undefined, { weekday: "short" });
    const weekCard = h("div", { class: "card", id: "week-card" }, h("h2", {}, t("week_status"), " ",
        wkst.submitted ? badge(`${t("week_submitted")} ${wkst.submitted.at.slice(0, 10)}`, "GREEN") : badge(t("week_not_submitted"), "AMBER")),
      h("div", { class: "days" }, wkst.days.map(d => h("div", { class: `day ${d.off ? "off" : wkst.missing_days.includes(d.date) ? "miss" : d.hours ? "ok" : ""}`, title: d.holiday || "" },
        h("div", { class: "dn" }, dayName(d.date)), h("div", { class: "dh" }, d.off === "leave" ? t("leave_short") : d.off === "holiday" ? t("holiday_short") : d.off ? "—" : `${num(d.hours)} h`)))),
      wkst.missing_days.length ? h("p", { class: "small neg" }, `${t("missing_days_h")}: ${wkst.missing_days.length}`) : null,
      wkst.can_submit ? h("div", { class: "row", style: "margin-top:8px" }, wkst.missing_days.length ? field(t("note"), wnote) : null,
        h("button", { class: "btn", type: "button", id: "submit-week", onClick: guarded(null, async () => { mount(werr); try { await api("POST", "/me/week/submit", { week_of: wk, note: wnote.value.trim() || null }); toast(t("week_submitted")); await render(); } catch (e) { mount(werr, errorBox(e)); } }) },
          wkst.submitted ? t("resubmit_week") : t("submit_week"))) : null, werr);
    const projName = (id) => (S.projects.find(p => p.id === id) || {}).number || id;
    await Promise.all([...new Set(entries.filter(e => e.project_id).map(e => e.project_id))].map(async (pid) => { if (!S.actCache[pid]) { try { S.actCache[pid] = await api("GET", `/projects/${pid}`); } catch { /* no access: fall back to id */ } } }));
    const actCode = (e) => { const pr = S.actCache[e.project_id]; const a = pr && pr.activities.find(x => x.id === e.activity_id); return a ? a.code : `#${e.activity_id}`; };
    const live = util.submitted + util.approved;
    mount(root,
      h("h1", {}, t("nav_timesheet")),
      h("p", {}, h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, () => downloadCsv("/export/timesheets.csv", "timesheets.csv")) }, t("export_csv")), xlsxBtn("/export/timesheets.xlsx", "timesheets.xlsx")),
      h("div", { class: "row weeknav", style: "margin-bottom:12px" },
        h("button", { class: "btn secondary small", onClick: () => { S.week = addDays(S.week, -7); render(); } }, t("prev")),
        h("strong", {}, `${t("week_of")} ${wk}`),
        h("button", { class: "btn secondary small", onClick: () => { S.week = addDays(S.week, 7); render(); } }, t("next")),
        h("button", { class: "btn secondary small", onClick: () => { S.week = weekStart(new Date()); render(); } }, t("this_week")),
        h("button", { class: "btn secondary small", type: "button", id: "copy-week", onClick: guarded(null, async () => {
          if (!confirm(t("copy_confirm"))) return;
          const r = await api("POST", "/timesheets/copy-week", { from_week_of: fmtDate(addDays(S.week, -7)), to_week_of: wk });
          toast(`${t("copy_done")}: ${r.created}` + (r.skipped.length ? ` · ${t("copy_skipped")}: ${r.skipped.length}` : ""));
          await render();
        }) }, t("copy_last_week"))),
      h("div", { class: "grid", style: "margin-bottom:16px" },
        stat(t("capacity"), `${num(util.capacity)} h`), stat(t("submitted"), `${num(util.submitted)} h`), stat(t("approved"), `${num(util.approved)} h`),
        stat(t("utilization"), `${num(util.utilization_pct)}%`), stat(t("remaining"), `${num(util.remaining_capacity)} h`),
        util.overtime_entries ? stat(t("overtime"), util.overtime_entries) : null),
      h("div", { class: "card" }, bar(util.utilization_pct, live > util.capacity),
        Object.keys(util.per_project).length ? h("div", { class: "row", style: "margin-top:12px; gap:8px" }, h("span", { class: "muted small" }, `${t("this_week_by_project")}:`),
          Object.entries(util.per_project).map(([k, v]) => badge(`${/^\d+$/.test(k) ? projName(Number(k)) : k}: ${num(v)} h`, "GREY"))) : null),
      weekCard,
      await form(),
      h("div", { class: "card" }, h("h2", {}, t("my_entries")),
        table([t("date"), t("project"), t("activity"), t("hours"), t("status"), t("flags"), ""],
          entries.map(e => [e.entry_date, e.project_id ? projName(e.project_id) : `${t("non_project")}: ${e.code}`,
            e.activity_id ? actCode(e) : "", num(e.hours) + (e.original_hours ? ` (${num(e.original_hours)})` : ""),
            badge(t(e.status), e.status) , h("span", { class: "small muted" }, [e.overtime_flag ? t("overtime") : null, e.decision_reason, ...(e.flags || [])].filter(Boolean).join(" · ")),
            e.status !== "approved" ? h("span", { class: "row", style: "gap:6px;flex-wrap:nowrap" }, h("button", { class: "btn secondary small", onClick: () => { S.editing = e; render(); } }, t("edit")),
              h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, async () => { if (!confirm(t("withdraw_confirm"))) return; await api("DELETE", `/timesheets/${e.id}`); toast(t("withdrawn")); if (S.editing?.id === e.id) S.editing = null; await render(); }) }, t("withdraw"))) : ""]),
          t("no_entries"))));
  }

  async function form() {
    const ed = S.editing;
    const kind = h("select", {}, h("option", { value: "project" }, t("project_time")), h("option", { value: "code" }, t("non_project")));
    const proj = h("select", {}, bookable.map(p => h("option", { value: p.id }, `${p.number} · ${p.name} (${t(p.state)})`)));
    const act = h("select");
    const code = h("select", {}, Object.entries(S.codes).map(([k, v]) => h("option", { value: k }, `${k} · ${v}`)));
    const date = h("input", { type: "date", value: ed ? ed.entry_date : today(), max: ed ? undefined : undefined });
    const hours = h("input", { type: "number", step: "0.25", min: "0.25", max: "24", value: ed ? ed.hours : "8", style: "width:90px" });
    const desc = h("input", { value: ed?.description || "", style: "min-width:220px" });
    const err = h("div"), hint = h("div", { class: "muted small", style: "margin-top:6px" });
    const projWrap = h("div", { class: "row" }, field(t("project"), proj), field(t("activity"), act));
    const codeWrap = h("div", { class: "row", style: "display:none" }, field(t("code"), code));

    async function loadActs() {
      mount(act);
      if (!proj.value) return;
      const acts = await activitiesOf(Number(proj.value));
      acts.forEach(a => act.append(h("option", { value: a.id }, `${a.code} · ${a.name}`)));
      if (ed?.activity_id) act.value = ed.activity_id;
      await showHint();
    }
    async function showHint() {
      mount(hint);
      if (kind.value === "code" || !proj.value || !act.value) return;
      try {
        const x = await api("GET", `/timesheets/hints?project_id=${proj.value}&activity_id=${act.value}`);
        if (x.cap == null) return;
        const left = x.remaining;
        mount(hint, `${x.personal_limit ? t("your_limit") : t("activity_cap")}: ${num(x.used)} / ${num(x.cap)} h · `, h("strong", { style: left < 0 ? "color:var(--red)" : "" }, `${num(left)} h ${t("left")}`));
      } catch { /* hint is optional */ }
    }
    act.addEventListener("change", showHint);
    function sync() { const c = kind.value === "code"; projWrap.style.display = c ? "none" : ""; codeWrap.style.display = c ? "" : "none"; }
    kind.addEventListener("change", () => { sync(); showHint(); });
    proj.addEventListener("change", loadActs);
    if (ed) {
      if (ed.code) { kind.value = "code"; code.value = ed.code; } else if (ed.project_id) proj.value = ed.project_id;
      sync();
    }
    await loadActs();

    function payload() {
      const base = { entry_date: date.value, hours: Number(hours.value), description: desc.value.trim() || null };
      return kind.value === "code" ? { ...base, code: code.value } : { ...base, project_id: Number(proj.value), activity_id: Number(act.value) };
    }

    async function send(extra = {}) {
      const body = { ...payload(), ...extra };
      try {
        await api(ed ? "PUT" : "POST", ed ? `/timesheets/${ed.id}` : "/timesheets", body);
        toast(t("entry_saved"));
        S.editing = null;
        await render();
      } catch (e) {
        const d = e.data || {};
        const overtime = d.detail === "Overtime reason required" || (e.status === 409 && (d.violations || []).some(v => v.rule === "R1"));
        if ((e.status === 409 || overtime) && d.violations) return confirmModal(d.violations, overtime, body);
        mount(err, errorBox(e));
      }
    }

    function confirmModal(violations, needReason, body) {
      const ack = h("input", { type: "checkbox" });
      const reason = h("textarea", { value: body.overtime_reason || "" });
      const msg = h("div");
      modal({
        title: t("warnings_title"),
        body: h("div", {}, warnBox(violations.filter(v => v.severity !== "BLOCK").map(v => `${v.rule}: ${v.message}`)),
          needReason ? h("label", {}, t("overtime_reason"), reason) : null,
          h("label", { style: "flex-direction:row;align-items:center;gap:8px;margin-top:10px" }, ack, t("acknowledge")), msg),
        actions: [
          { label: t("cancel"), class: "secondary", onClick: (c) => c() },
          { label: t("acknowledge_submit"), onClick: (c) => {
              if (!ack.checked || (needReason && !reason.value.trim())) { mount(msg, h("div", { class: "err" }, needReason ? `${t("overtime_reason")} + ${t("acknowledge")}` : t("acknowledge"))); return; }
              c();
              send({ acknowledge_warnings: true, overtime_reason: needReason ? reason.value.trim() : null });
          } }],
      });
    }

    const btn = h("button", { class: "btn ts-submit", type: "button", id: "ts-submit" }, ed ? t("save") : t("submit"));
    btn.addEventListener("click", guarded(btn, async () => { mount(err); await send(); }));
    return h("div", { class: "card ts-form", id: "ts-form" }, h("h2", {}, ed ? t("edit_entry") : t("new_entry")),
      h("div", { class: "row" }, field("", kind), projWrap, codeWrap, field(t("date"), date), field(t("hours"), hours), h("div", { class: "grow" }, field(t("description"), desc)), btn,
        ed ? h("button", { class: "btn secondary", type: "button", onClick: () => { S.editing = null; render(); } }, t("cancel")) : null),
      hint, err);
  }
  await render();
}
