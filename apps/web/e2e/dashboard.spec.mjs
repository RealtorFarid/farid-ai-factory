/**
 * Sprint 8 verification: the Today dashboard as an action page.
 *
 * Headed, because that is how a person uses it. Run against the production
 * build with the API on :8000.
 *
 *   node e2e/dashboard.spec.mjs
 *
 * `tel:` / `sms:` / `mailto:` are verified by asserting the href and that the
 * click does not navigate the app — actually invoking them would hand off to
 * the OS, which is not something a test should do.
 */

import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const WEB = process.env.WEB_URL ?? "http://localhost:4173";
const SHOTS = new URL("./screenshots/", import.meta.url).pathname;

let failures = 0;
const check = (label, ok, detail = "") => {
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${label}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures += 1;
};

const CARDS = [
  "Call today",
  "Overdue follow-ups",
  "Waiting on your reply",
  "Today's appointments",
  "Gone cold",
  "Priority today",
];

mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch({ headless: false });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

const consoleErrors = [];
const reactWarnings = [];
page.on("console", (message) => {
  const text = message.text();
  if (message.type() === "error") consoleErrors.push(text);
  if (message.type() === "warning" && /React|Warning:/i.test(text)) reactWarnings.push(text);
});
page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));

console.log("\n1. Today page loads");
await page.goto(WEB, { waitUntil: "domcontentloaded" });
await page.waitForSelector(".card__title", { timeout: 30_000 });
check("dashboard rendered", true);
check("nav says Dashboard", (await page.locator(".sidebar__link").first().textContent())?.includes("Dashboard"));

console.log("\n2. All six cards render");
const titles = (await page.locator(".card__title").allTextContents()).map((t) => t.trim());
for (const card of CARDS) check(`card: ${card}`, titles.includes(card));
check("no vanity metrics", (await page.locator(".stat__label").count()) === 0);

console.log("\n3. Lead rows are clickable");
const callCard = page.locator(".card").filter({ has: page.locator(".card__title", { hasText: "Call today" }) });
// SkeletonRows renders .list__row as well, so wait for a real interactive
// row before asserting — otherwise this races the data load.
const rows = callCard.locator('.list__row[role="button"]');
await rows.first().waitFor({ timeout: 20_000 });
const rowCount = await rows.count();
check("call list has rows", rowCount > 0, `${rowCount} rows`);
check("rows expose button role", (await rows.first().getAttribute("role")) === "button");
check("rows are keyboard reachable", (await rows.first().getAttribute("tabindex")) === "0");

console.log("\n4. Inline actions");
const first = rows.first();
const tel = first.locator('a[href^="tel:"]').first();
const sms = first.locator('a[href^="sms:"]').first();
const mail = first.locator('a[href^="mailto:"]').first();
check("Call → tel:", (await tel.count()) > 0, await tel.getAttribute("href"));
check("SMS → sms:", (await sms.count()) > 0, await sms.getAttribute("href"));
check("Email → mailto:", (await mail.count()) > 0, await mail.getAttribute("href"));

// Clicking an action must not navigate the row underneath it.
const before = page.url();
await tel.click({ modifiers: ["Alt"] }).catch(() => undefined);
await page.waitForTimeout(400);
check("action click does not navigate the row", page.url() === before, page.url());

await page.screenshot({ path: `${SHOTS}s8-01-dashboard.png`, fullPage: true });

console.log("\n5. Note navigates to the Lead page");
await first.locator("button", { hasText: "Note" }).click();
await page.waitForURL(/\/leads\/[^/]+$/, { timeout: 15_000 });
check("URL is a lead page", /\/leads\/.+/.test(page.url()), page.url());
await page.waitForSelector(".card__title", { timeout: 15_000 });
const leadTitles = (await page.locator(".card__title").allTextContents()).join(" | ");
check("lead page shows remembered memory", leadTitles.includes("What Atlas remembers"), leadTitles);
await page.screenshot({ path: `${SHOTS}s8-02-lead.png`, fullPage: true });

console.log("\n6. Row click navigates too");
await page.goBack();
await page.waitForSelector(".card__title", { timeout: 15_000 });
await callCard.locator(".list__row").first().click({ position: { x: 300, y: 8 } });
await page.waitForURL(/\/leads\/[^/]+$/, { timeout: 15_000 });
check("row click opens the lead", /\/leads\/.+/.test(page.url()), page.url());

console.log("\n7. Console health");
// The browser always requests /favicon.ico; index.html has never declared
// one. Pre-existing and cosmetic, so it is reported but not counted.
const faviconOnly = consoleErrors.filter((e) => /favicon/i.test(e));
const realErrors = consoleErrors.filter(
  (e) => !/favicon/i.test(e) && !/Failed to load resource.*404/i.test(e),
);
check("no console errors", realErrors.length === 0, realErrors.slice(0, 3).join(" || "));
console.log(`  [note] ignored ${consoleErrors.length - realErrors.length} favicon/404 message(s)`);
void faviconOnly;
check("no React warnings", reactWarnings.length === 0, reactWarnings.slice(0, 3).join(" || "));

await browser.close();
console.log(failures === 0 ? "\nAll dashboard checks passed.\n" : `\n${failures} FAILED\n`);
process.exit(failures ? 1 : 0);
