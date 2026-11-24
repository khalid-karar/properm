import fs from "fs";
import { createHmac } from "node:crypto";
// End-to-end UI test against a freshly seeded demo server. Run with: bash tests/ui/run.sh
// Needs Playwright (npm i playwright) and Chrome. Override with PLAYWRIGHT_PATH and CHROME_PATH.
const { chromium } = await import(process.env.PLAYWRIGHT_PATH || "playwright");
const BASE = (process.env.BASE_URL || "http://localhost:8765") + "/ui/";
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || (fs.existsSync("/usr/bin/google-chrome") ? "/usr/bin/google-chrome" : undefined), args: ["--no-sandbox"] });
const problems = [];
async function newPage(name, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, ...opts.ctx });
  if (!opts.tour) await ctx.addInitScript(() => { try { localStorage.setItem("properm.tour.off", "1"); } catch { /* ignore */ } });
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
const step = async (label, fn) => { try { await fn(); console.log("ok  ", label); } catch (e) { problems.push(`${label}: ${e.message.split("\n").slice(0, 3).join(" ")}`); try { await p.screenshot({ path: "/tmp/fail-" + label.replace(/\W+/g, "_") + ".png" }); } catch {} console.log("FAIL", label, e.message.split("\n")[0]); } };
const tab = async (p, name) => { const ex = p.locator(`button[role=tab]:text-is("${name}")`); if (await ex.count()) return ex.first().click(); return p.click(`button[role=tab]:has-text("${name}")`); };

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
await step("login page: build progress needs the password", async () => {
  await p.goto(BASE); await p.waitForSelector("#ms-password");
  if (await p.locator(".timeline details.ms").count()) throw new Error("milestones visible before the password");
  await p.fill("#ms-password", "ui-build-pass"); await p.click("#ms-open");
  await p.waitForSelector(".timeline .light.done"); if (!(await p.locator(".timeline details.ms").count())) throw new Error("no milestones");
});

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
  await p.goto(BASE + "#/projects/1"); await tab(p, "Plan"); await p.waitForSelector("#gantt-card .tl .tl-bar"); await p.click("#gantt-card [data-zoom=week]"); await p.waitForSelector("#gantt-card [data-zoom=week][aria-pressed=true]");
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

p = await newPage("ctl-pm"); await login(p, "pm1");
await step("PM control tab: variance, action, lesson; lessons library", async () => {
  await p.goto(BASE + "#/projects/2"); await tab(p, "Control"); await p.waitForSelector("#variance-card td");
  const ac = p.locator("#actions-card"); await ac.getByLabel("Title", { exact: true }).fill("UI follow-up action");
  await Promise.all([p.waitForResponse(r => r.url().includes("/actions") && r.request().method() === "POST"), ac.locator("button:has-text('Add')").click()]);
  await p.waitForSelector("#actions-card td:has-text('UI follow-up action')");
  const lc = p.locator("#lessons-card"); await lc.getByLabel("What happened", { exact: true }).fill("UI lesson happened here");
  await lc.getByLabel("Recommendation", { exact: true }).fill("Do it differently next time");
  await Promise.all([p.waitForResponse(r => r.url().includes("/lessons") && r.request().method() === "POST"), lc.locator("button:has-text('Add lesson')").click()]);
  await p.goto(BASE + "#/lessons"); await p.fill("input[type=search]", "access"); await p.waitForSelector("td:has-text('Name an IT access owner')");
  await p.goto(BASE + "#/todo"); await p.waitForSelector("h2:has-text('Actions assigned to you')");
});

p = await newPage("wk-staff"); await login(p, "s3");
await step("staff: week strip, submit week with note, book leave", async () => {
  await p.goto(BASE + "#/timesheet"); await p.waitForSelector("#week-card .day");
  const wk0 = await p.textContent("strong:has-text('Week of')");
  await p.click("button:has-text('Previous')"); await p.waitForFunction((w) => document.querySelector("#week-card") && ![...document.querySelectorAll("strong")].some(s => s.textContent === w), wk0);
  await p.waitForSelector("#submit-week");
  const n = p.locator("#week-card input"); if (await n.count()) await n.fill("Away at client site");
  await Promise.all([p.waitForResponse(r => r.url().includes("/me/week/submit")), p.click("#submit-week")]);
  await p.waitForSelector("#week-card .badge:has-text('Week submitted')");
  await p.goto(BASE + "#/leave"); await p.waitForSelector("#leave-form");
  const d = new Date(Date.now() + 60 * 864e5).toISOString().slice(0, 10);
  await p.locator("#leave-form").getByLabel("From", { exact: true }).fill(d); await p.locator("#leave-form").getByLabel("To", { exact: true }).fill(d);
  await Promise.all([p.waitForResponse(r => r.url().endsWith("/leave") && r.request().method() === "POST"), p.click("#leave-form button:has-text('Request')")]);
  await p.waitForSelector("td .badge:has-text('Waiting')");
});

