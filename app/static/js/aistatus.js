// One honest label for every place the product says "AI": is a language model really connected, or are these rules?
import { api } from "./api.js";
import { t } from "./i18n.js";
import { badge, h } from "./ui.js";

let cache = null;
export async function aiStatus() { if (!cache) cache = api("GET", "/ai/status").catch(() => ({ mode: "stub" })); return cache; }

/** Show a readable name; a raw OCI model OCID is shortened. */
const shortModel = (m) => (String(m).startsWith("ocid1.") ? `${String(m).split(".")[2]}…${String(m).slice(-6)}` : m);

/** A small badge: grey "Rule-based, no AI model connected" or green "AI model (Saudi-hosted)". Safe to call anywhere; fills itself in. */
export function aiLabel() {
  const box = h("span", { class: "ai-label", "data-ai": "" });
  aiStatus().then(s => {
    const live = s.mode === "live";
    box.dataset.ai = live ? "live" : "stub";
    box.replaceChildren(badge(live ? `${t("ai_label_live")} · ${shortModel(s.model)}` : t("ai_label_stub"), live ? "GREEN" : "GREY"));
    box.title = live ? (s.in_kingdom ? t("ai_in_kingdom") : t("ai_not_in_kingdom")) : t("ai_label_stub_tip");
  });
  return box;
}
