// Small dependency-free SVG charts (no external libraries or fonts: data stays in the Kingdom and works offline).
import { h } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  n.append(...kids.flat().filter(x => x != null));
  return n;
};
const txt = (s, attrs) => { const n = el("text", attrs); n.textContent = s; return n; };
export const COLORS = { navy: "var(--navy2)", gold: "var(--gold)", red: "var(--red)", green: "var(--green)", amber: "var(--amber)", grey: "var(--grey)" };

function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v)), f = v / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}
const compact = (v) => (Math.abs(v) >= 1e6 ? `${+(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `${+(v / 1e3).toFixed(1)}k` : String(+v.toFixed(2)));

/** series: [{name, color, dash?, values: (number|null)[]}], labels: string[] (same length). refLine: {index, label}. refY: {value,label} */
export function lineChart({ labels, series, height = 260, refLine, refY, yMin, yMax, fmt = compact }) {
  const W = 760, H = height, m = { l: 52, r: 16, t: 14, b: 30 };
  const all = series.flatMap(s => s.values).filter(v => v != null);
  if (!all.length) return h("p", { class: "muted" }, "—");
  const lo = yMin ?? Math.min(0, ...all), hi = yMax ?? niceMax(Math.max(...all, refY?.value ?? 0));
  const X = (i) => m.l + (labels.length < 2 ? 0 : (i * (W - m.l - m.r)) / (labels.length - 1));
  const Y = (v) => m.t + (1 - (v - lo) / (hi - lo || 1)) * (H - m.t - m.b);
  const g = el("g");
  for (let i = 0; i <= 4; i++) {
    const v = lo + ((hi - lo) * i) / 4, y = Y(v);
    g.append(el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "var(--line)", "stroke-width": 1 }), txt(fmt(v), { x: m.l - 6, y: y + 4, "text-anchor": "end", class: "ct" }));
  }
  const every = Math.max(1, Math.ceil(labels.length / 8));
  labels.forEach((l, i) => { if (i % every === 0 || i === labels.length - 1) g.append(txt(l.slice(5) || l, { x: X(i), y: H - 8, "text-anchor": "middle", class: "ct" })); });
  if (refLine) g.append(el("line", { x1: X(refLine.index), x2: X(refLine.index), y1: m.t, y2: H - m.b, stroke: "var(--grey)", "stroke-dasharray": "4 3" }), txt(refLine.label, { x: X(refLine.index) + 4, y: m.t + 10, class: "ct" }));
  if (refY) g.append(el("line", { x1: m.l, x2: W - m.r, y1: Y(refY.value), y2: Y(refY.value), stroke: "var(--gold)", "stroke-dasharray": "6 4" }), txt(refY.label, { x: W - m.r, y: Y(refY.value) - 4, "text-anchor": "end", class: "ct" }));
  for (const s of series) {
    let d = "";
    s.values.forEach((v, i) => { if (v == null) return; d += `${d && s.values[i - 1] != null ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; });
    g.append(el("path", { d, fill: "none", stroke: s.color, "stroke-width": 2.4, "stroke-linejoin": "round", "stroke-dasharray": s.dash || null }));
    const last = s.values.map((v, i) => [v, i]).filter(([v]) => v != null).pop();
    if (last) g.append(el("circle", { cx: X(last[1]), cy: Y(last[0]), r: 3.5, fill: s.color }));
  }
  const legend = h("div", { class: "legend" }, series.map(s => h("span", {}, h("i", { style: `background:${s.color}` }), s.name)));
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": series.map(s => s.name).join(", ") }, g);
  return h("div", {}, svg, legend);
}