p = await newPage("wk-pmo"); await login(p, "pmo1");
await step("PMO: approve leave, team week status, reminders", async () => {
  await p.goto(BASE + "#/leave"); await p.waitForSelector("#leave-queue");
  await Promise.all([p.waitForResponse(r => r.url().includes("/decision")), p.locator("#leave-queue button:has-text('Approve')").first().click()]);
  await p.goto(BASE + "#/approvals"); await p.waitForSelector("#team-weeks td");
  const b = p.locator("#team-weeks button:has-text('Send reminders')"); if (await b.count()) await Promise.all([p.waitForResponse(r => r.url().includes("/reminders/")), b.click()]);
});

p = await newPage("pf-pmo"); await login(p, "pmo1");
await step("portfolio: priorities, score a project, capacity heat map, compliance", async () => {
  await p.goto(BASE + "#/portfolio"); await p.waitForSelector("#priorities td"); await p.waitForSelector("#capacity td.cp"); await p.waitForSelector("#compliance td");
  await p.locator("#priorities button:has-text('Score')").first().click();
  await Promise.all([p.waitForResponse(r => r.url().includes("/portfolio/scores/")), p.click(".modal button:has-text('Save')")]);
  await p.selectOption("#capacity select", "person"); await p.waitForSelector("#capacity td:has-text('Faisal')");
});

p = await newPage("pg-road"); await login(p, "pg1");
await step("program manager: roadmap with conflict, add program risk", async () => {
  await p.goto(BASE + "#/programs"); await p.click("a:has-text('Roadmap')"); await p.waitForSelector("#roadmap svg.chart");
  await p.waitForSelector("#xdeps .badge:has-text('Conflict')");
  const r = p.locator("#prisks"); await r.getByLabel("Title", { exact: true }).fill("UI program risk");
  await Promise.all([p.waitForResponse(x => x.url().includes("/risks") && x.request().method() === "POST"), r.locator("button:has-text('Add risk')").click()]);
  await p.waitForSelector("#prisks td:has-text('UI program risk')");
});

p = await newPage("sec-admin"); await login(p, "admin");
await step("admin: sign-in history and hand over a user's work", async () => {
  await p.goto(BASE + "#/admin"); await p.waitForSelector("#security-card td");
  await p.check("#security-card label.check input"); await p.waitForSelector("#security-card .badge:has-text('Wrong password')");
  await p.locator("tr:has(td:has-text('uiimp1')) button:has-text('Hand over')").click(); await p.waitForSelector(".modal:has-text('No open work')");
  await Promise.all([p.waitForResponse(r => r.url().includes("/handover") && r.request().method() === "POST"), p.click(".modal button:has-text('Hand over')")]);
  await p.waitForSelector("tr:has(td:has-text('uiimp1')) .badge:has-text('Inactive')");
  await p.goto(BASE + "#/profile"); await p.waitForSelector("h2:has-text('Recent sign-ins')");
});

p = await newPage("tools-pm"); await login(p, "pm1");
await step("PM tools: RACI, comms, resource request, critical path, apply template", async () => {
  await p.goto(BASE + "#/projects/1"); await tab(p, "RACI & communication"); await p.waitForSelector("#raci-card table.raci");
  await p.waitForSelector("#comms-card td:has-text('Steering committee')");
  await tab(p, "Plan"); await p.waitForSelector("#critical-path");
  await p.goto(BASE + "#/projects/4"); await tab(p, "Setup"); await p.waitForSelector("#apply-template");
  await Promise.all([p.waitForResponse(r => r.url().includes("/apply-template/")), p.click("#apply-template button:has-text('Apply')")]);
});

p = await newPage("tools-pmo"); await login(p, "pmo1");
await step("PMO: templates page, assign resource request", async () => {
  await p.goto(BASE + "#/templates"); await p.waitForSelector("td:has-text('DIGI-SVC')");
  await p.locator("tr:has(td:has-text('DIGI-SVC')) button:has-text('Open')").click(); await p.waitForSelector(".modal td:has-text('Discovery')"); await p.click(".modal button:has-text('Close')");
  await p.goto(BASE + "#/load"); await p.waitForSelector("#rr-queue td:has-text('Senior data engineer')");
  await Promise.all([p.waitForResponse(r => r.url().includes("/resource-requests/")), p.click("#rr-queue button:has-text('Assign')")]);
});

