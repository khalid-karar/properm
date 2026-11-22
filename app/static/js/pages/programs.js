import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, errorBox, field, guarded, h, mount, num, stat, table, toast } from "../ui.js";

export default async function (root, { me }) {
  const canEdit = ["PMO", "ADMIN"].includes(me.role);
  const dir = await api("GET", "/directory");
  async function render() {
    const progs = await api("GET", "/programs");
    const dash = await Promise.all(progs.map(g => api("GET", `/programs/${g.id}/dashboard`).catch(() => null)));
    const code = h("input", { style: "width:100px" }), name = h("input"), mgr = h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id }, u.full_name)));
    const err = h("div"), btn = h("button", { class: "btn", type: "button" }, t("create"));
    btn.addEventListener("click", guarded(btn, async () => {
      mount(err);
      try { await api("POST", "/programs", { code: code.value.trim(), name: name.value.trim(), manager_id: mgr.value ? Number(mgr.value) : null }); toast(t("saved")); await render(); }
      catch (e) { mount(err, errorBox(e)); }
    }));
    mount(root, h("h1", {}, t("programs")),
      progs.map((g, i) => { const d = dash[i]; return h("div", { class: "card" }, h("h2", {}, `${g.code} · ${g.name}`),
        !d ? h("p", { class: "muted" }, t("none")) : [
          h("div", { class: "grid" }, stat("RED", d.rag_counts.RED), stat("AMBER", d.rag_counts.AMBER), stat("GREEN", d.rag_counts.GREEN),
            stat(t("avg_realization"), d.benefits.avg_realization_pct == null ? "—" : `${num(d.benefits.avg_realization_pct, 0)}%`),
            stat("CPI", num(d.evm.CPI, 2)), stat("SPI", num(d.evm.SPI, 2))),
          table([t("project"), t("state"), "RAG", "%"], d.projects.map(p => [h("a", { href: `#/projects/${p.project_id}` }, `${p.number} · ${p.name}`), t(p.state), badge(p.rag), `${num(p.progress_pct, 0)}%`]), t("none"))]); }),
      progs.length ? null : h("p", { class: "muted" }, t("none")),
      canEdit ? h("div", { class: "card" }, h("h2", {}, t("new_program")), h("div", { class: "row" }, field(t("code"), code), field(t("name"), name), field(t("manager"), mgr), btn), err) : null);
  }
  await render();
}
