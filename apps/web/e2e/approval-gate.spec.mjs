/**
 * Sprint 4A acceptance test, driven through a real browser.
 *
 * Proves in the UI what the backend tests prove at the API:
 *   approve one action, reject another
 *   -> the approved one happens, the rejected one does not
 *   -> the run reports PARTIAL
 *   -> the interface says so plainly
 *
 * Run against a live stack:
 *   PROPILOT_DEFAULT_MODEL=stub make run      # API  :8000
 *   npm run dev                               # web  :5173
 *   node e2e/approval-gate.spec.mjs
 *
 * Exits non-zero on the first failed assertion, and writes screenshots to
 * e2e/screenshots/ either way.
 */

import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const WEB = process.env.WEB_URL ?? "http://localhost:5173";
const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const SHOTS = new URL("./screenshots/", import.meta.url).pathname;

let failures = 0;

function check(label, condition, detail = "") {
  const mark = condition ? "PASS" : "FAIL";
  if (!condition) failures += 1;
  console.log(`  [${mark}] ${label}${detail ? ` — ${detail}` : ""}`);
}

async function emailNeedsResponse() {
  const res = await fetch(`${API}/v1/workspace/email/summary?limit=50`);
  const body = await res.json();
  return body.threads.find((t) => t.id === "eml_001").needs_response;
}

async function taskExists(id) {
  const res = await fetch(`${API}/v1/workspace/tasks`);
  return (await res.json()).some((t) => t.id === id);
}

async function main() {
  mkdirSync(SHOTS, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (error) => {
    console.log(`  [FAIL] uncaught page error — ${error.message}`);
    failures += 1;
  });

  console.log("\n1. Dashboard renders live data");
  await page.goto(WEB, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".stat__value");
  const stats = await page.locator(".stat__value").allTextContents();
  check("stat tiles populated", stats.length >= 4 && stats.every((s) => s.trim()), stats.join(" / "));
  check("tasks listed", (await page.locator(".list__row").count()) > 0);
  await page.screenshot({ path: `${SHOTS}01-dashboard.png`, fullPage: true });

  console.log("\n2. Baseline workspace state");
  const emailBefore = await emailNeedsResponse();
  const taskBefore = await taskExists("tsk_001");
  check("eml_001 awaits a reply", emailBefore === true);
  check("tsk_001 is open", taskBefore === true);

  console.log("\n3. Ask Atlas — run pauses on the gate");
  await page.goto(`${WEB}/chat`, { waitUntil: "domcontentloaded" });
  await page.fill(".composer__input", "Sort out my morning");
  await page.click(".composer__box .btn--primary");

  await page.waitForSelector(".approval", { timeout: 30_000 });
  const heading = (await page.locator(".approval__head").first().textContent()) ?? "";
  check("approval card appears", heading.includes("approval"), heading.trim());

  const items = page.locator(".approval__item");
  const itemCount = await items.count();
  check("both gated actions listed", itemCount === 2, `${itemCount} shown`);

  const names = (await page.locator(".approval__item-head strong").allTextContents()).map((s) =>
    s.trim(),
  );
  check("send email proposed", names.includes("Send Email"), names.join(", "));
  check("complete task proposed", names.includes("Complete Task"));

  const confirm = page.locator(".approval__confirm .btn");
  check("confirm blocked until every action is decided", await confirm.isDisabled());

  check("nothing has run yet — email", (await emailNeedsResponse()) === true);
  check("nothing has run yet — task", (await taskExists("tsk_001")) === true);
  await page.screenshot({ path: `${SHOTS}02-approval-pending.png`, fullPage: true });

  console.log("\n4. Approve the email, decline the task");
  const emailItem = items.filter({ hasText: "Send Email" });
  const taskItem = items.filter({ hasText: "Complete Task" });
  await emailItem.locator("button", { hasText: "Approve" }).click();
  await taskItem.locator("button", { hasText: "Decline" }).click();

  const badges = (await page.locator(".approval__item .badge").allTextContents()).map((s) =>
    s.trim(),
  );
  check("choices shown before submitting", badges.includes("Will approve") && badges.includes("Will decline"), badges.join(", "));
  check("confirm now enabled", await confirm.isEnabled());
  await page.screenshot({ path: `${SHOTS}03-choices-made.png`, fullPage: true });

  console.log("\n5. Confirm — outcomes must be real");
  await confirm.click();
  await page.waitForSelector(".approval--resolved", { timeout: 30_000 });

  const summary = (await page.locator(".approval--resolved .approval__head").textContent()) ?? "";
  check("UI reports a partial result", /part/i.test(summary), summary.trim());
  check("UI says one was carried out and one was not", /1 carried out, 1 not/i.test(summary), summary.trim());

  const outcomes = (await page.locator(".approval__outcomes li").allTextContents()).map((s) =>
    s.replace(/\s+/g, " ").trim(),
  );
  check("email shown as done", outcomes.some((o) => /^Done\s*Send Email/.test(o)), outcomes.join(" | "));
  check("task shown as declined", outcomes.some((o) => /^Declined\s*Complete Task/.test(o)));

  const emailAfter = await emailNeedsResponse();
  const taskAfter = await taskExists("tsk_001");
  check("APPROVED ACTION HAPPENED (email answered)", emailAfter === false);
  check("DECLINED ACTION DID NOT HAPPEN (task still open)", taskAfter === true);

  const emptyBubbles = await page
    .locator(".msg__bubble")
    .evaluateAll((nodes) => nodes.filter((n) => !n.textContent?.trim()).length);
  check("no empty message bubbles", emptyBubbles === 0, `${emptyBubbles} found`);
  await page.screenshot({ path: `${SHOTS}04-partial-result.png`, fullPage: true });

  console.log("\n6. Activity page reports the run as partial");
  await page.goto(`${WEB}/activity`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".list__row");
  const firstRun = (await page.locator(".list__row").first().textContent()) ?? "";
  check("run listed as Partial", /partial/i.test(firstRun), firstRun.replace(/\s+/g, " ").slice(0, 90));
  await page.screenshot({ path: `${SHOTS}05-activity.png`, fullPage: true });

  console.log("\n7. Responsive layout");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(WEB, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".stat__value");
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  check("no horizontal overflow at 390px", overflow === false);
  await page.screenshot({ path: `${SHOTS}06-mobile.png`, fullPage: true });

  await browser.close();

  console.log(
    failures === 0
      ? "\nAll browser checks passed.\n"
      : `\n${failures} browser check(s) FAILED.\n`,
  );
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error("\ne2e run crashed:", error);
  process.exit(1);
});