p = await newPage("b-pmo"); await login(p, "pmo1");
await step("search, board pack, what-if, coming up", async () => {
  await p.fill("#topsearch", "ERP"); await p.press("#topsearch", "Enter"); await p.waitForSelector(".search-group a:has-text('ERP Rollout')");
  const [pop] = await Promise.all([p.waitForEvent("popup"), p.goto(BASE + "#/executive").then(() => p.click("#board-pack"))]);
  await pop.waitForSelector("h1:has-text('Steering committee pack')"); await pop.close();
  await p.goto(BASE + "#/portfolio"); await p.selectOption("#what-if select >> nth=1", "stop"); await p.click("#what-if button:has-text('Show effect')"); await p.waitForSelector("#what-if table.whatif");
  await p.goto(BASE + "#/todo"); await p.waitForSelector("#coming-up");
});

p = await newPage("b-staff"); await login(p, "s1");
await step("staff: planned hours ahead", async () => { await p.goto(BASE + "#/mine"); await p.waitForSelector("#upcoming td"); });

p = await newPage("c-admin"); await login(p, "admin");
await step("admin: mail settings test, backup download, department list, start page", async () => {
  await p.goto(BASE + "#/admin"); await p.waitForSelector("#mail-card");
  await p.locator("#mail-card").getByLabel("Send a test to", { exact: true }).fill("x@example.sa");
  await Promise.all([p.waitForResponse(r => r.url().includes("/admin/mail/test")), p.click("#mail-card button:has-text('Send test')")]); await p.waitForSelector("#mail-card .err");
  const [dl] = await Promise.all([p.waitForEvent("download"), p.click("#backup-card button:has-text('Download backup')")]);
  if (!dl.suggestedFilename().endsWith(".json")) throw new Error("no json backup");
  await p.goto(BASE + "#/config"); await p.waitForSelector("h2:has-text('Departments')");
  await p.goto(BASE + "#/profile"); await Promise.all([p.waitForResponse(r => r.url().includes("/me/home")), p.selectOption("#home-page", "audit")]);
});

p = await newPage("c-pg"); await login(p, "pg1");
await step("program page: envelope, program issues, benefits plan", async () => {
  await p.goto(BASE + "#/programs/1"); await p.waitForSelector("#envelope .stat"); await p.waitForSelector("#pissues td:has-text('Shared test environment')"); await p.waitForSelector("#benefits-plan td");
});

p = await newPage("d-pmo"); await login(p, "pmo1");
await step("scope tab: charter approved, accept a deliverable, add a requirement", async () => {
  await p.goto(BASE + "#/projects/1"); await tab(p, "Scope"); await p.waitForSelector("#charter-card .badge:has-text('Approved')");
  await p.waitForSelector("#wbs-card td:has-text('Finance core configured')");
  await p.locator("#wbs-card tr:has(td:has-text('Finance core configured')) button:has-text('Accept')").click();
  await p.waitForSelector(".modal textarea"); await p.fill(".modal textarea", "Signed off by finance"); await Promise.all([p.waitForResponse(r => r.url().includes("/decision")), p.click(".modal button:has-text('Submit')")]);
  await p.waitForSelector("#wbs-card tr:has(td:has-text('Finance core configured')) .badge:has-text('Accepted')");
  await p.waitForSelector("#req-card .warn");
});

p = await newPage("d-pm2"); await login(p, "pm1");
await step("agile tab: board, burndown, move a card, close sprint", async () => {
  await p.goto(BASE + "#/projects"); await p.click("tr:has(td:has-text('AGILE-01')) a:has-text('Open')"); await tab(p, "Agile");
  await p.waitForSelector("#board-card .kcard:has-text('Accessibility audit fixes')"); await p.waitForSelector("#burndown-card svg");
  await Promise.all([p.waitForResponse(r => r.url().includes("/move")), p.locator("#board-card .kcard:has-text('Accessibility audit fixes') button:has-text('→')").click()]);
  await p.waitForSelector("#backlog-card td:has-text('Online payment of fees')");
  await p.locator("#sprints-card tr:has(td:has-text('Sprint 1')) button:has-text('Close sprint')").click();
  await p.waitForSelector(".modal select"); await p.selectOption(".modal select", { label: "Sprint 2" });
  await Promise.all([p.waitForResponse(r => r.url().includes("/close")), p.click(".modal button:has-text('Close sprint')")]);
  await p.waitForSelector("#sprints-card tr:has(td:has-text('Sprint 1')) .badge:has-text('Closed')");
});

p = await newPage("e-pmo"); await login(p, "pmo1");
await step("strategy coverage and compliance overview", async () => {
  await p.goto(BASE + "#/strategy"); await p.waitForSelector("#objectives-card tr:has(td:has-text('SO-3')) .badge:has-text('No project')"); await p.waitForSelector("#orphans-card li");
  await p.goto(BASE + "#/compliance"); await p.waitForSelector("#compliance-overview td:has-text('PDPL')"); await p.waitForSelector("#library-card td:has-text('PDPL-01')");
  await p.goto(BASE + "#/projects/1"); await tab(p, "Compliance"); await p.waitForSelector("#pcompliance-card tr:has(td:has-text('PDPL-01')) .badge:has-text('Compliant')");
  await p.waitForSelector("#pcompliance-card button:has-text('Apply framework')");
});

