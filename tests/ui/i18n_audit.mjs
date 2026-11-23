// Fails when a text key used by the pages is missing in English or Arabic, or the two dictionaries differ.
import fs from "fs";
import path from "path";
import { fileURLToPath, pathToFileURL } from "url";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../app/static/js");
globalThis.localStorage = { getItem: () => null, setItem() {} };
const { dictionaries } = await import(pathToFileURL(path.join(ROOT, "i18n.js")).href);
const files = ["app.js", "assistant.js", ...fs.readdirSync(path.join(ROOT, "pages")).map(f => "pages/" + f)];
const used = new Set(), prefixes = new Set();
for (const f of files) {
  const s = fs.readFileSync(path.join(ROOT, f), "utf8");
  for (const m of s.matchAll(/\bt\("([a-z0-9_]+)"\)/g)) used.add(m[1]);
  for (const m of s.matchAll(/\bt\(`([a-z0-9_]+)\$\{/g)) prefixes.add(m[1]);                 // dynamic keys such as t(`ev_${x}`)
}
// Dynamic keys: every dictionary key that starts with a prefix used dynamically must exist in both languages.
const dyn = [];
for (const pre of prefixes) for (const l of ["en", "ar"]) for (const k of Object.keys(dictionaries[l])) if (k.startsWith(pre)) dyn.push([l, k]);
for (const k of ["acknowledge_a", "assign", "escalate", "dismiss", "resolve", "verify", "reject_verification", "tendering", "planning", "execution", "closing", "archived", "on_hold", "cancelled", "submitted", "approved", "rejected"]) used.add(k);
const miss = (l) => [...used].filter(k => !(k in dictionaries[l]));
const onlyEn = Object.keys(dictionaries.en).filter(k => !(k in dictionaries.ar)), onlyAr = Object.keys(dictionaries.ar).filter(k => !(k in dictionaries.en));
const emptyVals = ["en", "ar"].flatMap(l => Object.entries(dictionaries[l]).filter(([, v]) => !String(v).trim()).map(([k]) => `${l}:${k}`));
const dynMissing = dyn.filter(([l, k]) => !(k in dictionaries[l === "en" ? "ar" : "en"]));
console.log(`keys used: ${used.size} | dynamic prefixes: ${[...prefixes].join(",")} | missing en: ${miss("en").length} | missing ar: ${miss("ar").length} | en-only: ${onlyEn.length} | ar-only: ${onlyAr.length} | empty: ${emptyVals.length}`);
const bad = [...miss("en"), ...miss("ar"), ...onlyEn, ...onlyAr, ...emptyVals, ...dynMissing.map(x => x[1])];
if (bad.length) { console.error("PROBLEMS:", [...new Set(bad)].join(", ")); process.exit(1); }
