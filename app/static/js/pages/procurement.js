// Portfolio procurement view: contracts across projects, expiries, vendor performance.
import { api } from "../api.js";
import { t } from "../i18n.js";
import { badge, h, mount, num, table } from "../ui.js";

export default async function (root) {
  const ov = await api("GET", "/procurement/overview");
  mount(root, h("h1", {}, t("nav_procurement")),
    h("div", { class: "stats" }, h("div", { class: "stat" }, h("div", { class: "v" }, num(ov.total_value, 0)), h("div", { class: "l" }, t("contract_value"))), h("div", { class: "stat" }, h("div", { class: "v" }, num(ov.total_invoiced, 0)), h("div", { class: "l" }, t("invoiced"))),
      h("div", { class: `stat ${ov.expiring_soon.length ? "amber" : "green"}` }, h("div", { class: "v" }, ov.expiring_soon.length), h("div", { class: "l" }, t("expiring_60")))),
    h("div", { class: "card", id: "po-contracts" }, h("h2", {}, t("contracts")),
      table([t("project"), t("number"), t("vendor"), t("contract_value"), t("invoiced"), t("ends"), t("status")],
        ov.contracts.map(c => [h("a", { href: `#/projects/${c.project_id}` }, c.project), c.number, c.vendor, `${num(c.value, 0)} ${c.currency}`, num(c.invoiced, 0),
          c.end_date ? h("span", { class: c.expires_in != null && c.expires_in <= 60 ? "neg" : "" }, `${c.end_date}${c.expires_in != null ? ` (${c.expires_in} ${t("days")})` : ""}`) : "—",
          h("span", {}, badge(t(`ct_${c.status}`), c.status === "active" ? "GREEN" : "GREY"), c.overdue_payments ? badge(`${c.overdue_payments} ${t("overdue")}`, "RED") : null)]), t("none"))),
    h("div", { class: "card" }, h("h2", {}, t("vendor_performance")), table([t("vendor"), t("reviews"), t("average")], ov.vendors.map(v => [v.vendor, v.reviews, v.rating >= 4 ? badge(String(v.rating), "GREEN") : v.rating >= 3 ? badge(String(v.rating), "AMBER") : badge(String(v.rating), "RED")]), t("none"))));
}