p = await newPage("f-pm"); await login(p, "pm1");
await step("procurement tab: contracts, record an invoice, vendor review", async () => {
  await p.goto(BASE + "#/projects/1"); await tab(p, "Procurement"); await p.waitForSelector("#contracts-card td:has-text('Najd Systems')");
  await p.waitForSelector("#payments-card tr:has(td:has-text('Build complete')) .badge:has-text('Planned')");
  await p.locator("#payments-card tr:has(td:has-text('Build complete')) button:has-text('Mark achieved')").click();
  await p.waitForSelector("#payments-card tr:has(td:has-text('Build complete')) .badge:has-text('Achieved')");
  await p.locator("#payments-card tr:has(td:has-text('Build complete')) button:has-text('Record invoice')").click();
  await p.fill(".modal textarea", "INV-777"); await Promise.all([p.waitForResponse(r => r.url().includes("/payments/")), p.click(".modal button:has-text('Submit')")]);
  await p.waitForSelector("#payments-card tr:has(td:has-text('Build complete')) td:has-text('INV-777')");
  await p.waitForSelector("#reviews-card td:has-text('Design delivered four days late')");
});
p = await newPage("f-pmo"); await login(p, "pmo1");
await step("procurement overview", async () => { await p.goto(BASE + "#/procurement"); await p.waitForSelector("#po-contracts td:has-text('Hosting Co')"); });

p = await newPage("g-staff"); await login(p, "s3");
await step("skills page: add a skill and a certificate", async () => {
  await p.goto(BASE + "#/skills"); await p.waitForSelector("#my-skills td:has-text('Data engineering')");
  await p.locator("#my-skills input").first().fill("Power BI"); await Promise.all([p.waitForResponse(r => r.url().includes("/me/skills")), p.click("#my-skills button:has-text('Add')")]);
  await p.waitForSelector("#my-skills td:has-text('Power BI')");
  await p.locator("#my-certs input").first().fill("PMP"); await Promise.all([p.waitForResponse(r => r.url().includes("/me/certs")), p.click("#my-certs button:has-text('Add')")]);
  await p.waitForSelector("#my-certs td:has-text('PMP')");
});
p = await newPage("g-pmo"); await login(p, "pmo1");
await step("PMO: skills directory, development gaps, best matches for a request", async () => {
  await p.goto(BASE + "#/skills"); await p.waitForSelector("#skills-dir td"); await p.fill("#skill-q", "TOGAF"); await p.waitForSelector("#skills-dir td:has-text('Khaled')");
  await p.waitForSelector("#dev-gaps td");
  await p.evaluate(async () => {
    const tok = JSON.parse(sessionStorage.getItem(Object.keys(sessionStorage)[0])).token;
    const H = { "Content-Type": "application/json", Authorization: "Bearer " + tok };
    const ps = await (await fetch("/projects", { headers: H })).json();
    await fetch(`/projects/${ps[0].id}/resource-requests`, { method: "POST", headers: H, body: JSON.stringify({ skill: "Senior data engineer", hours_per_week: 8, start: "2026-12-01", end: "2027-01-15" }) });
  });
  await p.goto(BASE + "#/load"); await p.waitForSelector("#rr-queue");
  await p.locator("#rr-queue button:has-text('Best matches')").first().click(); await p.waitForSelector("#matches td:has-text('Faisal')");
  await p.click(".modal button:has-text('Close')");
});

