import { chromium } from "playwright";
const WEB = process.env.WEB_URL ?? "http://localhost:4173";

let fails = 0;
const check = (l, c, d="") => { console.log(`  [${c?"PASS":"FAIL"}] ${l}${d?` — ${d}`:""}`); if(!c) fails++; };

// Headed on purpose: headless Chromium exposes no audio input device, so
// getUserMedia fails with NotSupportedError there. This is a local validation
// script, not a CI job.
const browser = await chromium.launch({
  headless: false,
  args: ["--use-fake-ui-for-media-capture", "--use-fake-device-for-media-stream"],
});
const ctx = await browser.newContext();
await ctx.grantPermissions(["microphone"], { origin: WEB });
const page = await ctx.newPage();
page.on("pageerror", e => { console.log("  [FAIL] page error — " + e.message); fails++; });

await page.goto(`${WEB}/capture`, { waitUntil: "domcontentloaded" });
await page.waitForSelector(".recorder__button");
check("recorder control renders", true);

// Assert on the response: Playwright cannot read Blob-backed multipart
// request bodies, so postDataBuffer() is empty even on a valid upload.
const upload = page.waitForResponse(r => r.url().includes("/v1/capture/voice") && r.request().method() === "POST", { timeout: 40000 });
await page.click(".recorder__button");
await page.waitForSelector(".recorder__button--live", { timeout: 20000 });
check("recording state entered", true);
await page.waitForTimeout(2500);
const label = await page.locator(".recorder__label").textContent();
check("timer advances", /0:0[1-9]/.test(label ?? ""), (label??"").trim());

await page.click(".recorder__button");
const res = await upload;
check("upload accepted", res.status() === 200, `HTTP ${res.status()}`);
const body = await res.json();
check("server returned a transcript", !!body.transcript, `${(body.transcript ?? "").length} chars`);
check("server stored claims", (body.claims ?? []).length > 0, `${(body.claims ?? []).length} claims`);

await page.waitForSelector(".capture__transcript", { timeout: 30000 });
const t = await page.locator(".capture__transcript").textContent();
check("transcript rendered back", !!t && t.length > 10);
const claims = await page.locator(".claim__quote").count();
check("claims rendered with quotes", claims > 0, `${claims} quotes`);

await page.screenshot({ path: "e2e/screenshots/voice-capture.png", fullPage: true });
await browser.close();
console.log(fails === 0 ? "\nRecorder OK\n" : `\n${fails} FAILED\n`);
process.exit(fails ? 1 : 0);
