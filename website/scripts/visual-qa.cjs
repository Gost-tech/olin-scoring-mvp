const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const outputDir = path.join(__dirname, "..", "qa-artifacts");
fs.mkdirSync(outputDir, { recursive: true });
const baseUrl = process.env.OLIN_VISUAL_QA_URL || "http://127.0.0.1:8001";
const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const browserLaunchOptions = () => {
  const configured = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  if (configured) return { headless: true, executablePath: configured };
  if (process.platform === "darwin" && fs.existsSync(macChrome)) {
    return { headless: true, executablePath: macChrome };
  }
  return { headless: true };
};

const waitForPreview = async (timeoutMs = 30_000) => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(baseUrl);
      if (response.ok) return;
    } catch {
      // The preview process may still be binding its socket.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Astro preview did not become ready at ${baseUrl}`);
};

(async () => {
  const preview = process.env.OLIN_VISUAL_QA_URL
    ? null
    : spawn(
        process.platform === "win32" ? "pnpm.cmd" : "pnpm",
        ["exec", "astro", "preview", "--host", "127.0.0.1", "--port", "8001"],
        { cwd: path.join(__dirname, ".."), stdio: ["ignore", "pipe", "pipe"] },
      );
  let previewError = "";
  preview?.stderr.on("data", (chunk) => { previewError += chunk.toString(); });
  preview?.on("exit", (code) => {
    if (code && code !== 0) previewError += `\nAstro preview exited with code ${code}.`;
  });

  let browser;
  try {
    await waitForPreview();
    browser = await chromium.launch(browserLaunchOptions());
    const failures = [];

    for (const route of [
      { name: "homepage", path: "/" },
      { name: "waitlist", path: "/lista-espera/" },
    ]) {
      for (const viewport of [
        { name: "desktop", width: 1440, height: 1000 },
        { name: "mobile", width: 390, height: 844 },
      ]) {
        const page = await browser.newPage({
          viewport: { width: viewport.width, height: viewport.height },
          deviceScaleFactor: 1,
          reducedMotion: "reduce",
        });
        page.on("pageerror", (error) => failures.push(`${route.name}/${viewport.name}: ${error.message}`));
        page.on("console", (message) => {
          if (message.type() === "error") failures.push(`${route.name}/${viewport.name}: ${message.text()}`);
        });
        await page.route("**/api/v1/waitlist", (request) => request.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: { applications_received: 0 } }),
        }));
        const response = await page.goto(`${baseUrl}${route.path}`, {
          waitUntil: "networkidle",
          timeout: 30_000,
        });
        if (!response?.ok()) throw new Error(`${route.path} returned HTTP ${response?.status()}`);
        await page.screenshot({
          path: path.join(outputDir, `${route.name}-${viewport.name}.png`),
          fullPage: true,
        });
        const overflow = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        if (overflow.scrollWidth > overflow.clientWidth) {
          throw new Error(`${route.name} ${viewport.name} horizontal overflow: ${JSON.stringify(overflow)}`);
        }
        await page.close();
      }
    }

    if (failures.length) throw new Error(`Browser console failures:\n${failures.join("\n")}`);
    console.log(`Visual QA passed for 4 route/viewport combinations; artifacts: ${outputDir}`);
  } finally {
    await browser?.close();
    if (preview && !preview.killed) preview.kill("SIGTERM");
    if (previewError) process.stderr.write(previewError);
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
