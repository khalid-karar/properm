// Skills & certifications: everyone keeps their own; PMs and the PMO search the directory and see development gaps.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, table, toast } from "../ui.js";

const LV = [1, 2, 3, 4];

export default async function (root, { me }) {
  const lead = ["PM", "PMO", "ADMIN", "PROGRAM_MANAGER"].includes(me.role), hr = ["PMO", "ADMIN"].includes(me.role);
  async function render() {
    const [mine, list] = await Promise.all([api("GET", "/me/skills"), api("GET", "/skills/list")]);
    const sk = list.length ? h("select", {}, list.map(x => h("option", { value: x }, x))) : h("input", { placeholder: t("skill_ph") });
    const lvl = h("select", {}, LV.map(n => h("option", { value: n, selected: n === 2 }, t(`lv_${n}`)))), tgt = h("select", {}, h("option", { value: "" }, "—"), LV.map(n => h("option", { value: n }, t(`lv_${n}`)))), yrs = h("input", { type: "number", min: "0", step: "0.5", style: "width:80px" });
    const err = h("div"), cerr = h("div");
    const cn = h("input"), ci = h("input"), ce = h("input", { type: "date" });
    const skillsCard = h("div", { class: "card", id: "my-skills" }, h("h2", {}, t("my_skills")), h("p", { class: "muted small" }, t("skills_note")),
      table([t("skill"), t("level"), t("target_level"), t("years"), ""], mine.skills.map(s => [s.skill, t(`lv_${s.level}`), s.target_level ? h("span", {}, t(`lv_${s.target_level}`), " ", s.gap ? badge(t("to_develop"), "AMBER") : "") : "—", s.years ?? "—",
        h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/me/skills/${s.id}`); await render(); }) }, t("remove"))]), t("none")),
      h("div", { class: "row", style: "margin-top:12px" }, field(t("skill"), sk), field(t("level"), lvl), field(t("target_level"), tgt), field(t("years"), yrs),
        h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(err); try { await api("POST", "/me/skills", { skill: sk.value.trim(), level: Number(lvl.value), target_level: tgt.value ? Number(tgt.value) : null, years: yrs.value ? Number(yrs.value) : null }); toast(t("saved")); await render(); } catch (e) { mount(err, errorBox(e)); } }) }, t("add"))), err);
    const certCard = h("div", { class: "card", id: "my-certs" }, h("h2", {}, t("certifications")),
      table([t("name"), t("issuer"), t("expires"), ""], mine.certs.map(c => [c.name, c.issuer || "—", c.expires_on ? h("span", { class: c.expired ? "neg" : "" }, c.expires_on, " ", c.expired ? badge(t("expired"), "RED") : c.expires_soon ? badge(t("expires_soon"), "AMBER") : "") : "—",
        h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("DELETE", `/me/certs/${c.id}`); await render(); }) }, t("remove"))]), t("none")),
      h("div", { class: "row", style: "margin-top:12px" }, field(t("name"), cn), field(t("issuer"), ci), field(t("expires"), ce),
        h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { mount(cerr); try { await api("POST", "/me/certs", { name: cn.value.trim(), issuer: ci.value.trim() || null, expires_on: ce.value || null }); toast(t("saved")); await render(); } catch (e) { mount(cerr, errorBox(e)); } }) }, t("add"))), cerr);

    let dirCard = null;
    if (lead) {
      const q = h("input", { placeholder: t("skill_search_ph"), id: "skill-q" }), body = h("div");
      const load = async () => {
        const rows = await api("GET", `/people/skills${q.value.trim() ? `?skill=${encodeURIComponent(q.value.trim())}` : ""}`);
        mount(body, table([t("name"), t("department"), t("skills"), t("certifications")], rows.map(p => [p.name, p.department || "—", p.skills.map(s => `${s.skill} (${t(`lv_${s.level}`)})`).join(", ") || "—", p.certs.map(c => c.name).join(", ") || "—"]), t("none")));
      };
      q.addEventListener("input", () => { clearTimeout(q._t); q._t = setTimeout(load, 250); });
      dirCard = h("div", { class: "card", id: "skills-dir" }, h("h2", {}, t("skills_directory")), h("div", { class: "row" }, field(t("search"), q)), body);
      await load();
    }
    let gapCard = null;
    if (hr) {
      const g = await api("GET", "/people/development-gaps");
      gapCard = h("div", { class: "card", id: "dev-gaps" }, h("h2", {}, t("development_gaps")),
        table([t("name"), t("skill"), t("level"), t("target_level")], g.skill_gaps.map(x => [x.user, x.skill, t(`lv_${x.level}`), t(`lv_${x.target_level}`)]), t("none")),
        h("h3", {}, t("certs_expiring")), table([t("name"), t("certifications"), t("expires")], g.certs_expiring.map(x => [x.user, x.name, h("span", { class: x.expired ? "neg" : "" }, x.expires_on)]), t("none")));
    }
    mount(root, h("h1", {}, t("nav_skills")), skillsCard, certCard, dirCard, gapCard);
  }
  await render();
}
