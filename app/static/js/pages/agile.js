// Project "Agile" tab (hybrid / adaptive projects): sprint board, burndown, velocity, backlog and sprints.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { COLORS, lineChart } from "../charts.js";
import { badge, errorBox, field, guarded, h, modal, mount, num, stat, toast } from "../ui.js";
import { registerCard } from "../register.js";

const COLS = ["ready", "in_progress", "review", "done"];
const so = (pref, list) => list.map(x => [x, t(`${pref}_${x}`)]);

export async function agile(body, p, { pid, me, dir, canManage, render }) {
  const [sum, items, sprints] = await Promise.all([api("GET", `/projects/${pid}/agile-summary`), api("GET", `/projects/${pid}/backlog`), api("GET", `/projects/${pid}/sprints`)]);
  const active = sprints.find(s => s.status === "active");
  const editable = canManage && p.state !== "archived";

  const stats = h("div", { class: "stats" }, stat(t("avg_velocity"), sum.average_velocity ?? "—"), stat(t("remaining_points"), num(sum.remaining_points, 1)),
    stat(t("sprints_to_go"), sum.sprints_to_go ?? "—"), stat(t("unestimated"), sum.unestimated));

  // board
  const move = (it, to) => guarded(null, async () => { await api("POST", `/projects/${pid}/backlog/${it.id}/move`, { status: to }); await render(); });
  const card = (it) => {
    const i = COLS.indexOf(it.status);
    return h("div", { class: "kcard" }, h("div", { class: "kt" }, it.title), h("div", { class: "muted small" }, `${t(`bk_${it.kind}`)} · ${it.points ?? "?"} ${t("pts")}${it.assignee ? ` · ${it.assignee}` : ""}`),
      h("div", { class: "row", style: "gap:4px;margin-top:6px" },
        i > 0 ? h("button", { class: "btn small secondary", type: "button", title: t(`bs_${COLS[i - 1]}`), "aria-label": t(`bs_${COLS[i - 1]}`), onClick: move(it, COLS[i - 1]) }, "←") : null,
        i < COLS.length - 1 ? h("button", { class: "btn small", type: "button", title: t(`bs_${COLS[i + 1]}`), "aria-label": t(`bs_${COLS[i + 1]}`), onClick: move(it, COLS[i + 1]) }, "→") : null));
  };
  const board = active ? h("div", { class: "card", id: "board-card" }, h("h2", {}, `${t("board")}: ${active.name}`), active.goal ? h("p", { class: "muted" }, active.goal) : null,
    h("div", { class: "kboard" }, COLS.map(c => { const col = items.filter(x => x.sprint_id === active.id && (x.status === c || (c === "ready" && x.status === "backlog"))); return h("div", { class: "kcol" }, h("h3", {}, `${t(`bs_${c}`)} (${col.length})`), col.map(card)); }))) : h("div", { class: "card" }, h("p", { class: "muted" }, t("no_active_sprint")));

  // burndown
  const b = sum.burndown;
  const burn = b ? h("div", { class: "card", id: "burndown-card" }, h("h2", {}, `${t("burndown")}: ${b.sprint}`),
    lineChart({ labels: b.points.map(x => x.date.slice(5)), yMin: 0, fmt: (v) => String(Math.round(v)), series: [{ name: t("ideal"), color: COLORS.grey, dash: "5 4", values: b.points.map(x => x.ideal) }, { name: t("remaining"), color: COLORS.navy, values: b.points.map(x => x.remaining) }] })) : null;
  const vel = sum.velocity.length ? h("div", { class: "card" }, h("h2", {}, t("velocity")),
    lineChart({ labels: sum.velocity.map(x => x.sprint), yMin: 0, fmt: (v) => String(Math.round(v)), series: [{ name: t("committed"), color: COLORS.grey, dash: "5 4", values: sum.velocity.map(x => x.committed) }, { name: t("done"), color: COLORS.navy, values: sum.velocity.map(x => x.done) }] })) : null;

  // sprints
  const closeSprint = (s) => {
    const next = h("select", {}, h("option", { value: "" }, t("back_to_backlog")), sprints.filter(x => x.status === "planned").map(x => h("option", { value: x.id }, x.name)));
    const rv = h("textarea", { rows: 2 }, s.review_note || ""), rt = h("textarea", { rows: 2 }, s.retro_note || ""), err = h("div");
    modal({ title: `${t("close_sprint")}: ${s.name}`, body: h("div", {}, err, field(t("unfinished_to"), next), field(t("sprint_review"), rv), field(t("sprint_retro"), rt)),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("close_sprint"), onClick: async (c) => {
        try { await api("POST", `/projects/${pid}/sprints/${s.id}/close`, { move_to: next.value ? Number(next.value) : null, review_note: rv.value, retro_note: rt.value }); c(); toast(t("saved")); await render(); }
        catch (e) { mount(err, errorBox(e)); } } }] });
  };
  const sprintCard = registerCard({ id: "sprints-card", title: t("sprints"), base: `/projects/${pid}/sprints`, rows: sprints, canManage: editable, render, dir,
    fields: [{ k: "name", label: t("name"), req: true }, { k: "goal", label: t("sprint_goal") }, { k: "start_date", label: t("planned_start"), type: "date", req: true }, { k: "end_date", label: t("planned_end"), type: "date", req: true },
      { k: "review_note", label: t("sprint_review"), type: "textarea" }, { k: "retro_note", label: t("sprint_retro"), type: "textarea" }],
    columns: [{ h: t("name"), f: r => r.name }, { h: t("sprint_goal"), f: r => r.goal || "" }, { h: t("planned_start"), f: r => r.start_date }, { h: t("planned_end"), f: r => r.end_date },
      { h: t("pts"), f: r => `${num(r.done_points, 1)} / ${num(r.points, 1)}` }, { h: t("status"), f: r => badge(t(`sp_${r.status}`), r.status === "active" ? "GREEN" : r.status === "closed" ? "GREY" : "AMBER") }],
    actions: (r) => !editable ? [] : [r.status === "planned" ? h("button", { class: "btn small", type: "button", onClick: guarded(null, async () => { await api("POST", `/projects/${pid}/sprints/${r.id}/start`); await render(); }) }, t("start")) : null,
      r.status === "active" ? h("button", { class: "btn small", type: "button", onClick: () => closeSprint(r) }, t("close_sprint")) : null] });

  // backlog
  const open = sprints.filter(s => s.status !== "closed");
  const backlog = registerCard({ id: "backlog-card", title: t("backlog"), note: t("backlog_note"), base: `/projects/${pid}/backlog`, rows: items, canManage: editable, render, dir,
    fields: [{ k: "title", label: t("title"), req: true }, { k: "kind", label: t("kind"), type: "select", options: so("bk", ["story", "bug", "task", "epic"]), def: "story" }, { k: "points", label: t("pts"), type: "number" }, { k: "rank", label: t("rank"), type: "number", def: 100 },
      { k: "status", label: t("status"), type: "select", options: so("bs", ["backlog", "ready", "in_progress", "review", "done"]), def: "backlog" },
      { k: "sprint_id", label: t("sprint"), type: "select", num: true, options: [["", "—"], ...open.map(s => [s.id, s.name])] }, { k: "assignee_id", label: t("assignee"), type: "user" },
      { k: "acceptance_criteria", label: t("acceptance_criteria"), type: "textarea" }, { k: "description", label: t("description"), type: "textarea" }],
    columns: [{ h: t("rank"), f: r => r.rank }, { h: t("title"), f: r => r.title }, { h: t("kind"), f: r => t(`bk_${r.kind}`) }, { h: t("pts"), f: r => r.points ?? "—" }, { h: t("sprint"), f: r => r.sprint || "—" }, { h: t("assignee"), f: r => r.assignee || "—" }, { h: t("status"), f: r => t(`bs_${r.status}`) }] });

  mount(body, stats, board, burn, vel, sprintCard, backlog);
}
