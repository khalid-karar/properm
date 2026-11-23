// Generic register card: table + add/edit dialog + delete, driven by a field list.
import { api } from "./api.js";
import { t } from "./i18n.js";
import { errorBox, field, guarded, h, modal, mount, table, toast } from "./ui.js";

// field: { k, label, type: text|textarea|number|date|select|user, options: [[value,label]], req, def }
export function formFor(fields, init = {}, dir = []) {
  const inputs = {};
  const nodes = fields.map(f => {
    let el;
    const v = init[f.k] ?? f.def ?? "";
    if (f.type === "textarea") el = h("textarea", { rows: 3 }, v);
    else if (f.type === "select") el = h("select", {}, f.options.map(([val, lab]) => h("option", { value: val, selected: String(v) === String(val) }, lab)));
    else if (f.type === "user") el = h("select", {}, h("option", { value: "" }, "—"), dir.map(u => h("option", { value: u.id, selected: Number(v) === u.id }, u.full_name)));
    else el = h("input", { type: f.type === "number" ? "number" : f.type === "date" ? "date" : "text", step: f.type === "number" ? "any" : undefined, value: v ?? "" });
    inputs[f.k] = el;
    return field(f.label + (f.req ? " *" : ""), el);
  });
  const read = () => {
    const out = {};
    for (const f of fields) {
      const raw = inputs[f.k].value;
      if (f.type === "number" || f.type === "user") out[f.k] = raw === "" ? null : Number(raw);
      else if (f.type === "select" && f.num) out[f.k] = raw === "" ? null : Number(raw);
      else out[f.k] = raw.trim() === "" ? null : raw.trim();
    }
    return out;
  };
  return { nodes, read, inputs };
}

export function registerCard({ id, title, note, base, rows, fields, columns, canManage, render, dir = [], actions, empty, remove = true, head }) {
  const open = (row) => {
    const f = formFor(fields, row || {}, dir), err = h("div");
    modal({ title: row ? t("edit") : t("add"), body: h("div", {}, err, ...f.nodes),
      actions: [{ label: t("cancel"), class: "secondary", onClick: (c) => c() }, { label: t("save"), onClick: async (c) => {
        try { await api(row ? "PATCH" : "POST", row ? `${base}/${row.id}` : base, f.read()); c(); toast(t("saved")); await render(); }
        catch (e) { mount(err, errorBox(e)); } } }] });
  };
  const cols = columns.map(c => c.h);
  const body = rows.map(r => [...columns.map(c => c.f(r)),
    canManage || actions ? h("span", { class: "row", style: "gap:6px" }, ...(actions ? actions(r) : []),
      canManage ? h("button", { class: "btn small secondary", type: "button", onClick: () => open(r) }, t("edit")) : null,
      canManage && remove ? h("button", { class: "btn small secondary", type: "button", onClick: guarded(null, async () => { if (!confirm(t("confirm_delete"))) return; await api("DELETE", `${base}/${r.id}`); await render(); }) }, t("remove")) : null) : ""]);
  return h("div", { class: "card", id }, h("h2", {}, title), note ? h("p", { class: "muted small" }, note) : null, head || null,
    table([...cols, ""], body, empty || t("none")),
    canManage ? h("p", {}, h("button", { class: "btn", type: "button", onClick: () => open(null) }, t("add"))) : null);
}

// Checkbox group for strategic objectives. avail: [{id, code, name}], selected: [id]
export function objectivePicker(avail, selected = [], disabled = false) {
  const boxes = avail.map(o => ({ o, el: h("input", { type: "checkbox", checked: selected.includes(o.id), disabled, "aria-label": `${o.code} ${o.name}` }) }));
  const node = h("div", { class: "checks" }, boxes.length ? boxes.map(({ o, el }) => h("label", { class: "check" }, el, ` ${o.code} · ${o.name}`)) : h("p", { class: "muted small" }, t("none")));
  return { node, ids: () => boxes.filter(b => b.el.checked).map(b => b.o.id) };
}
