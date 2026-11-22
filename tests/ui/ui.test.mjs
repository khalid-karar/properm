// End-to-end UI test against a freshly seeded demo server. Run with: bash tests/ui/run.sh
// Needs Playwright (npm i playwright) and Chrome. Override with PLAYWRIGHT_PATH and CHROME_PATH.
const { chromium } = await import(process.env.PLAYWRIGHT_PATH || "playwright");
const BASE = (process.env.BASE_URL || "http://localhost:8765") + "/ui/";
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", args: ["--no-sandbox"] });
const problems = [];
async function newPage(name) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  page.on("pageerror", e => problems.push(`[${name}] pageerror: ${e.message}`));
  page.on("console", m => { if (m.type() === "error" && !/40[0-9]|409|422/.test(m.text())) problems.push(`[${name}] console: ${m.text()}`); });
  page.on("response", r => { if (r.status() >= 500) problems.push(`[${name}] ${r.status()} ${r.url()}`); });
  return page;
}
async function login(page, id) {
  await page.goto(BASE); await page.fill('input[name=staff_id]', id); await page.fill('input[name=password]', "demo-pass-1");
  await page.click('button[type=submit]'); await page.waitForSelector("header.top");
}
const SHOTS = process.env.SHOTS_DIR;
const shot = (page, n) => (SHOTS ? page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true }) : null);
const step = async (label, fn) => { try { await fn(); console.log("ok  ", label); } catch (e) { problems.push(`${label}: ${e.message.split("\n")[0]}`); console.log("FAIL", label, e.message.split("\n")[0]); } };
const tab = (p, name) => p.click(`button[role=tab]:has-text("${name}")`);

let p = await newPage("pm");
await login(p, "pm1");
await step("progress saved for this week", async () => { await p.goto(BASE + "#/projects/1"); await tab(p, "Progress"); await p.waitForSelector('button:has-text("Save progress")'); await p.click('button:has-text("Save progress")'); await p.waitForSelector(".toast:has-text('Progress saved')"); });
await step("weekly report submitted", async () => {
  await tab(p, "Weekly reports"); await p.waitForSelector("textarea");
  const ta = p.locator("textarea"); await ta.nth(0).fill("Finished design"); await ta.nth(1).fill("Build"); await ta.nth(2).fill("Need vendor decision");
  await p.click('button:has-text("Submit report")'); await p.waitForSelector(".toast:has-text('Report submitted')"); await p.waitForSelector("text=Finished design"); await p.waitForSelector("text=Overall % complete"); await shot(p, "10-report");
});
await step("duplicate report shows error", async () => { await p.locator("textarea").nth(0).fill("x"); await p.locator("textarea").nth(1).fill("y"); await p.click('button:has-text("Submit report")'); await p.waitForSelector(".err:has-text('already submitted')"); });
await step("allocation set + grid", async () => {
  await tab(p, "Allocations"); await p.waitForSelector('button:has-text("Set allocation")');
  await p.getByLabel("Hours", { exact: true }).fill("45"); await p.click('button:has-text("Set allocation")'); await p.waitForSelector(".toast:has-text('Over-allocated')"); await p.waitForSelector("table td:has-text('45')"); await shot(p, "11-alloc");
});
await step("change requested", async () => {
  await tab(p, "Change control"); await p.waitForSelector('button:has-text("Request")');
  await p.getByLabel("Hours Δ").fill("10"); await p.getByLabel("Cost Δ").fill("5000"); await p.locator("textarea").fill("Add reporting module");
  await p.click('button:has-text("Request")'); await p.waitForSelector("td:has-text('Add reporting module')"); await p.waitForSelector("td .badge:has-text('requested')"); await shot(p, "12-change");
});
await step("impact required error", async () => { await p.locator("textarea").fill("no impact"); await p.click('button:has-text("Request")'); await p.waitForSelector(".err:has-text('Impact analysis')"); });
await step("CCB requester does not see own request to decide", async () => { await p.goto(BASE + "#/approvals"); await p.waitForSelector("text=awaiting decision"); if (await p.locator("td:has-text('Add reporting module')").count()) throw new Error("requester sees own request"); });

p = await newPage("pmo"); await login(p, "pmo1");
await step("PMO approves change from approvals", async () => {
  await p.goto(BASE + "#/approvals"); await p.waitForSelector("text=Change requests awaiting decision"); await p.waitForSelector("td:has-text('Add reporting module')");
  await shot(p, "13-pending"); await p.locator("tr:has-text('Add reporting module') button:has-text('Approve')").click(); await p.waitForSelector(".toast:has-text('Saved')");
  await p.waitForFunction(() => !document.body.innerText.includes("Add reporting module"));
});
await step("baseline version bumped & change shows approved", async () => { await p.goto(BASE + "#/projects/1"); await tab(p, "Change control"); await p.waitForSelector("td .badge:has-text('approved')"); });
await step("resource load page", async () => { await p.goto(BASE + "#/load"); await p.waitForSelector("td:has-text('45')"); await p.waitForSelector(".badge:has-text('Over-allocated')"); await shot(p, "14-load"); });

