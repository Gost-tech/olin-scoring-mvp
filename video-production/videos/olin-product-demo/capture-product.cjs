const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const outputDir = path.join(__dirname, "assets", "product");
fs.mkdirSync(outputDir, { recursive: true });

const shot = async (page, name) => {
  await page.screenshot({
    path: path.join(outputDir, name),
    fullPage: false,
  });
};

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath:
      "/Users/pc/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-x64/chrome-headless-shell",
  });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
  });
  const page = await context.newPage();

  await page.goto("http://127.0.0.1:8001/demo/", {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.addStyleTag({
    content: `
      header.site-header, footer.site-footer, .page-hero, .button-row,
      .explorer-disclaimer { display:none!important; }
      main { padding:0!important; }
      .section { padding:28px 0!important; min-height:900px; }
      .shell { width:min(1480px, calc(100% - 48px))!important; }
      .pilot-workspace { margin:0!important; }
    `,
  });
  await shot(page, "01-intake.png");

  const consent = page.getByText(
    "Confirmo que el comerciante autorizó el uso de la evidencia crediticia y operativa seleccionada para este piloto sombra.",
    { exact: true },
  );
  await consent.click();
  await shot(page, "02-consent.png");

  await page.getByRole("button", { name: "Simular expediente" }).click();
  await shot(page, "03-evidence.png");

  await page.getByRole("button", { name: "Continuar" }).click();
  await shot(page, "04-recommendation.png");

  await page.getByRole("button", { name: "Continuar" }).click();
  await page.getByRole("button", { name: "Aprobar" }).click();
  await shot(page, "05-partner-outcome.png");

  await page.goto("http://127.0.0.1:8001/analyst-demo/", {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.addStyleTag({
    content: `
      header.site-header, footer.site-footer, .page-hero,
      .explorer-disclaimer { display:none!important; }
      main { padding:0!important; }
      .section { padding:28px 0!important; min-height:900px; }
      .shell { width:min(1520px, calc(100% - 40px))!important; }
      .analyst-console { margin:0!important; }
    `,
  });
  await shot(page, "06-analyst-queue.png");
  await page.getByRole("button", { name: /Taquería San Miguel/ }).click();
  await shot(page, "07-analyst-review.png");
  await page.getByRole("button", { name: "Solicitar evidencia" }).click();
  await shot(page, "08-audit-outcome.png");

  console.log(`Captured ${fs.readdirSync(outputDir).length} product states in ${outputDir}`);
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
