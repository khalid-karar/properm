// Administrator restore and retention cards, and the two-factor card on My profile.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { errorBox, field, guarded, h, mount, num, table, toast } from "../ui.js";

export function restoreCard() {
  const file = h("input", { type: "file", accept: "application/json,.json", id: "restore-file" });
  const word = h("input", { id: "restore-word", placeholder: "RESTORE", style: "width:140px" });
  const out = h("div", { id: "restore-out" });
  let backup = null;
  const call = (mode) => api("POST", "/admin/restore", { confirm: word.value.trim(), mode, backup });
  const show = (r) => mount(out,
    h("p", { class: "muted small" }, `${t("restore_from")}: ${r.exported_at || "—"}`),
    table([t("table"), t("rows")], Object.entries(r.counts).filter(([, n]) => n).map(([k, n]) => [k, num(n, 0)])),
    r.users_needing_temporary_password?.length ? h("p", { class: "warn" }, `${t("restore_new_users")}: ${r.users_needing_temporary_password.join(", ")}`) : null,
    r.document_content_missing_in?.length ? h("p", { class: "warn" }, t("restore_no_docs")) : null,
    r.temporary_passwords ? h("div", { class: "warn", id: "restore-temp" }, h("strong", {}, t("restore_temp_note")), table([t("staff_id"), t("password")], Object.entries(r.temporary_passwords))) : null);
  return h("div", { class: "card", id: "restore-card" }, h("h2", {}, t("restore")), h("p", { class: "muted small" }, t("restore_note")),
    h("div", { class: "row" }, field(t("restore_file"), file),
      h("button", { class: "btn secondary", type: "button", onClick: guarded(null, async () => {
        mount(out);
        try { backup = JSON.parse(await file.files[0].text()); word.value = word.value || "RESTORE"; show(await call("dry_run")); toast(t("restore_checked")); }
        catch (e) { mount(out, errorBox(e)); }
      }) }, t("restore_check"))),
    h("div", { class: "row" }, field(t("restore_type"), word),
      h("button", { class: "btn danger", type: "button", onClick: guarded(null, async () => {
        if (!backup) return mount(out, errorBox(new Error(t("restore_pick_first"))));
        try { show(await call("replace")); toast(t("restore_done")); } catch (e) { mount(out, errorBox(e)); }
      }) }, t("restore_apply"))), out);
}

export function retentionCard() {
  const out = h("div", { id: "retention-out" });
  const ld = h("input", { type: "number", value: 365, min: 30, style: "width:90px" }), nd = h("input", { type: "number", value: 90, min: 7, style: "width:90px" });
  const load = async () => {
    try {
      const r = await api("GET", `/admin/retention?login_days=${ld.value}&notification_days=${nd.value}`);
      mount(out, h("p", {}, `${t("ret_logins")}: `, h("strong", {}, num(r.login_events, 0)), ` · ${t("ret_notes")}: `, h("strong", {}, num(r.read_notifications, 0))),
        table([t("project"), t("end")], r.projects_past_retention.map(p => [`${p.number} ${p.name}`, p.planned_end]), t("ret_no_projects")),
        h("p", { class: "muted small" }, r.note));
    } catch (e) { mount(out, errorBox(e)); }
  };
  load();
  return h("div", { class: "card", id: "retention-card" }, h("h2", {}, t("retention")), h("p", { class: "muted small" }, t("retention_note")),
    h("div", { class: "row" }, field(t("ret_login_days"), ld), field(t("ret_notif_days"), nd),
      h("button", { class: "btn secondary", type: "button", onClick: guarded(null, load) }, t("ret_preview")),
      h("button", { class: "btn", type: "button", onClick: guarded(null, async () => {
        try { const r = await api("POST", "/admin/retention/apply", { login_days: Number(ld.value), notification_days: Number(nd.value) }); toast(`${r.login_events_deleted + r.read_notifications_deleted} ${t("ret_removed")}`); await load(); }
        catch (e) { mount(out, errorBox(e)); }
      }) }, t("ret_apply"))), out);
}

export async function twoFactorCard() {
  const box = h("div", { class: "card", id: "twofa-card" });
  const render = async () => {
    const s = await api("GET", "/me/2fa");
    const err = h("div");
    if (s.enabled) {
      const pw = h("input", { type: "password", autocomplete: "current-password" }), code = h("input", { inputmode: "numeric", autocomplete: "one-time-code", style: "width:140px" });
      return mount(box, h("h2", {}, t("twofa")), h("p", { class: "ok" }, `${t("twofa_on")} · ${t("twofa_codes_left")}: ${s.backup_codes_left}`), err,
        h("div", { class: "row" }, field(t("password"), pw), field(t("twofa_code"), code),
          h("button", { class: "btn secondary", type: "button", onClick: guarded(null, async () => {
            try { await api("POST", "/me/2fa/disable", { password: pw.value, code: code.value }); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); }
          }) }, t("twofa_turn_off"))));
    }
    return mount(box, h("h2", {}, t("twofa")), h("p", { class: "muted small" }, t("twofa_note")), s.required_for_role ? h("p", { class: "warn" }, t("twofa_required")) : null, err,
      h("button", { class: "btn", type: "button", id: "twofa-start", onClick: guarded(null, async () => {
        const st = await api("POST", "/me/2fa/setup");
        const code = h("input", { id: "twofa-confirm", inputmode: "numeric", autocomplete: "one-time-code", style: "width:140px" });
        mount(box, h("h2", {}, t("twofa")), h("p", {}, t("twofa_scan")), h("p", {}, h("code", { id: "twofa-secret", style: "font-size:1.1em;letter-spacing:2px" }, st.secret)),
          h("p", { class: "muted small" }, st.uri), err,
          h("div", { class: "row" }, field(t("twofa_code"), code),
            h("button", { class: "btn", type: "button", onClick: guarded(null, async () => {
              try {
                const r = await api("POST", "/me/2fa/enable", { code: code.value });
                mount(box, h("h2", {}, t("twofa")), h("p", { class: "ok" }, t("twofa_on")), h("div", { class: "warn", id: "twofa-backup" }, h("strong", {}, t("twofa_backup_note")), h("p", { style: "font-family:monospace;font-size:1.1em" }, r.backup_codes.join("   "))));
              } catch (e) { mount(err, errorBox(e)); }
            }) }, t("twofa_enable"))));
      }) }, t("twofa_start")));
  };
  await render();
  return box;
}
