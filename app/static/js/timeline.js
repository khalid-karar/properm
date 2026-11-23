// Project timeline: grouped, collapsible rows, week / month / fit zoom, today line, milestones, dependency arrows.
// Built from HTML boxes positioned with logical (inline-start) offsets, so Arabic (right-to-left) mirrors by itself.
import { h } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const DAY = 864e5;
const D = (s) => new Date(String(s).slice(0, 10) + "T00:00:00").getTime();
const sv = (tag, a = {}, ...k) => { const n = document.createElementNS(NS, tag); for (const [x, v] of Object.entries(a)) if (v != null) n.setAttribute(x, v); n.append(...k.flat().filter(Boolean)); return n; };

/** rows: [{id,label,start,end,group,pct,color,critical}], links: [{from,to,bad}] (row ids), marks: [{label,date,done}] */
export function timeline({ rows, links = [], marks = [], labels }) {
  const L = Object.assign({ month: "Month", week: "Week", fit: "Fit", today: "Today", milestones: "Milestones", expand: "Expand all", collapse: "Collapse all" }, labels || {});
  if (!rows.length) return h("p", { class: "muted" }, "—");
  const rtl = document.documentElement.dir === "rtl";
  const phone = window.innerWidth < 600;
  const LW = phone ? 130 : 250, RH = phone ? 40 : 38, HEAD = 44;
  const groups = [];
  const gmap = new Map();
  rows.forEach(r => { const k = r.group || ""; if (!gmap.has(k)) { const g = { key: k, rows: [], open: true }; gmap.set(k, g); groups.push(g); } gmap.get(k).rows.push(r); });
  const all = [...rows.flatMap(r => [D(r.start), D(r.end)]), ...marks.map(m => D(m.date))];
  const now = new Date().setHours(0, 0, 0, 0);
  let lo = Math.min(...all), hi = Math.max(...all);
  if (now > lo - 30 * DAY && now < hi + 30 * DAY) { lo = Math.min(lo, now); hi = Math.max(hi, now); }
  lo -= 3 * DAY; hi += 3 * DAY;
  const days = Math.max(7, Math.round((hi - lo) / DAY));
  let zoom = "fit";
  const ppd = () => zoom === "week" ? 16 : zoom === "month" ? 5 : Math.max(1.4, Math.min(14, 640 / days));
  const box = h("div", { class: "tl", dir: rtl ? "rtl" : "ltr" });
  const draw = () => {
    const k = ppd(), TW = Math.ceil(days * k) + 20;
    const items = [];
    if (marks.length) items.push({ t: "ms" });
    groups.forEach(g => { if (g.key) items.push({ t: "g", g }); if (g.open || !g.key) g.rows.forEach(r => items.push({ t: "r", r })); });
    const H = HEAD + items.length * RH;
    const px = (ms) => Math.round(((ms - lo) / DAY) * k);
    const scroller = h("div", { class: "tl-scroll" });
    const inner = h("div", { class: "tl-inner", style: `width:${LW + TW}px;height:${H}px` });
    // header scale
    const head = h("div", { class: "tl-head", style: `height:${HEAD}px` }, h("div", { class: "tl-lab tl-corner", style: `width:${LW}px` }, ""));
    const scale = h("div", { class: "tl-scale", style: `inset-inline-start:${LW}px;width:${TW}px` });
    const d0 = new Date(lo); d0.setDate(1);
    for (let d = new Date(d0); d.getTime() <= hi; d.setMonth(d.getMonth() + 1)) {
      if (d.getTime() < lo) continue;
      scale.append(h("span", { class: "tl-m", style: `inset-inline-start:${px(d.getTime())}px` }, `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`));
    }
    if (zoom !== "fit") for (let d = new Date(lo); d.getTime() <= hi; d.setDate(d.getDate() + (zoom === "week" ? 7 : 14))) scale.append(h("span", { class: "tl-d", style: `inset-inline-start:${px(d.getTime())}px` }, String(d.getDate())));
    head.append(scale); inner.append(head);
    // vertical month lines + today
    const lines = h("div", { class: "tl-lines", style: `inset-inline-start:${LW}px;width:${TW}px;top:${HEAD}px;height:${H - HEAD}px` });
    for (let d = new Date(d0); d.getTime() <= hi; d.setMonth(d.getMonth() + 1)) if (d.getTime() >= lo) lines.append(h("i", { style: `inset-inline-start:${px(d.getTime())}px` }));
    if (now >= lo && now <= hi) lines.append(h("b", { class: "tl-today", style: `inset-inline-start:${px(now)}px` }, h("em", {}, L.today)));
    inner.append(lines);
    const yOf = new Map();
    items.forEach((it, i) => {
      const y = HEAD + i * RH;
      if (it.t === "ms") {
        const row = h("div", { class: "tl-row ms", style: `top:${y}px;height:${RH}px` }, h("div", { class: "tl-lab", style: `width:${LW}px` }, `◆ ${L.milestones}`));
        marks.forEach(m => row.append(h("span", { class: `tl-dia ${m.done ? "done" : ""}`, title: `${m.label} · ${m.date}`, style: `inset-inline-start:${LW + px(D(m.date)) - 7}px` }), h("span", { class: "tl-dl", title: m.label, style: `inset-inline-start:${LW + px(D(m.date)) + 12}px` }, m.label)));
        inner.append(row);
      } else if (it.t === "g") {
        const g = it.g, s = Math.min(...g.rows.map(r => D(r.start))), e = Math.max(...g.rows.map(r => D(r.end)));
        const pct = g.rows.reduce((a, r) => a + (r.pct || 0), 0) / g.rows.length;
        inner.append(h("div", { class: "tl-row grp", style: `top:${y}px;height:${RH}px` },
          h("button", { type: "button", class: "tl-lab tl-gtoggle", style: `width:${LW}px`, "aria-expanded": String(g.open), title: g.label || g.key, onClick: () => { g.open = !g.open; draw(); } }, `${g.open ? "▾" : "▸"} ${g.label || g.key} · ${g.rows.length}`),
          h("span", { class: "tl-gbar", title: `${g.label || g.key}: ${new Date(s).toISOString().slice(0, 10)} → ${new Date(e).toISOString().slice(0, 10)}`, style: `inset-inline-start:${LW + px(s)}px;width:${Math.max(6, px(e) - px(s))}px` }, h("span", { style: `width:${Math.round(pct)}%` }))));
      } else {
        const r = it.r; yOf.set(r.id, y);
        const w = Math.max(6, px(D(r.end)) - px(D(r.start)));
        inner.append(h("div", { class: "tl-row", style: `top:${y}px;height:${RH}px` },
          h("div", { class: "tl-lab", style: `width:${LW}px`, title: `${r.label} · ${r.start} → ${r.end}` }, h("span", {}, r.label)),
          h("span", { class: `tl-bar ${r.critical ? "crit" : ""}`, title: `${r.label}\n${r.start} → ${r.end}${r.pct != null ? `\n${Math.round(r.pct)}%` : ""}`, style: `inset-inline-start:${LW + px(D(r.start))}px;width:${w}px` }, h("span", { style: `width:${Math.round(r.pct || 0)}%` }))));
      }
    });
    // dependency arrows (only between visible rows)
    const svg = sv("svg", { class: "tl-dep", width: TW, height: H, style: `inset-inline-start:${LW}px`, "aria-hidden": "true" });
    const X = (ms) => { const v = px(ms); return rtl ? TW - v : v; };
    const byId = Object.fromEntries(rows.map(r => [r.id, r]));
    links.forEach(l => {
      const a = byId[l.from], b = byId[l.to]; if (!a || !b || !yOf.has(l.from) || !yOf.has(l.to)) return;
      const xa = X(D(a.end)), ya = yOf.get(l.from) + RH / 2, xb = X(D(b.start)), yb = yOf.get(l.to) + RH / 2, dx = rtl ? -24 : 24;
      svg.append(sv("path", { d: `M${xa} ${ya} C${xa + dx} ${ya}, ${xb - dx} ${yb}, ${xb} ${yb}`, fill: "none", stroke: l.bad ? "var(--red)" : "var(--muted)", "stroke-width": 1.5, "stroke-dasharray": l.bad ? "" : "4 3" }), sv("circle", { cx: xb, cy: yb, r: 3, fill: l.bad ? "var(--red)" : "var(--muted)" }));
    });
    inner.append(svg);
    scroller.append(inner);
    const btn = (id, label) => h("button", { type: "button", class: `btn small ${zoom === id ? "" : "secondary"}`, "data-zoom": id, "aria-pressed": String(zoom === id), onClick: () => { zoom = id; draw(); } }, label);
    const bulk = (open) => h("button", { type: "button", class: "btn small secondary", onClick: () => { groups.forEach(g => { g.open = open; }); draw(); } }, open ? L.expand : L.collapse);
    const top = h("div", { class: "row tl-bar-top" }, btn("fit", L.fit), btn("month", L.month), btn("week", L.week), groups.some(g => g.key) ? [bulk(true), bulk(false)] : null);
    box.replaceChildren(top, scroller);
    // keep today in view on first paint
    if (zoom !== "fit" && now >= lo && now <= hi) requestAnimationFrame(() => { scroller.scrollLeft = (rtl ? -1 : 1) * Math.max(0, px(now) - 120); });
  };
  draw();
  return box;
}
