// Project "Compliance" tab: requirements applied to this project with status and evidence.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, guarded, h, mount, toast } from "../ui.js";
import { registerCard } from "../register.js";

const COL = { not_started: "GREY", in_progress: "AMBER", compliant: "GREEN", exception: "RED", n_a: "GREY" };

export async function compliance(body, p, { pid, dir, canManage, render }) {
  const [rows, lib] = await Promise.all([api("GET", `/projects/${pid}/compliance`), api("GET", "/compliance-library").catch(() => [])]);
  const editable = canManage && p.state !== "archived";
  const frameworks = [...new Set(lib.filter(x => x.active).map(x => x.framework))];
  const fsel = h("select", {}, frameworks.map(f => h("option", { value: f }, f)));
  const applied = new Set(rows.map(r => r.requirement_id));
  const done = rows.filter(r => r.status === "compliant").length, app_ = rows.filter(r => r.status !== "n_a").length;
  const card = registerCard({ id: "pcompliance-card", title: t("compliance"), note: t("pcompliance_note"), base: `/projects/${pid}/compliance`, rows, canManage: editable, render, dir,
    head: h("div", {}, rows.length ? h("p", {}, badge(`${done}/${app_}`, done === app_ ? "GREEN" : "AMBER"), " ", t("compliant_of")) : null,
      editable && frameworks.length ? h("p", { class: "row" }, fsel, h("button", { class: "btn secondary small", type: "button", onClick: guarded(null, async () => { const r = await api("POST", `/projects/${pid}/compliance/apply-framework`, { framework: fsel.value }); toast(`${r.added} ${t("added")}`); await render(); }) }, t("apply_framework"))) : null),
    fields: [{ k: "requirement_id", label: t("requirement"), type: "select", num: true, req: true, options: lib.filter(x => x.active || applied.has(x.id)).map(x => [x.id, `${x.framework} · ${x.code} · ${x.title}`]) },
      { k: "status", label: t("status"), type: "select", options: ["not_started", "in_progress", "compliant", "exception", "n_a"].map(x => [x, t(`cs_${x}`)]), def: "not_started" },
      { k: "owner_id", label: t("owner"), type: "user" }, { k: "due_date", label: t("due_date"), type: "date" }, { k: "evidence", label: t("evidence"), type: "textarea" }],
    columns: [{ h: t("framework"), f: r => r.framework }, { h: t("code"), f: r => r.code }, { h: t("title"), f: r => r.title }, { h: t("owner"), f: r => r.owner || "—" },
      { h: t("due_date"), f: r => h("span", { class: r.overdue ? "neg" : "" }, r.due_date || "—") }, { h: t("evidence"), f: r => r.evidence || "—" }, { h: t("status"), f: r => badge(t(`cs_${r.status}`), COL[r.status]) }] });
  mount(body, card);
}
