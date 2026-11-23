import { api } from "../api.js";
import { t } from "../i18n.js";
import { jobsCard, restoreCard, retentionCard } from "./ops.js";
import { badge, errorBox, field, guarded, h, modal, mount, num, table, toast, today } from "../ui.js";

const ROLES = ["STAFF", "PM", "PMO", "PROGRAM_MANAGER", "DECISION_MAKER", "ADMIN"];

export default async function (root) {
  function editUser(u, users, me) {
    const f = { jt: h("input", { value: u.job_title || "" }), dep: depInput(u.department), name: h("input", { value: u.full_name }), role: h("select", {}, ROLES.map(r => h("option", { value: r, selected: r === u.role }, r))),
      grade: h("input", { value: u.rate_grade || "" }), email: h("input", { type: "email", value: u.email || "" }), cap: h("input", { type: "number", value: u.capacity_hours_week, style: "width:80px" }), ccb: h("input", { type: "checkbox", checked: u.is_ccb }),
      active: h("input", { type: "checkbox", checked: u.active, disabled: u.id === me.id }), pw: h("input", { type: "password", autocomplete: "new-password" }),
      lm: h("select", {}, h("option", { value: "" }, "—"), users.filter(x => x.id !== u.id).map(x => h("option", { value: x.id, selected: x.id === u.line_manager_id }, x.full_name))),
      dg: h("select", {}, h("option", { value: "" }, "—"), users.filter(x => x.id !== u.id).map(x => h("option", { value: x.id, selected: x.id === u.delegate_id }, x.full_name))) };
    const err = h("div");
    modal({ title: `${t("edit")}: ${u.staff_id}`,
      body: h("div", {}, h("div", { class: "row" }, field(t("full_name"), f.name), field(t("job_title"), f.jt), field(t("department"), f.dep), field(t("role"), f.role), field(t("grade"), f.grade), field(t("capacity"), f.cap), field(t("line_manager"), f.lm), field(t("delegate"), f.dg), field(t("email"), f.email)),
        h("div", { class: "row", style: "margin-top:10px" }, field(t("is_ccb"), f.ccb), field(t("active"), f.active), field(t("new_password"), f.pw)), err),
      actions: [{ label: t("cancel"), onClick: (close) => close() }, { label: t("save"), class: "primary", onClick: async (close) => {
        mount(err);
        const body = { full_name: f.name.value.trim(), job_title: f.jt.value.trim() || null, department: f.dep.value.trim() || null, role: f.role.value, rate_grade: f.grade.value.trim() || null, capacity_hours_week: Number(f.cap.value), is_ccb: f.ccb.checked, line_manager_id: f.lm.value ? Number(f.lm.value) : null, delegate_id: f.dg.value ? Number(f.dg.value) : null, email: f.email.value.trim() || null, active: f.active.checked };
        if (f.pw.value) body.new_password = f.pw.value;
        try { await api("PATCH", `/users/${u.id}`, body); toast(t("saved")); close(); await render(); } catch (e) { mount(err, errorBox(e)); }
      } }] });
  }

  async function handover(u, users) {
    const w = await api("GET", `/admin/users/${u.id}/handover`);
    const to = h("select", {}, users.filter(x => x.active && x.id !== u.id).map(x => h("option", { value: x.id }, `${x.full_name} (${x.role})`)));
    const deact = h("input", { type: "checkbox", checked: true }), err = h("div");
    const line = (k, v) => (Array.isArray(v) ? v.length : v) ? h("li", {}, `${t(`ho_${k}`)}: ${Array.isArray(v) ? v.join(", ") : v}`) : null;
    modal({ title: `${t("handover")}: ${u.full_name}`, body: h("div", {}, err,
      w.total ? h("ul", {}, Object.entries(w).filter(([k]) => k !== "total" && k !== "own_entries_pending").map(([k, v]) => line(k, v))) : h("p", { class: "muted" }, t("ho_nothing")),
      w.own_entries_pending ? h("p", { class: "muted small" }, `${t("ho_own_entries_pending")}: ${w.own_entries_pending}`) : null,
      field(t("ho_to"), to), h("label", { class: "check" }, deact, " ", t("ho_deactivate")), h("p", { class: "muted small" }, t("ho_note"))),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("handover"), onClick: async (c) => {
        try { const r = await api("POST", `/admin/users/${u.id}/handover`, { to_user_id: Number(to.value), deactivate: deact.checked }); toast(`${t("saved")}: ${Object.values(r.moved).reduce((a, b) => a + b, 0)} ${t("ho_moved")}`); c(); await render(); }
        catch (e) { mount(err, errorBox(e)); } } }] });
  }

  let DEPTS = [];
  const depInput = (v) => DEPTS.length ? h("select", {}, h("option", { value: "" }, "—"), DEPTS.map(d => h("option", { value: d, selected: d === v }, d))) : h("input", { value: v || "" });

  async function render() {
    const me = await api("GET", "/me");
    DEPTS = ((await api("GET", "/config/lists")).department || []).map(x => x.label);
    const sec = await api("GET", "/admin/logins?limit=60");
    const failedOnly = h("input", { type: "checkbox", checked: !!render.failed, onChange: (e) => { render.failed = e.target.checked; render(); } });
    const events = render.failed ? sec.events.filter(e => !e.ok) : sec.events;
    const secCard = h("div", { class: "card", id: "security-card" }, h("h2", {}, t("security")), h("p", { class: "muted small" }, t("security_note")),
      sec.locked.length ? [h("h3", {}, t("locked_accounts")), table([t("full_name"), t("locked_until"), ""], sec.locked.map(x => [x.user, x.locked_until.slice(0, 16).replace("T", " "),
        h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { await api("POST", `/admin/users/${x.user_id}/unlock`); toast(t("saved")); await render(); }) }, t("unlock"))]))] : null,
      sec.must_change.length ? h("p", { class: "small" }, `${t("must_change_list")}: ${sec.must_change.map(x => x.user).join(", ")}`) : null,
      h("h3", {}, t("signin_history")), h("label", { class: "check" }, failedOnly, " ", t("failed_only")),
      table([t("time"), t("staff_id"), t("full_name"), t("result")], events.map(e => [e.at ? e.at.slice(0, 16).replace("T", " ") : "", e.staff_id, e.user || "—", e.ok ? badge(t("signin_ok"), "GREEN") : badge(t(`sr_${e.reason || "bad_password"}`), "RED")]), t("none")));
    const [users, rates, cfg] = await Promise.all([api("GET", "/users"), api("GET", "/admin/rates"), api("GET", "/admin/rules")]);
    const f = { jt: h("input"), dep: depInput(null), sid: h("input"), name: h("input"), pw: h("input", { type: "password", autocomplete: "new-password" }), role: h("select", {}, ROLES.map(r => h("option", { value: r }, r))), grade: h("input", { style: "width:90px" }),
      cap: h("input", { type: "number", value: "40", style: "width:80px" }), ccb: h("input", { type: "checkbox" }), lm: h("select", {}, h("option", { value: "" }, "—"), users.map(u => h("option", { value: u.id }, u.full_name))) };
    const uerr = h("div");
    const hols = await api("GET", "/calendar/holidays");
    const hd = h("input", { type: "date" }), hn = h("input", { placeholder: t("holiday_name") }), herr = h("div");
    const addH = h("button", { class: "btn", type: "button" }, t("add_holiday"));
    addH.addEventListener("click", guarded(addH, async () => {
      mount(herr);
      try { await api("POST", "/calendar/holidays", { day: hd.value, name: hn.value.trim() }); toast(t("saved")); await render(); } catch (e) { mount(herr, errorBox(e)); }
    }));
    const addU = h("button", { class: "btn", type: "button" }, t("create"));
    addU.addEventListener("click", guarded(addU, async () => {
      mount(uerr);
      try { await api("POST", "/users", { staff_id: f.sid.value.trim(), full_name: f.name.value.trim(), password: f.pw.value, job_title: f.jt.value.trim() || null, department: f.dep.value.trim() || null, role: f.role.value, rate_grade: f.grade.value.trim() || null, capacity_hours_week: Number(f.cap.value), is_ccb: f.ccb.checked, line_manager_id: f.lm.value ? Number(f.lm.value) : null }); toast(t("saved")); await render(); }
      catch (e) { mount(uerr, errorBox(e)); }
    }));
    const rg = h("input", { style: "width:90px" }), rv = h("input", { type: "number", min: "0", style: "width:100px" }), rc = h("input", { value: "SAR", maxlength: "3", style: "width:70px" }), rd = h("input", { type: "date", value: today() });
    const rerr = h("div");
    const addR = h("button", { class: "btn", type: "button" }, t("add"));
    addR.addEventListener("click", guarded(addR, async () => { mount(rerr); try { await api("POST", "/admin/rates", { grade: rg.value.trim(), hourly_rate: Number(rv.value), currency: rc.value.toUpperCase(), effective_from: rd.value }); toast(t("saved")); await render(); } catch (e) { mount(rerr, errorBox(e)); } }));

    const sevSel = (rule) => h("select", { value: cfg.severities[rule], onChange: guarded(null, async (ev) => { await api("PUT", `/admin/rules/${rule}`, { severity: ev.target.value }); toast(t("saved_ok")); }) }, ["BLOCK", "WARN", "FLAG"].map(s => h("option", { value: s }, s)));
    const setting = (key) => { const i = h("input", { type: "number", step: "any", value: cfg.params[key], style: "width:110px" }); i.addEventListener("change", guarded(i, async () => { await api("PUT", `/admin/settings/${key}`, { value: Number(i.value) }); toast(t("saved_ok")); })); return i; };

    const perm = await api("GET", "/admin/permissions");
    const csvBox = h("textarea", { rows: 5, placeholder: "staff_id,full_name,role,job_title,department,email,capacity_hours_week,password" }), cout = h("div");
    const impBtn = h("button", { class: "btn", type: "button" }, t("import_users"));
    impBtn.addEventListener("click", guarded(impBtn, async () => {
      mount(cout);
      try {
        const r = await api("POST", "/admin/users/import", { csv_text: csvBox.value });
        mount(cout, h("p", {}, `${t("created")}: ${r.created.length} · ${t("import_errors")}: ${r.errors.length}`),
          r.created.some(x => x.password) ? h("div", {}, h("p", { class: "muted small" }, t("import_pw_note")), table([t("staff_id"), t("password")], r.created.filter(x => x.password).map(x => [x.staff_id, h("code", {}, x.password)]))) : null,
          r.errors.length ? table([t("line"), t("staff_id"), t("imp_error")], r.errors.map(x => [x.line, x.staff_id || "", x.error])) : null);
        if (r.created.length) toast(t("saved"));
      } catch (e) { mount(cout, errorBox(e)); }
    }));
    const mail = await api("GET", "/admin/mail");
    const mf = { host: h("input", { value: mail.host || "" }), port: h("input", { type: "number", value: mail.port, style: "width:90px" }), user: h("input", { value: mail.username || "", autocomplete: "off" }),
      pw: h("input", { type: "password", autocomplete: "new-password", placeholder: mail.password_set ? t("pw_kept") : "" }), from: h("input", { value: mail.from_addr || "" }),
      tls: h("input", { type: "checkbox", checked: mail.starttls }), on: h("input", { type: "checkbox", checked: mail.enabled }), to: h("input", { type: "email", placeholder: "name@example.sa" }) };
    const mout = h("div");
    const mailCard = h("div", { class: "card", id: "mail-card" }, h("h2", {}, t("mail_server")), h("p", { class: "muted small" }, `${t("mail_note")} ${t("mail_source")}: ${t(`ms_${mail.source}`)}`),
      h("div", { class: "row" }, field(t("mail_host"), mf.host), field(t("mail_port"), mf.port), field(t("mail_user"), mf.user), field(t("password"), mf.pw), field(t("mail_from"), mf.from)),
      h("div", { class: "row" }, h("label", { class: "check" }, mf.tls, " STARTTLS"), h("label", { class: "check" }, mf.on, " ", t("mail_enabled")),
        h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(mout); try { await api("PUT", "/admin/mail", { host: mf.host.value.trim() || null, port: Number(mf.port.value), username: mf.user.value.trim() || null, password: mf.pw.value || null, from_addr: mf.from.value.trim() || null, starttls: mf.tls.checked, enabled: mf.on.checked }); toast(t("saved")); await render(); } catch (e) { mount(mout, errorBox(e)); } }) }, t("save"))),
      h("div", { class: "row", style: "margin-top:8px" }, field(t("mail_test_to"), mf.to), h("button", { class: "btn secondary", type: "button", onClick: guarded(null, async () => { mount(mout); try { const r = await api("POST", "/admin/mail/test", { to: mf.to.value.trim() }); mount(mout, r.ok ? h("p", { class: "ok" }, t("mail_test_ok")) : errorBox(new Error(r.error))); } catch (e) { mount(mout, errorBox(e)); } }) }, t("mail_test"))), mout);
    const incDocs = h("input", { type: "checkbox" });
    const backupCard = h("div", { class: "card", id: "backup-card" }, h("h2", {}, t("backup")), h("p", { class: "muted small" }, t("backup_note")),
      h("div", { class: "row" }, h("label", { class: "check" }, incDocs, " ", t("backup_docs")),
        h("button", { class: "btn", type: "button", onClick: guarded(null, async () => {
          const d = await api("GET", `/admin/export?include_documents=${incDocs.checked}`);
          const url = URL.createObjectURL(new Blob([JSON.stringify(d, null, 1)], { type: "application/json" }));
          const a = h("a", { href: url, download: `properm-backup-${d.exported_at.slice(0, 10)}.json` }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
        }) }, t("backup_download"))));
    mount(root, h("h1", {}, t("nav_admin")),
      h("div", { class: "card" }, h("h2", {}, t("users")), table([t("staff_id"), t("full_name"), t("role"), t("grade"), t("capacity"), t("is_ccb"), t("status"), ""], users.map(u => [u.staff_id, u.full_name, u.role, u.rate_grade || "—", num(u.capacity_hours_week), u.is_ccb ? "✓" : "", badge(u.active ? t("active") : t("inactive"), u.active ? "approved" : "critical"), h("span", { class: "row", style: "gap:6px;flex-wrap:nowrap" }, h("button", { class: "btn small", type: "button", onClick: () => editUser(u, users, me) }, t("edit")),
          u.active && u.id !== me.id ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, () => handover(u, users)) }, t("handover")) : null)]), t("none")),
        h("h2", { style: "margin-top:14px" }, t("new_user")),
        h("div", { class: "row" }, field(t("staff_id"), f.sid), field(t("full_name"), f.name), field(t("job_title"), f.jt), field(t("department"), f.dep), field(t("password"), f.pw), field(t("role"), f.role), field(t("grade"), f.grade), field(t("capacity"), f.cap), field(t("is_ccb"), f.ccb), field(t("line_manager"), f.lm), addU), uerr),
      secCard, mailCard, backupCard, restoreCard(), retentionCard(), jobsCard(),
      h("div", { class: "card", id: "import-card" }, h("h2", {}, t("bulk_import")), h("p", { class: "muted small" }, t("bulk_import_note")), csvBox, h("p", {}, impBtn), cout),
      h("div", { class: "card" }, h("h2", {}, t("rates")), table([t("grade"), t("hourly_rate"), t("currency"), t("effective_from"), ""], rates.map(r => [r.grade, num(r.hourly_rate, 2), r.currency, r.effective_from, r.future ? h("span", { class: "row", style: "gap:6px" }, badge(t("future_rate"), "AMBER"), h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/admin/rates/${r.id}`); await render(); }) }, t("remove"))) : ""]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("grade"), rg), field(t("hourly_rate"), rv), field(t("currency"), rc), field(t("effective_from"), rd), addR), rerr),
      h("div", { class: "card" }, h("h2", {}, t("holidays")), h("p", { class: "muted" }, t("work_week_note")),
        table([t("date"), t("name"), ""], hols.map(x => [x.day, x.name, h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/calendar/holidays/${x.id}`); await render(); }) }, t("remove"))]), t("none")),
        h("div", { class: "row", style: "margin-top:12px" }, field(t("date"), hd), field(t("name"), hn), addH), herr),
      h("div", { class: "card" }, h("h2", {}, t("perm_matrix")), h("p", { class: "muted small" }, t("perm_note")),
        table([t("capability"), t("roles")], perm.matrix.map(m => [m.capability, m.roles.map(r => badge(r, "GREY"))]))),
      h("div", { class: "card" }, h("h2", {}, t("rules")), table([t("rule"), t("severity")], Object.keys(cfg.severities).sort().map(r => [r, sevSel(r)]))),
      h("div", { class: "card" }, h("h2", {}, t("settings")), table([t("rule"), t("amount")], Object.keys(cfg.params).sort().map(k => [k, setting(k)]))));
  }
  await render();
}
