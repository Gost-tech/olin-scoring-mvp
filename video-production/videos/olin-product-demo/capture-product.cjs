const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const outputDir = path.join(__dirname, "capture", "assets");
fs.mkdirSync(outputDir, { recursive: true });

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath:
      "/Users/pc/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-x64/chrome-headless-shell",
  });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:8080/", {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  await page.locator("body").waitFor();
  await page.addStyleTag({
    content: ".topbar{position:static!important}.toast{display:none!important}",
  });

  await page.screenshot({
    path: path.join(outputDir, "analyst-dashboard.png"),
    fullPage: true,
  });
  await page.screenshot({
    path: path.join(outputDir, "analyst-dashboard-top.png"),
    fullPage: false,
  });

  const caseCaptures = [
    ["Jugueria La Esquina", "case-decline.png"],
    ["Roberto", "case-committee.png"],
    ["Maria", "case-approved.png"],
  ];
  for (const [merchant, fileName] of caseCaptures) {
    const card = page.locator("article.card").filter({ hasText: merchant }).first();
    await card.screenshot({ path: path.join(outputDir, fileName) });
  }

  const buttons = await page.locator("button").allTextContents();
  const links = await page.locator("a").allTextContents();
  const body = (await page.locator("body").innerText()).slice(0, 16_000);
  console.log(JSON.stringify({ title: await page.title(), buttons, links, body }, null, 2));

  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