/** rows: [{label, a (planned), b (actual)}] horizontal paired bars; actual over planned turns red. */
export function pairedBars({ rows, aName, bName }) {
  if (!rows.length) return h("p", { class: "muted" }, "—");
  const max = Math.max(...rows.flatMap(r => [r.a, r.b]), 1);
  return h("div", { class: "pbars" }, rows.map(r => h("div", { class: "pb" }, h("div", { class: "pbl" }, r.label),
    h("div", { class: "pbb" }, h("div", { class: "pbr", title: `${aName}: ${compact(r.a)}`, style: `width:${(r.a / max) * 100}%;background:var(--line-strong, #cbd2dc)` }),
      h("div", { class: "pbr", title: `${bName}: ${compact(r.b)}`, style: `width:${(r.b / max) * 100}%;background:${r.b > r.a ? "var(--red)" : "var(--navy2)"}` })),
    h("div", { class: "pbv" }, `${compact(r.b)} / ${compact(r.a)}`))),
    h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:var(--line-strong,#cbd2dc)" }), aName), h("span", {}, h("i", { style: "background:var(--navy2)" }), bName)));
}

/** 5x5 probability x impact grid. cells: {"p-i": [{title}]}. */
export function heatmap(cells, { pLabel, iLabel }) {
  const tint = (s) => (s >= 15 ? "var(--red-s)" : s >= 8 ? "var(--amber-s)" : "var(--green-s)");
  const edge = (s) => (s >= 15 ? "var(--red)" : s >= 8 ? "var(--amber)" : "var(--green)");
  const rowsEls = [];
  for (let p = 5; p >= 1; p--) {
    rowsEls.push(h("div", { class: "hm-axis" }, String(p)));
    for (let i = 1; i <= 5; i++) {
      const list = cells[`${p}-${i}`] || [];
      rowsEls.push(h("div", { class: "hm-cell", style: `background:${tint(p * i)};border-color:${list.length ? edge(p * i) : "transparent"}`, title: list.map(x => x.title).join("\n") }, list.length ? String(list.length) : ""));
    }
  }
  const foot = [h("div")]; for (let i = 1; i <= 5; i++) foot.push(h("div", { class: "hm-axis" }, String(i)));
  return h("div", {}, h("div", { class: "hm" }, rowsEls, foot), h("div", { class: "muted small", style: "margin-top:6px" }, `↑ ${pLabel}   → ${iLabel}`));
}

/** history: [{date, RED, AMBER, GREEN, GREY}] stacked bars. */
export function ragStack(history, height = 150) {
  if (!history.length) return h("p", { class: "muted" }, "—");
  const W = 760, H = height, m = { l: 28, r: 8, t: 8, b: 24 }, bw = Math.min(40, (W - m.l - m.r) / history.length - 6);
  const max = Math.max(...history.map(x => x.RED + x.AMBER + x.GREEN + x.GREY), 1);
  const g = el("g");
  history.forEach((x, i) => {
    const cx = m.l + ((i + 0.5) * (W - m.l - m.r)) / history.length;
    let y = H - m.b;
    for (const [k, c] of [["GREEN", "green"], ["AMBER", "amber"], ["RED", "red"], ["GREY", "grey"]]) {
      const hh = (x[k] / max) * (H - m.t - m.b);
      if (hh > 0) { y -= hh; g.append(el("rect", { x: cx - bw / 2, y, width: bw, height: hh, fill: COLORS[c], rx: 2 }, el("title", {}, `${x.date} ${k}: ${x[k]}`))); }
    }
    if (history.length <= 12 || i % Math.ceil(history.length / 8) === 0) g.append(txt(x.date.slice(5), { x: cx, y: H - 8, "text-anchor": "middle", class: "ct" }));
  });
  return el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img" }, g);
}

/** Timeline. rows: [{label, start:'YYYY-MM-DD', end, pct?}], marks: [{label, date, done?}]. */
export function gantt({ rows, marks = [], todayLabel = "", links = [] }) {
  const D = (s) => new Date(s + "T00:00:00").getTime();
  const all = [...rows.flatMap(r => [D(r.start), D(r.end), ...(r.marks || []).map(m => D(m.date))]), ...marks.map(m => D(m.date)), ...links.flatMap(l => [D(l.fromDate), D(l.toDate)])];
  if (!rows.length || !all.length) return h("p", { class: "muted" }, "—");
  const now = Date.now();
  let lo = Math.min(...all), hi = Math.max(...all);
  if (now > lo - 864e5 * 30 && now < hi + 864e5 * 30) { lo = Math.min(lo, now); hi = Math.max(hi, now); }
  const span = Math.max(hi - lo, 864e5), W = 860, L = 170, R = 20, RH = 26, T = 28, H = T + (rows.length + (marks.length ? 1 : 0)) * RH + 10;
  const x = (ms) => L + ((ms - lo) / span) * (W - L - R);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", style: "width:100%;height:auto" });
  const months = Math.max(1, Math.round(span / (864e5 * 30)));
  const stepM = Math.max(1, Math.ceil(months / 10));
  const d0 = new Date(lo); d0.setDate(1);
  let lastX = -1e9;
  for (let d = new Date(d0); d.getTime() <= hi; d.setMonth(d.getMonth() + stepM)) {
    if (d.getTime() < lo) continue;            // first partial month: no label at the clamped edge
    const gx = x(d.getTime());
    if (gx - lastX < 70) continue;
    lastX = gx;
    svg.append(el("line", { x1: gx, x2: gx, y1: T - 6, y2: H - 6, stroke: "var(--line)" }), txt(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, { x: gx + 3, y: T - 10, class: "ct", fill: "var(--muted)" }));
  }
  rows.forEach((r, i) => {
    const y = T + i * RH, x1 = x(D(r.start)), w = Math.max(4, x(D(r.end)) - x1);
    svg.append(txt(r.label.length > 24 ? r.label.slice(0, 23) + "…" : r.label, { x: 4, y: y + 16, class: "ct", fill: "var(--text)" }),
      el("rect", { x: x1, y: y + 4, width: w, height: 14, rx: 3, fill: "var(--grey)", opacity: 0.45 }),
      r.pct ? el("rect", { x: x1, y: y + 4, width: w * Math.min(1, r.pct / 100), height: 14, rx: 3, fill: "var(--navy2)" }) : null,
      ...(r.marks || []).map(m => { const cx = x(D(m.date)); return el("path", { d: `M${cx} ${y + 4} l7 7 l-7 7 l-7 -7 z`, fill: m.done ? "var(--green)" : "var(--gold)", stroke: "#fff" }, el("title", {}, `${m.label} ${m.date}`)); }));
  });
  links.forEach(l => {   // from the delivering row/date to the waiting row/date
    const xa = x(D(l.fromDate)), ya = T + l.fromRow * RH + 11, xb = x(D(l.toDate)), yb = T + l.toRow * RH + 11;
    svg.append(el("path", { d: `M${xa} ${ya} C${xa + 30} ${ya}, ${xb - 30} ${yb}, ${xb} ${yb}`, fill: "none", stroke: l.bad ? "var(--red)" : "var(--muted)", "stroke-width": 1.6, "stroke-dasharray": l.bad ? "" : "4 3" }, el("title", {}, l.label || "")),
      el("circle", { cx: xb, cy: yb, r: 3.5, fill: l.bad ? "var(--red)" : "var(--muted)" }));
  });
  const my = T + rows.length * RH;
  marks.forEach(m => {
    const cx = x(D(m.date));
    svg.append(el("path", { d: `M${cx} ${my + 4} l7 7 l-7 7 l-7 -7 z`, fill: m.done ? "var(--green)" : "var(--gold)" }, el("title", {}, `${m.label} ${m.date}`)));
  });
  if (marks.length) svg.append(txt("◆", { x: 4, y: my + 17, class: "ct", fill: "var(--gold)" }));
  if (now >= lo && now <= hi) svg.append(el("line", { x1: x(now), x2: x(now), y1: T - 6, y2: H - 6, stroke: "var(--red)", "stroke-dasharray": "4 3" }), txt(todayLabel, { x: x(now) + 3, y: H - 1, class: "ct", fill: "var(--red)" }));
  return h("div", { style: "overflow-x:auto" }, svg);
}