p = await newPage("login"); 
await step("login page shows build timeline", async () => { await p.goto(BASE); await p.waitForSelector(".timeline .light.done"); if (!(await p.locator(".timeline details.ms").count())) throw new Error("no milestones"); });

p = await newPage("admin"); await login(p, "admin");
await step("admin edits a user", async () => {
  await p.goto(BASE + "#/admin"); await p.waitForSelector("tr:has-text('s3') button:has-text('Edit')");
  await p.click("tr:has-text('s3') button:has-text('Edit')"); await p.waitForSelector(".modal");
  await p.locator(".modal label:has-text('Capacity') input").fill("32"); await p.locator(".modal label:has-text('CCB') input").check();
  await p.click(".modal button:has-text('Save')"); await p.waitForSelector(".toast:has-text('Saved')");
  await p.waitForSelector("tr:has-text('s3'):has-text('32')"); await p.waitForSelector("tr:has-text('s3'):has-text('✓')");
});
await step("admin deactivates a user; that user can no longer sign in", async () => {
  await p.click("tr:has-text('s2') button:has-text('Edit')"); await p.waitForSelector(".modal");
  await p.locator(".modal label:has-text('Active') input").uncheck(); await p.click(".modal button:has-text('Save')");
  await p.waitForSelector("tr:has-text('s2') .badge:has-text('Inactive')");
  const q = await newPage("s2"); await q.goto(BASE); await q.fill("input[name=staff_id]", "s2"); await q.fill("input[name=password]", "demo-pass-1"); await q.click("button[type=submit]");
  await q.waitForSelector(".err"); if (await q.locator("header.top").count()) throw new Error("inactive user got in");
});
await step("admin cannot deactivate self from the UI", async () => {
  await p.click("tr:has-text('admin') button:has-text('Edit')"); await p.waitForSelector(".modal");
  if (!(await p.locator(".modal label:has-text('Active') input").isDisabled())) throw new Error("self-deactivate enabled");
  await p.click(".modal button:has-text('Cancel')");
});


p = await newPage("staff"); await login(p, "s1");
await step("staff sees change tab w/o cost, no allocations tab", async () => {
  await p.goto(BASE + "#/projects/1").catch(() => {});
  const ok = await p.locator('button[role=tab]:has-text("Allocations")').count();
  if (ok) throw new Error("staff sees Allocations tab");
  await tab(p, "Change control"); await p.waitForSelector("td:has-text('Add reporting module')");
  if (await p.locator("th:has-text('Cost Δ')").count()) throw new Error("cost column visible to staff");
});
await step("staff has no load nav", async () => { if (await p.locator('nav a:has-text("Resource load")').count()) throw new Error("load nav visible"); });

p = await newPage("gov"); await login(p, "pmo1");
await step("programs page shows rollup", async () => { await p.goto(BASE + "#/programs"); await p.waitForSelector("h2:has-text('DX-2026')"); await p.waitForSelector("a:has-text('ALPHA-01')"); });
await step("benefits tab shows realisation", async () => { await p.goto(BASE + "#/projects/1"); await tab(p, "Benefits"); await p.waitForSelector("td:has-text('Faster month-end close')"); await p.waitForSelector("td:has-text('40%')"); });
await step("closure tab hidden until closing", async () => { if (await p.locator('button[role=tab]:has-text("Closure")').count()) throw new Error("closure tab visible too early"); });
p = await newPage("gov-admin"); await login(p, "admin");
await step("admin holiday section", async () => { await p.goto(BASE + "#/admin"); await p.waitForSelector("h2:has-text('Public holidays')"); await p.waitForSelector("td:has-text('Demo public holiday')"); });

p = await newPage("notif"); await login(p, "pm1");
await step("bell shows notifications and page lists them", async () => { await p.waitForSelector("#bell"); await p.goto(BASE + "#/notifications"); await p.waitForSelector("h1:has-text('Notifications')"); });
await step("csv export downloads with BOM", async () => {
  await p.goto(BASE + "#/alerts"); await p.waitForSelector("button:has-text('Export CSV')");
  const [dl] = await Promise.all([p.waitForEvent("download"), p.click("button:has-text('Export CSV')")]);
  const fs = await import("node:fs"); const txt = fs.readFileSync(await dl.path(), "utf8");
  if (!txt.startsWith("\ufeffid,project")) throw new Error("bad csv: " + txt.slice(0, 40));
});
await step("schedule a weekly project report", async () => {
  await p.goto(BASE + "#/notifications"); await p.waitForSelector("h2:has-text('Scheduled reports')");
  await p.selectOption("select >> nth=0", "project"); await p.click("button:has-text('Add')"); await p.waitForSelector("td:has-text('Project report')");
});

p = await newPage("ar"); await login(p, "pmo1");
await step("arabic tabs & load", async () => { await p.click('button:has-text("العربية")'); await p.goto(BASE + "#/projects/1"); await p.waitForSelector('button[role=tab]:has-text("التحكم في التغيير")'); await tab(p, "التحكم في التغيير"); await p.waitForSelector("td .badge:has-text('معتمد')"); await shot(p, "15-ar-change"); });

console.log(problems.length ? "PROBLEMS:\n" + problems.join("\n") : "ALL OK");
await browser.close();
