// My profile: contact e-mail, delegate, password, notification choices.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { errorBox, field, guarded, h, mount, toast } from "../ui.js";

export default async function (root, { me }) {
  const [p, dir] = await Promise.all([api("GET", "/me/profile"), api("GET", "/directory")]);
  const email = h("input", { type: "email", value: p.email || "" });
  const dg = h("select", {}, h("option", { value: "" }, "—"), dir.filter(u => u.id !== p.id).map(u => h("option", { value: u.id, selected: u.id === p.delegate_id }, u.full_name)));
  const cur = h("input", { type: "password", autocomplete: "current-password" }), nw = h("input", { type: "password", autocomplete: "new-password", minlength: 8 });
  const perr = h("div");
  const emailOn = h("input", { type: "checkbox", checked: p.prefs.email_enabled });
  const kinds = p.kinds.map(k => ({ k, box: h("input", { type: "checkbox", checked: !p.prefs.muted_kinds.includes(k) }) }));
  mount(root, h("h1", {}, t("profile_title")),
    h("div", { class: "card" }, h("h2", {}, t("account")),
      h("p", {}, h("strong", {}, p.full_name), ` · ${p.staff_id} · ${p.role}`, p.job_title ? ` · ${p.job_title}` : "", p.department ? ` · ${p.department}` : ""),
      p.line_manager_name ? h("p", { class: "muted" }, `${t("line_manager_is")}: ${p.line_manager_name}`) : null,
      h("div", { class: "row" }, field(t("contact_email"), email), field(t("delegate"), dg)),
      h("p", { class: "muted small" }, t("delegate_note")),
      h("button", { class: "btn", type: "button", onClick: guarded(null, async () => {
        await api("PATCH", "/me/profile", { email: email.value.trim() || null, delegate_id: dg.value ? Number(dg.value) : null });
        toast(t("profile_saved"));
      }) }, t("save"))),
    h("div", { class: "card" }, h("h2", {}, t("notif_prefs")), h("p", { class: "muted small" }, t("notif_prefs_note")),
      kinds.map(({ k, box }) => h("label", { class: "check" }, box, " ", t(`ev_${k.replace(/\./g, "_")}`))),
      h("label", { class: "check" }, emailOn, " ", t("email_notif")),
      h("button", { class: "btn", type: "button", onClick: guarded(null, async () => {
        await api("PUT", "/me/prefs", { muted_kinds: kinds.filter(x => !x.box.checked).map(x => x.k), email_enabled: emailOn.checked });
        toast(t("profile_saved"));
      }) }, t("save"))),
    h("div", { class: "card" }, h("h2", {}, t("change_password")), perr,
      h("div", { class: "row" }, field(t("cur_password"), cur), field(t("new_password2"), nw)),
      h("button", { class: "btn", type: "button", onClick: async () => {
        perr.replaceChildren();
        try { await api("POST", "/me/password", { current_password: cur.value, new_password: nw.value }); cur.value = nw.value = ""; toast(t("password_changed")); }
        catch (e) { perr.append(errorBox(e)); }
      } }, t("change_password"))));
}
