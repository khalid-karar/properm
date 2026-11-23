import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, num, stat, table, toast } from "../ui.js";

export default async function (root, { me, arg }) {
  if (arg) return (await import("./program.js")).default(root, { me, gid: Number(arg) });
  const canEdit = ["PMO", "ADMIN"].includes(me.role);
  const isPg = me.role === "PROGRAM_MANAGER";
  const dir = await api("GET", "/directory");
  async function render() {
    const progs = await api("GET", "/programs");
    const allProjects = (canEdit || isPg) ? await api("GET", "/projects") : [];
    const dash = await Promise.all(progs.map(g => api("GET", `/programs/${g.id}/dashboard`).catch(() => null)));
    const roll = await Promise.all(progs.map(g => api("GET", `/programs/${g.id}/rollup`).catch(() => null)));
    const mineIds = new Set(progs.filter(g => g.manager_id === me.id).map(g => g.id));
    const manageable = (g) => canEdit || (isPg && mineIds.has(g.id));
    const addCard = (g) => {
      const free = allProjects.filter(p => p.program_id !== g.id);
      const sel = h("select", {}, free.map(p => h("option", { value: p.id }, `${p.number} · ${p.name}`)));
      const e2 = h("div");
      return h("div", { class: "row", style: "margin-top:12px" }, field(t("add_project_to_program"), sel),
        h("button", { class: "btn", type: "button", onClick: guarded(null, async () => { if (!sel.value) return; await api("PUT", `/projects/${sel.value}/program`, { program_id: g.id }); toast(t("saved")); await render(); }) }, t("add")), e2);
    };
    const code = h("input", { style: "width:100px" }), name = h("input"), mgr = h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id }, u.full_name)));
    const err = h("div"), btn = h("button", { class: "btn", type: "button" }, t("create"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try { await api("POST", "/programs", { code: code.value.trim(), name: name.value.trim(), manager_id: mgr.value ? Number(mgr.value) : null }); toast(t("saved")); await render(); }
      catch (e) { mount(err, errorBox(e)); }
    }));
    mount(root, h("h1", {}, t("programs")),
      isPg && !progs.some(g => mineIds.has(g.id)) ? h("p", { class: "muted" }, t("none")) : null,
      progs.slice().sort((a, b) => (mineIds.has(b.id) ? 1 : 0) - (mineIds.has(a.id) ? 1 : 0)).map((g) => { const i = progs.indexOf(g); const d = dash[i]; const ru = roll[i]; return h("div", { class: "card" }, h("h2", {}, `${g.code} · ${g.name} `, mineIds.has(g.id) ? badge(t("my_programs"), "gold") : null, " ", h("a", { class: "btn small secondary", href: `#/programs/${g.id}` }, t("open_roadmap"))),
        !d ? h("p", { class: "muted" }, t("none")) : [
          h("div", { class: "grid" }, stat("RED", d.rag_counts.RED), stat("AMBER", d.rag_counts.AMBER), stat("GREEN", d.rag_counts.GREEN),
            stat(t("avg_realization"), d.benefits.avg_realization_pct == null ? "—" : `${num(d.benefits.avg_realization_pct, 0)}%`),
            stat("CPI", num(d.evm.CPI, 2)), stat("SPI", num(d.evm.SPI, 2))),
          table([t("project"), t("state"), "RAG", "%", ""], d.projects.map(p => [h("a", { href: `#/projects/${p.project_id}` }, `${p.number} · ${p.name}`), t(p.state), badge(p.rag), `${num(p.progress_pct, 0)}%`, manageable(g) ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { await api("PUT", `/projects/${p.project_id}/program`, { program_id: null }); await render(); }) }, t("remove_from_program")) : ""]), t("none")),
          ru && ru.risks.length ? [h("h3", {}, t("program_risks")), table([t("project"), t("title"), t("score")], ru.risks.slice(0, 8).map(r => [r.project, r.title, badge(r.score, r.score >= 20 ? "critical" : "warning")]))] : null,
          ru && ru.benefits.length ? [h("h3", {}, t("program_benefits")), table([t("project"), t("metric"), t("target"), t("realization")], ru.benefits.map(b => [b.project, b.metric || b.title || "", num(b.target), b.realization_pct == null ? "—" : `${num(b.realization_pct, 0)}%`]))] : null,
          manageable(g) ? addCard(g) : null]); }),
      progs.length ? null : h("p", { class: "muted" }, t("none")),
      canEdit ? h("div", { class: "card" }, h("h2", {}, t("new_program")), h("div", { class: "row" }, field(t("code"), code), field(t("name"), name), field(t("manager"), mgr), btn), err) : null);
  }
  await render();
}