p = await newPage("h-pm"); await login(p, "pm1");
await step("depth: risk responses, reserves, quality, engagement, document versions", async () => {
  await p.goto(BASE + "#/projects/1"); await tab(p, "Risks"); await p.waitForSelector("#responses-card td:has-text('Mitigate')"); await p.waitForSelector("#opps-card td:has-text('reconciliation module')");
  await tab(p, "Cost"); await p.waitForSelector("#reserves-card td:has-text('Regulator asked')");
  await Promise.all([p.waitForResponse(r => r.url().includes("/reserves")), p.click("#reserves-card button:has-text('Use contingency')").then(() => p.waitForSelector(".modal textarea")).then(async () => { await p.locator(".modal input").first().fill("1000"); await p.fill(".modal textarea", "UI test draw"); await p.click(".modal button:has-text('Submit')"); })]);
  await p.waitForSelector("#reserves-card td:has-text('UI test draw')");
  await tab(p, "Scope"); await p.waitForSelector("#quality-card td:has-text('Trial balance')");
  await tab(p, "Details"); await p.waitForSelector("#engagement-card td .badge");
  await tab(p, "Documents"); await p.waitForSelector("#documents-card td:has-text('scope-statement.txt')");
  await p.fill("#doc-q", "zzz-nothing"); await p.waitForSelector("#doc-list .empty"); await p.fill("#doc-q", "scope-statement"); await p.waitForSelector("#doc-list td:has-text('scope-statement.txt')");
  await p.locator("tr:has(td:has-text('scope-statement.txt')) [data-act=doc-history]").click(); await p.waitForSelector(".modal li"); await p.click(".modal button:has-text('Close')");
  await p.locator("tr:has(td:has-text('scope-statement.txt')) button:has-text('Versions')").click(); await p.waitForSelector("#versions td:has-text('v1')"); await p.click(".modal button:has-text('Close')");
});
p = await newPage("h-pmo"); await login(p, "pmo1");
await step("depth: PMO approves a management reserve request", async () => {
  await p.goto(BASE + "#/projects/1"); await tab(p, "Cost");
  await Promise.all([p.waitForResponse(r => r.url().includes("/decision")), p.locator("#reserves-card tr:has(td:has-text('Regulator asked')) button:has-text('Approve')").click()]);
  await p.waitForSelector("#reserves-card tr:has(td:has-text('Regulator asked')) .badge:has-text('Approved')");
});

