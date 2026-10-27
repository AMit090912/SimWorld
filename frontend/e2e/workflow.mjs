import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const OUT = path.resolve(process.env.E2E_OUT || "e2e/artifacts");
fs.mkdirSync(OUT, { recursive: true });

const failures = [];
const browser = await chromium.launch({ channel: process.env.E2E_CHANNEL || "chrome", headless: true });

try {
  const page = await browser.newPage({ viewport: { width: 1500, height: 960 } });
  const consoleErrors = [];
  const requestFailures = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => {
    if (!request.url().includes("favicon")) requestFailures.push(request.url());
  });

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Launch run");

  for (const [route, selector] of [
    ["/scenarios", "text=Riverside Standard Run"],
    ["/agents", "text=Built-in strategies"],
    ["/runs", "text=Run log"],
    ["/docs", "text=SimWorld in ten minutes"],
  ]) {
    await page.goto(`${BASE}${route}`, { waitUntil: "networkidle" });
    await page.waitForSelector(selector);
  }

  if (process.env.E2E_EXPECT_EMPTY === "1") {
    await page.goto(`${BASE}/runs`, { waitUntil: "networkidle" });
    await page.waitForSelector("text=No runs yet");
  }

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Launch run");
  const health = await page.evaluate(async () => {
    const response = await fetch("/api/health");
    return { status: response.status, body: await response.json() };
  });
  assert.equal(health.status, 200);
  assert.equal(health.body.ok, true);

  await page.getByRole("button", { name: /Launch run/i }).click();
  await page.waitForSelector("text=Open replay", { timeout: 120000 });
  await page.getByRole("link", { name: /Open replay/i }).first().click();
  await page.waitForSelector("text=Action timeline", { timeout: 30000 });
  await page.waitForSelector("text=FINAL EVALUATION");
  await page.waitForSelector("text=CITY STATE");

  const legend = page.getByTestId("map-legend");
  if (await legend.isVisible()) {
    const items = page.getByTestId("map-legend-items");
    assert.equal(await items.isVisible(), true);
    await page.getByRole("button", { name: "Minimize legend" }).click();
    assert.equal(await items.isVisible(), false);
    await page.getByRole("button", { name: "Expand legend" }).click();
    assert.equal(await items.isVisible(), true);
  }

  const runId = new URL(page.url()).pathname.split("/").filter(Boolean).pop();
  const runResponse = await fetch(`${BASE}/api/runs/${runId}`);
  assert.equal(runResponse.status, 200);
  const run = await runResponse.json();
  assert.equal(run.run.status, "finished");
  assert.equal(run.evaluation.packages_delivered, run.evaluation.packages_total);
  assert.ok(run.evaluation.score > 0);
  assert.ok(run.run.steps > 0);

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("text=FINAL EVALUATION");
  await page.screenshot({ path: path.join(OUT, "completed-replay.png"), fullPage: false });

  assert.deepEqual(requestFailures, []);
  assert.deepEqual(consoleErrors, []);

  // The browser must show a recoverable error state when a request fails.
  const errorPage = await browser.newPage({ viewport: { width: 1500, height: 960 } });
  let failOnce = true;
  await errorPage.route("**/api/scenarios", async (route) => {
    if (failOnce) {
      failOnce = false;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await errorPage.goto(`${BASE}/scenarios`, { waitUntil: "domcontentloaded" });
  await errorPage.getByRole("button", { name: "Retry" }).waitFor({ timeout: 15000 });
  await errorPage.getByRole("button", { name: "Retry" }).click();
  await errorPage.waitForSelector("text=Riverside Standard Run", { timeout: 15000 });
  await errorPage.unroute("**/api/scenarios");
  await errorPage.close();

  console.log(JSON.stringify({
    browser: "chrome",
    health,
    run: {
      id: runId,
      status: run.run.status,
      steps: run.run.steps,
      score: run.evaluation.score,
      delivered: run.evaluation.packages_delivered,
      total: run.evaluation.packages_total,
    },
    consoleErrors: [],
    requestFailures: [],
    errorRecovery: "passed",
    screenshots: [path.relative(process.cwd(), path.join(OUT, "completed-replay.png"))],
  }, null, 2));
} catch (error) {
  failures.push(String(error));
  const pages = browser.contexts().flatMap((context) => context.pages());
  const page = pages[0];
  if (page) {
    try {
      await page.screenshot({ path: path.join(OUT, "failure.png"), fullPage: true });
    } catch {
      // The failure screenshot is best effort.
    }
  }
  console.error(JSON.stringify({ ok: false, error: String(error), failures }, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
