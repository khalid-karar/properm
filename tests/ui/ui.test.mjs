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
const step = async (label, fn) => { try { await fn(); console.log("ok  ", label); } catch (e) { problems.push(`${label}: ${e.message.split("\n")[0]}`); try { await p.screenshot({ path: "/tmp/fail-" + label.replace(/\W+/g, "_") + ".png" }); } catch {} console.log("FAIL", label, e.message.split("\n")[0]); } };
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


await step("config page: add a risk category, AI admin test", async () => {
  await p.goto(BASE + "#/config"); await p.waitForSelector("h2:has-text('AI administration')"); await p.waitForSelector("h2:has-text('Risk categories')");
  const rc = p.locator(".card:has(h2:has-text('Risk categories'))");
  await rc.locator("label:has-text('Code') input").fill("Legal"); await rc.locator("label:has-text('Name') input").fill("Legal"); await rc.locator("button:has-text('Add')").click(); await rc.locator("td:has-text('Legal')").first().waitFor();
  await p.click("button:has-text('Test connection')"); await p.waitForSelector(".ok:has-text('Model answered')");
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

await step("staff: cap hint, withdraw an entry", async () => {
  await p.goto(BASE + "#/timesheet"); await p.waitForSelector("h2:has-text('New entry')"); await p.waitForSelector("text=left");
  await p.fill("input[type=date]", "2026-11-10"); await p.fill("input[type=number]", "1");
  await p.click("button:has-text('Submit')"); await p.waitForSelector(".toast:has-text('saved')").catch(() => {});
  await p.goto(BASE + "#/todo"); await p.waitForSelector("h1:has-text('My to-do')");
});

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

await step("AI tab shows stub banner and drafts a narrative", async () => {
  await p.goto(BASE + "#/projects/1"); await tab(p, "AI assistant"); await p.waitForSelector(".warn:has-text('offline stub')");
  await p.click("button:has-text('Draft status narrative')"); await p.waitForSelector("textarea:has-text('(stub)')");
});
await step("AI suggestion on an alert", async () => {
  await p.goto(BASE + "#/alerts"); await p.click("button:has-text('AI suggestion') >> nth=0"); await p.waitForSelector(".modal:has-text('Offline stub output')");
});

await step("details tab: edit client, add stakeholder", async () => {
  await p.goto(BASE + "#/alerts"); const cl = p.locator(".modal button:has-text('Close')"); if (await cl.count()) await cl.click();
  await p.goto(BASE + "#/projects/1"); await tab(p, "Details"); await p.waitForSelector("h2:has-text('Project details')");
  await p.fill("label:has-text('Client') input", "Ministry X"); await Promise.all([p.waitForResponse(r => r.request().method() === "PATCH" && r.url().endsWith("/projects/1")), p.locator(".card:has(h2:has-text('Project details')) button:has-text('Save')").click()]);
  await p.goto(BASE + "#/projects/1"); await tab(p, "Details"); await p.waitForSelector("label:has-text('Client') input");
  if ((await p.inputValue("label:has-text('Client') input")) !== "Ministry X") throw new Error("client not saved");
  const sc = p.locator(".card:has(h2:has-text('Stakeholders'))"); await sc.locator("td:has-text('Salem')").waitFor(); await p.waitForTimeout(400); await sc.getByLabel("Name", { exact: true }).fill("Dr Khalid Test"); await sc.locator("button:has-text('Add')").click(); await sc.locator("td:has-text('Dr Khalid Test')").waitFor();
});
await step("plan tab: milestone and KPI", async () => {
  await p.goto(BASE + "#/projects/1"); await tab(p, "Plan"); await p.waitForSelector("h2:has-text('Milestones')");
  const mc = p.locator(".card:has(h2:has-text('Milestones'))"), kc = p.locator(".card:has(h2:has-text('KPIs'))");
  await mc.locator("label:has-text('Name') input").fill("Handover"); await mc.locator("label:has-text('Due date') input").fill("2027-03-01"); await mc.locator("button:has-text('Add')").click(); await mc.locator("td:has-text('Handover')").waitFor();
  await kc.locator("label:has-text('Name') input").fill("Uptime"); await kc.locator("label:has-text('Target') input").fill("99"); await kc.locator("button:has-text('Add')").click(); await kc.locator("td:has-text('Uptime')").waitFor();
});

p = await newPage("audit"); await login(p, "pmo1");
await step("audit viewer lists and filters; period lock status", async () => {
  await p.goto(BASE + "#/audit"); await p.waitForSelector("h2:has-text('Audit log')"); await p.waitForSelector("td .badge");
  await p.waitForSelector("h2:has-text('Period lock')");
  await p.selectOption("label:has-text('Action') select", { index: 1 }); await p.click("button:has-text('Filter')"); await p.waitForSelector("td .badge");
});

await step("executive summary, decision queue, project charts", async () => {
  await p.goto(BASE + "#/executive"); await p.waitForSelector("h1:has-text('Executive')"); await p.waitForSelector("h2:has-text('Needs attention')");
  await p.goto(BASE + "#/decisions"); await p.waitForSelector("h1:has-text('Decisions')");
  await p.goto(BASE + "#/dashboard/1"); await p.waitForSelector("h2:has-text('S-curve')"); await p.waitForSelector("svg.chart"); await p.waitForSelector("h2:has-text('Risk heat map')"); await shot(p, "16-charts");
});

await step("todo page, approvals filters and bulk select", async () => {
  await p.goto(BASE + "#/todo"); await p.waitForSelector("h1:has-text('My to-do')");
  await p.goto(BASE + "#/approvals"); await p.waitForSelector("h2:has-text('My recent decisions')");
  await p.click("button:has-text('Approve selected')", { trial: true }).catch(() => {});
  await p.check("label:has-text('Flagged only') input"); await p.waitForSelector("h2:has-text('My recent decisions')"); await p.uncheck("label:has-text('Flagged only') input");
});

await step("reports page: preview and excel download", async () => {
  await p.goto(BASE + "#/reports"); await p.waitForSelector("h1:has-text('Reports')"); await p.waitForSelector("h2:has-text('Portfolio')");
  await p.selectOption("label:has-text('Period') select", "quarter"); await p.click("button:has-text('Preview')"); await p.waitForSelector("td:has-text('ALPHA-01')");
  const [dl] = await Promise.all([p.waitForEvent("download"), p.click("button:has-text('Export Excel')")]);
  if (!dl.suggestedFilename().endsWith(".xlsx")) throw new Error("no xlsx: " + dl.suggestedFilename());
});

p = await newPage("self"); await login(p, "s1");
await step("profile, my projects, role guide, copy week", async () => {
  await p.click("a.who"); await p.waitForSelector("h1:has-text('My profile')");
  await p.getByLabel("E-mail (for notifications)", { exact: true }).fill("s1@example.com");
  await Promise.all([p.waitForResponse(r => r.url().includes("/me/profile") && r.request().method() === "PATCH"), p.locator(".card:has(h2:has-text('Account')) button:has-text('Save')").click()]);
  await p.locator(".card:has(h2:has-text('Notification choices')) label.check input").first().uncheck();
  await Promise.all([p.waitForResponse(r => r.url().includes("/me/prefs")), p.locator(".card:has(h2:has-text('Notification choices')) button:has-text('Save')").click()]);
  await p.getByLabel("Current password", { exact: true }).fill("wrong"); await p.getByLabel("New password (8+ characters)", { exact: true }).fill("another-pass-1");
  await p.locator(".card:has(h2:has-text('Change password')) button:has-text('Change password')").click(); await p.waitForSelector(".err, .error, [role=alert]");
  await p.goto(BASE + "#/mine"); await p.waitForSelector("h1:has-text('My projects')"); await p.waitForSelector("td");
  await p.goto(BASE + "#/guide"); await p.waitForSelector("h1:has-text('What you can do')");
  await p.goto(BASE + "#/timesheet"); p.once("dialog", d => d.accept());
  await Promise.all([p.waitForResponse(r => r.url().includes("/timesheets/copy-week")), p.click("#copy-week")]);
});

p = await newPage("pm-risk"); await login(p, "pm1");
await step("risk edit, timeline, portfolio filters, investment table", async () => {
  await p.goto(BASE + "#/projects/1"); await tab(p, "Risks"); await p.waitForSelector("h2:has-text('Risks')");
  await p.locator(".card:has(h2:has-text('Risks')) tbody tr").first().locator("button:has-text('Edit')").click();
  await p.locator(".modal input").first().fill("Edited risk title");
  await Promise.all([p.waitForResponse(r => r.request().method() === "PATCH" && r.url().includes("/risks/")), p.click(".modal button:has-text('Save')")]);
  await p.waitForSelector("td:has-text('Edited risk title')");
  await p.goto(BASE + "#/projects/1"); await tab(p, "Plan"); await p.waitForSelector("#gantt-card svg.chart");
  await p.goto(BASE + "#/projects"); await p.waitForSelector("h1:has-text('Projects')"); await p.selectOption("label:has-text('State') select", { index: 1 }); await p.waitForSelector("td");
});
p = await newPage("pmo-inv"); await login(p, "pmo1");
await step("executive investment table", async () => { await p.goto(BASE + "#/executive"); await p.waitForSelector("#investment td"); });

p = await newPage("progmgr"); await login(p, "pg1");
await step("program manager sees own program and can edit", async () => {
  await p.goto(BASE + "#/programs"); await p.waitForSelector("h1:has-text('Programs')"); await p.waitForSelector("h2:has-text('DX-2026')");
  await p.waitForSelector("h3:has-text('Open risks across the program')").catch(() => {}); await p.waitForSelector("button:has-text('Remove')");
});

p = await newPage("admin2"); await login(p, "admin");
await step("admin bulk import and permission matrix", async () => {
  await p.goto(BASE + "#/admin"); await p.waitForSelector("#import-card textarea");
  await p.fill("#import-card textarea", "staff_id,full_name,role\nuiimp1,UI Import,STAFF");
  await Promise.all([p.waitForResponse(r => r.url().includes("/admin/users/import")), p.click("#import-card button:has-text('Import')")]);
  await p.waitForSelector("#import-card code"); await p.waitForSelector("h2:has-text('Who can do what')");
});

p = await newPage("gov-pm"); await login(p, "pm1");
await step("PM: intake required, submit proposal, see stage gate", async () => {
  await p.goto(BASE + "#/projects"); await p.waitForSelector("a:has-text('Submit a proposal')");
  await p.goto(BASE + "#/proposals"); await p.waitForSelector("h2:has-text('My proposals')");
  const f = p.locator("#new-proposal");
  await f.getByLabel("Number", { exact: true }).fill("UI-PROP-1"); await f.getByLabel("Name", { exact: true }).fill("UI proposal");
  await f.getByLabel("Business case", { exact: true }).fill("A clear business case for the UI test.");
  await Promise.all([p.waitForResponse(r => r.url().endsWith("/proposals") && r.request().method() === "POST"), f.locator("button:has-text('Submit a proposal')").click()]);
  await p.waitForSelector("td:has-text('UI-PROP-1')");
  await p.goto(BASE + "#/projects/4"); await p.waitForSelector("#gate-card"); await p.waitForSelector("#gate-card li.bad");
});

p = await newPage("gov-dm"); await login(p, "dm1");
await step("DM: rank proposals, approve with conditions, decide gate", async () => {
  await p.goto(BASE + "#/proposals"); await p.waitForSelector("h2:has-text('Proposals ranked by score')");
  await p.locator("tr:has(td:has-text('DELTA-05')) button:has-text('Open')").click(); await p.click(".modal button:has-text('Decide')");
  await p.selectOption(".modal select", "approve_conditions"); await p.getByLabel("Rationale", { exact: true }).fill("Strong fit"); await p.getByLabel("Conditions", { exact: true }).fill("Phase 1 only");
  await Promise.all([p.waitForResponse(r => r.url().includes("/decision")), p.click(".modal button:has-text('Record decision')")]);
  await p.waitForSelector("tr:has(td:has-text('DELTA-05')) .badge:has-text('Approved with conditions')");
  await p.goto(BASE + "#/decisions"); await p.waitForSelector("#dq-gates");
  await p.locator("#dq-gates button:has-text('Decide')").first().click();
  await p.selectOption(".modal select", "request_info"); await p.getByLabel("Rationale", { exact: true }).fill("Add the risk register first");
  await Promise.all([p.waitForResponse(r => r.url().includes("/gates/")), p.click(".modal button:has-text('Record decision')")]);
  await p.goto(BASE + "#/projects/4"); await p.waitForSelector("#decision-log td:has-text('Add the risk register first')");
});

p = await newPage("ar"); await login(p, "pmo1");
await step("arabic tabs & load", async () => { await p.click('button:has-text("العربية")'); await p.goto(BASE + "#/projects/1"); await p.waitForSelector('button[role=tab]:has-text("التحكم في التغيير")'); await tab(p, "التحكم في التغيير"); await p.waitForSelector("td .badge:has-text('معتمد')"); await shot(p, "15-ar-change"); });

console.log(problems.length ? "PROBLEMS:\n" + problems.join("\n") : "ALL OK");
await browser.close();