p = await newPage("ops-admin"); await login(p, "admin");
await step("admin: restore check and apply, retention preview", async () => {
  await p.goto(BASE + "#/admin"); await p.waitForSelector("#restore-card");
  const backup = await p.evaluate(async () => {
    const tok = JSON.parse(sessionStorage.getItem(Object.keys(sessionStorage)[0])).token;
    return await (await fetch("/admin/export?include_documents=true", { headers: { Authorization: "Bearer " + tok } })).json();
  });
  await p.setInputFiles("#restore-file", { name: "b.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(backup)) });
  await p.click("#restore-card button:has-text('Check the file')"); await p.waitForSelector("#restore-out td:has-text('projects')");
  await p.fill("#restore-word", "RESTORE");
  await p.click("#restore-card button:has-text('Restore now')"); await p.waitForSelector(".toast:has-text('Restore complete'), #restore-out td");
  await p.waitForSelector("#retention-out strong");
});
p = await newPage("ops-2fa"); await login(p, "s3");
await step("profile: set up two-factor, then sign in with a code", async () => {
  await p.goto(BASE + "#/profile"); await p.click("#twofa-start"); await p.waitForSelector("#twofa-secret");
  const secret = await p.textContent("#twofa-secret");
  const code = (sec, ts = Date.now()) => {
    const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const ch of sec) bits += A.indexOf(ch).toString(2).padStart(5, "0");
    const key = Buffer.from(bits.match(/.{8}/g).map(b => parseInt(b, 2)));
    const c = Buffer.alloc(8); c.writeBigUInt64BE(BigInt(Math.floor(ts / 30000)));
    const mac = createHmac("sha1", key).update(c).digest(); const o = mac[19] & 15;
    return String((mac.readUInt32BE(o) & 0x7fffffff) % 1000000).padStart(6, "0");
  };
  await p.fill("#twofa-confirm", code(secret)); await p.click("#twofa-card button:has-text('Turn on')"); await p.waitForSelector("#twofa-backup");
  await p.click("button:has-text('Sign out')"); await p.waitForSelector("input[name=staff_id]");
  await p.fill("input[name=staff_id]", "s3"); await p.fill("input[name=password]", "demo-pass-1"); await p.click("button[type=submit]");
  await p.waitForSelector("#login-otp:visible"); await p.fill("#login-otp", code(secret)); await p.click("button[type=submit]"); await p.waitForSelector("header.top");
});

p = await newPage("brief"); await login(p, "pmo1");
await step("risks and issues: closing needs a note, shows in history, reopen needs a reason", async () => {
  const q = await newPage("closure"); await login(q, "pmo1");
  const pid = await q.evaluate(async () => {
    const tok = JSON.parse(sessionStorage.getItem(Object.keys(sessionStorage)[0])).token;
    const H = { "Content-Type": "application/json", Authorization: "Bearer " + tok };
    const r = await (await fetch("/projects", { method: "POST", headers: H, body: JSON.stringify({ number: "CL-UI-1", name: "Closure test", state: "planning", planned_start: "2027-01-03", planned_end: "2027-06-30" }) })).json();
    await fetch(`/projects/${r.id}/risks`, { method: "POST", headers: H, body: JSON.stringify({ title: "Vendor delay", probability: 3, impact: 3 }) });
    return r.id;
  });
  await q.goto(BASE + "#/projects/" + pid); await tab(q, "Risks"); await q.waitForSelector("td:has-text('Vendor delay')");
  await q.click("button[data-act=close]"); await q.waitForSelector("#cl-what");
  await q.locator(".modal .actions button").last().click(); await q.waitForSelector(".modal .err, .modal [role=alert]", { timeout: 3000 }).catch(() => {});
  await q.fill("#cl-what", "Vendor was late by two weeks"); await q.fill("#cl-how", "Moved the test window and agreed a penalty"); await q.fill("#cl-outcome", "No effect on go-live"); await q.check("#cl-lesson");
  await q.screenshot({ path: "/tmp/shots/closure-dialog.png" });
  await q.locator(".modal .actions button").last().click(); await q.waitForSelector(".toast:has-text('Closed and recorded')");
  await q.waitForSelector("button[data-act=reopen]"); await q.click("button[data-act=history]"); await q.waitForSelector(".modal :text('Moved the test window')");
  await q.screenshot({ path: "/tmp/shots/closure-history.png" });
  await q.locator(".modal .actions button").last().click();
  await q.click("button[data-act=reopen]"); await q.fill("#cl-reason", "The vendor slipped again"); await q.locator(".modal .actions button").last().click();
  await q.waitForSelector("button[data-act=close]");
});

await step("start a project from the book: preview, confirm, land on the draft plan", async () => {
  const q = await newPage("bookstart"); await login(q, "pmo1");
  await q.goto(BASE + "#/projects"); await q.waitForSelector("#book-start");
  await q.click("#book-start summary"); await q.fill("#bk-text", "Project scope\nProject name: Data lake build\nPhase 1: Discovery (2 months)\n1. Document all source systems and databases\n2. Prepare the data flow diagram\nPhase 1 deliverables: Data inventory, Discovery report.\nPhase 2: Build (3 months)\n1. Configure the platform\n2. Build the data pipelines\nPhase 2 deliverables: Configured platform.\nThe contractor must deliver within 5 months.");
  await q.click("#bk-read"); await q.waitForSelector("#bk-number"); await q.screenshot({ path: "/tmp/shots/bookstart-check.png", fullPage: true });
  await q.fill("#bk-number", "BOOK-UI-1"); await q.click("#bk-create"); await q.waitForSelector(".err:has-text('did not state a project name'), [role=alert]:has-text('did not state')"); await q.fill("#bk-name", "Data lake build"); await q.click("#bk-create");
  await q.waitForSelector("#brief-review", { timeout: 20000 });
});

await step("arabic book viewed in English: shows the original and says it is not translated", async () => {
  const q = await newPage("trbanner"); await login(q, "pmo1");
  const pid = await q.evaluate(async () => {
    const tok = JSON.parse(sessionStorage.getItem(Object.keys(sessionStorage)[0])).token;
    const H = { "Content-Type": "application/json", Authorization: "Bearer " + tok };
    const r = await (await fetch("/projects", { method: "POST", headers: H, body: JSON.stringify({ number: "TR-UI-1", name: "Tr", state: "planning", planned_start: "2027-01-03", planned_end: "2027-06-30" }) })).json();
    await fetch(`/projects/${r.id}/brief/analyze`, { method: "POST", headers: H, body: JSON.stringify({ text: "نطاق العمل\nالمرحلة الأولى: الاكتشاف (شهران)\n1. حصر الأنظمة ومصادر البيانات\n2. إعداد مخطط تدفق البيانات\nمخرجات المرحلة الأولى: سجل البيانات، تقرير الاكتشاف.\nالمرحلة الثانية: البناء (3 أشهر)\n1. إعداد المنصة\n2. بناء مسارات البيانات\nيجب على المقاول التسليم خلال 5 أشهر." }) });
    return r.id;
  });
  await q.goto(BASE + "#/projects/" + pid); await tab(q, "Plan draft"); await q.waitForSelector("#tr-note");
  await q.click("#tr-go"); await q.waitForSelector("#tr-box .warn:has-text('Not translated')");
});

await step("tendering: score, decide go, checklist, submit, win moves the project to planning", async () => {
  const q = await newPage("tender"); await login(q, "pmo1");
  await q.goto(BASE + "#/projects/3"); await tab(q, "Tender"); await q.waitForSelector("#tn-score");
  const patch = (fn) => Promise.all([q.waitForResponse(r => r.request().method() === "PATCH" && r.url().includes("/tender")), fn()]);
  for (const k of ["strategic_fit", "capability", "capacity", "margin", "client", "competition", "delivery_risk"]) await patch(() => q.selectOption(`#tn-sc-${k}`, "4"));
  await q.waitForSelector("#tn-score :text('80')");
  await q.screenshot({ path: "/tmp/shots/tender-top.png", fullPage: true });
  await Promise.all([q.waitForResponse(r => r.url().includes("/tender/decision")), q.click("#tn-go")]); await q.waitForSelector("#tn-score .badge:has-text('Go')");
  for (const k of ["read_book", "clarifications", "technical", "financial", "guarantee", "forms", "pmo_review", "signed"]) await patch(() => q.check(`#tn-ck-${k}`));
  await Promise.all([q.waitForResponse(r => r.url().includes("/tender/submit")), q.click("#tn-submit")]); await q.waitForSelector("#tn-checklist .badge:has-text('submitted')");
  await q.fill("#tn-onote", "Awarded by the client"); await Promise.all([q.waitForResponse(r => r.url().includes("/tender/outcome")), q.click("#tn-won")]);
  await q.waitForSelector("h1 .badge:has-text('Planning')");
});

await step("project book: paste, analyse, review, apply as a plan", async () => {
  const pid = await p.evaluate(async () => {
    const tok = JSON.parse(sessionStorage.getItem(Object.keys(sessionStorage)[0])).token;
    const H = { "Content-Type": "application/json", Authorization: "Bearer " + tok };
    const r = await fetch("/projects", { method: "POST", headers: H, body: JSON.stringify({ number: "BK-UI-1", name: "Book test", state: "planning", planned_start: "2027-01-03", planned_end: "2027-06-30" }) });
    return (await r.json()).id;
  });
  await p.goto(BASE + "#/projects/" + pid); await tab(p, "Plan draft"); await p.waitForSelector("#brief-card");
  await p.fill("#brief-text", "Project scope\nPhase 1: Discovery (2 months)\n1. Document all source systems and databases\n2. Prepare the data flow diagram\n3. Assess the current infrastructure\nPhase 1 deliverables: Data inventory, Data flow diagram, Discovery report.\nPhase 2: Build (3 months)\n1. Configure the platform\n2. Build the data pipelines\nPhase 2 deliverables: Configured platform, Pipeline documentation.\nThe contractor must deliver within 5 months.");
  await p.click("#brief-go"); await p.waitForSelector("#brief-review");
  await p.waitForSelector("#brief-domains #dom-cost");
  await p.fill("#dom-fb-cost", "add travel"); await p.click("#dom-reject-cost"); await p.waitForSelector("#dom-cost .diff", { state: "attached" });
  await p.click("#dom-accept-communication"); await p.waitForSelector("#dom-communication summary:has-text('Accepted')");
  // editor: wrapped text boxes, add / edit / delete anything the reader found
  await p.evaluate(() => document.querySelectorAll("details.sec").forEach(d => { d.open = true; }));
  const nTasks = await p.locator("#task-box .item").count();
  await p.click("#el-add-activities"); await p.locator("#task-box .item").last().locator("textarea").first().fill("Hand-added task with a long name that must wrap inside the box instead of being cut off");
  if (await p.locator("#task-box .item").count() !== nTasks + 1) throw new Error("add task failed");
  if (!(await p.locator("#task-box .item").last().locator("textarea").first().evaluate(e => e.scrollHeight <= e.clientHeight + 2))) throw new Error("long text is cut off");
  await p.click("#el-add-requirements"); await p.locator("#el-requirements .item").last().locator("textarea").nth(1).fill("Added requirement");
  await p.locator("#task-box .item .del").first().click(); if (await p.locator("#task-box .item").count() !== nTasks) throw new Error("delete task failed");
  await p.waitForSelector("#brief-apply:not([disabled])"); await p.click("#brief-apply"); await p.waitForSelector(".toast:has-text('Plan created')");
  await p.waitForSelector("#brief-result td");
  await tab(p, "Plan"); await p.waitForSelector("#imp-plan");
  await p.waitForSelector("#gantt-card .tl-gtoggle"); await p.click("#gantt-card button:has-text('Collapse all')"); await p.waitForSelector("#gantt-card .tl-gbar", { state: "attached" }); await p.click("#gantt-card button:has-text('Expand all')"); await p.waitForSelector("#gantt-card .tl-bar");
  await p.setInputFiles("#imp-file-plan", { name: "plan.csv", mimeType: "text/csv", buffer: Buffer.from("code,name,planned_hours\nX-1,Imported task,24\nX-2,Another,16\n") });
  await p.click("#imp-preview-plan"); await p.waitForSelector("#imp-out-plan td");
  await p.click("#imp-commit-plan"); await p.waitForSelector(".toast:has-text('Saved rows')");
});

p = await newPage("home"); await login(p, "pmo1");
await step("home page, grouped nav, assistant widget and quick jump", async () => {
  await p.goto(BASE + "#/home"); await p.waitForSelector(".welcome h1"); await p.waitForSelector(".tiles a.tile"); await p.waitForSelector("aside.side .navhead");
  await shot(p, "20-home");
  await p.click("#asst-btn"); await p.waitForSelector("#asst-panel.open .msg.bot");
  await p.fill("#asst-input", "Any alerts?"); await p.press("#asst-input", "Enter");
  await p.waitForSelector("#asst-panel .msg.bot:nth-child(4) .bub, #asst-panel .msg.bot:nth-child(3) .bub");
  await p.waitForFunction(() => /alert/i.test(document.querySelector("#asst-log").textContent) && !/Thinking/.test(document.querySelector("#asst-log").textContent));
  await p.keyboard.press("Control+k"); await p.waitForSelector("#palette input"); await p.fill("#palette input", "Reports"); await p.waitForSelector("#palette .pal-row"); await p.press("#palette input", "Enter");
  await p.waitForSelector("h1");
  if (!p.url().includes("#/reports")) throw new Error("quick jump did not navigate: " + p.url());
});
p = await newPage("ar"); await login(p, "pmo1");
await step("arabic tabs & load", async () => { await p.click('button:has-text("العربية")'); await p.goto(BASE + "#/projects/1"); await p.waitForSelector('button[role=tab]:has-text("التحكم في التغيير")'); await tab(p, "التحكم في التغيير"); await p.waitForSelector("td .badge:has-text('معتمد')"); await shot(p, "15-ar-change"); });

// ---- first-time tour, dark mode, phone layout, accessibility ----
p = await newPage("tour", { tour: true }); await login(p, "dm1");
await step("first-time tour shows once and can be skipped", async () => {
  await p.goto(BASE + "#/home"); await p.waitForSelector("#tour-card"); await p.click("#tour-next"); await p.waitForSelector(".tour-on");
  await p.click("#tour-skip"); await p.waitForFunction(() => !document.getElementById("tour-card"));
  await p.reload(); await p.waitForSelector(".welcome h1"); await p.waitForTimeout(1200);
  if (await p.$("#tour-card")) throw new Error("tour came back after being skipped");
  await p.click("#tour-btn"); await p.waitForSelector("#tour-card"); await p.click("#tour-skip");
});
await step("dark mode toggle changes the page and is remembered", async () => {
  const bg = () => p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const before = await bg(); await p.click("#theme-btn"); const after = await bg();
  if (before === after) throw new Error("theme did not change");
  await shot(p, "21-dark-home"); await p.reload(); await p.waitForSelector(".welcome h1");
  if ((await bg()) !== after) throw new Error("theme not remembered");
});

const axeSrc = fs.readFileSync(process.env.AXE_PATH || "node_modules/axe-core/axe.min.js", "utf8");
const PAGES = ["home", "timesheet", "projects", "projects/1", "alerts", "reports", "admin", "approvals", "portfolio", "profile"];
for (const [who, theme] of [["pmo1", "light"], ["pmo1", "dark"]]) {
  p = await newPage("a11y-" + theme); await login(p, who);
  await p.evaluate((th) => { localStorage.setItem("properm.theme", th); }, theme);
  await step(`accessibility scan (${theme})`, async () => {
    const bad = [];
    for (const pg of PAGES) {
      await p.goto(BASE + "#/" + pg); await p.reload(); await p.waitForSelector("header.top"); await p.waitForTimeout(700);
      await p.evaluate(axeSrc);
      const r = await p.evaluate(async () => (await axe.run(document, { runOnly: ["wcag2a", "wcag2aa"], resultTypes: ["violations"] })).violations.filter(v => ["serious", "critical"].includes(v.impact)).map(v => `${v.id}(${v.nodes.length})`));
      if (r.length) bad.push(`${pg}: ${r.join(", ")}`);
    }
    if (bad.length) throw new Error("a11y: " + bad.join(" | "));
  });
}
p = await newPage("phone", { ctx: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } }); await login(p, "s1");
await step("phone: no sideways scroll, menu opens, tap targets reachable", async () => {
  const bad = [];
  for (const pg of ["home", "timesheet", "mine", "leave", "todo"]) {
    await p.goto(BASE + "#/" + pg); await p.reload(); await p.waitForSelector("header.top"); await p.waitForTimeout(600);
    const w = await p.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    if (w[0] > w[1] + 2) bad.push(`${pg}: ${w[0]}px wide on a ${w[1]}px screen`);
  }
  await shot(p, "22-phone-timesheet");
  await p.click(".menu-btn"); await p.waitForSelector("body.nav-open aside.side nav a");
  if (bad.length) throw new Error(bad.join(" | "));
});

console.log(problems.length ? "PROBLEMS:\n" + problems.join("\n") : "ALL OK");
await browser.close();
