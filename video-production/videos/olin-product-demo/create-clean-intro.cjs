const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const root = __dirname;
const browserPath =
  "/Users/pc/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-x64/chrome-headless-shell";
const productImagePath = path.join(root, "assets", "product", "04-recommendation.png");
const productImage = `data:image/png;base64,${fs.readFileSync(productImagePath).toString("base64")}`;

const languages = {
  en: {
    kicker: "ONE CASE · ONE AUDIT TRAIL",
    eyebrow: "REAL PRODUCT DEMO · SYNTHETIC DATA",
    title: "See the evidence<br><em>behind</em> the recommendation.",
    body: "Olin organizes authorized data for the credit team. The institution keeps the final decision.",
    tags: ["WORKING PRODUCT", "SYNTHETIC ENVIRONMENT", "NO MONEY MOVEMENT"],
  },
  es: {
    kicker: "UN EXPEDIENTE · UNA BITÁCORA",
    eyebrow: "DEMOSTRACIÓN REAL DEL PRODUCTO · DATOS SINTÉTICOS",
    title: "Vea la evidencia<br><em>detrás</em> de la recomendación.",
    body: "Olin organiza datos autorizados para el equipo de crédito. La institución conserva la decisión.",
    tags: ["PRODUCTO FUNCIONAL", "ENTORNO SINTÉTICO", "SIN MOVIMIENTO DE DINERO"],
  },
};

const html = (copy) => `<!doctype html>
<html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#f4f6f0;color:#071310;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
body{position:relative;background-image:linear-gradient(rgba(7,19,16,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(7,19,16,.045) 1px,transparent 1px);background-size:58px 58px}
.top{position:absolute;left:70px;right:70px;top:42px;display:flex;justify-content:space-between;align-items:center}.logo{font-size:35px;font-weight:950;letter-spacing:-.065em}.logo i{display:inline-block;width:15px;height:15px;background:#c9ff52;border-radius:50%;margin-left:7px}.mode{padding:10px 16px;border-radius:999px;background:#071310;color:#c9ff52;font-size:13px;letter-spacing:.11em;font-weight:850}
.layout{position:absolute;inset:120px 70px 82px;display:grid;grid-template-columns:700px 1fr;gap:48px;align-items:center}.eyebrow{font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:#0c5a45;font-weight:900;margin-bottom:24px}h1{font-size:78px;line-height:.95;letter-spacing:-.064em;margin:0}h1 em{position:relative;font-style:normal;z-index:1}h1 em:after{content:"";position:absolute;left:-4px;right:-5px;bottom:5px;height:18px;background:#c9ff52;z-index:-1}p{font-size:24px;line-height:1.4;color:#50655c;margin:28px 0 0;max-width:650px}.tags{display:flex;gap:10px;margin-top:34px}.tags span{padding:11px 14px;border-radius:999px;background:#071310;color:#fff;font-size:12px;font-weight:850}.tags span:last-child{background:#c9ff52;color:#071310}
.window{height:760px;border:9px solid #071310;border-radius:25px;overflow:hidden;background:#071310;box-shadow:0 32px 80px rgba(7,19,16,.22)}.bar{height:34px;background:#071310;padding:12px 0 0 16px}.bar i{display:inline-block;width:9px;height:9px;border-radius:50%;background:#c9ff52;margin-right:7px}.window img{display:block;width:100%;height:calc(100% - 34px);object-fit:contain;object-position:center;background:#f4f6f0}
.foot{position:absolute;left:70px;right:70px;bottom:28px;display:flex;justify-content:space-between;font-size:13px;color:#52675e;font-weight:800;letter-spacing:.08em}
</style></head><body>
<div class="top"><div class="logo">OLIN<i></i></div><div class="mode">${copy.eyebrow}</div></div>
<div class="layout"><div><div class="eyebrow">${copy.kicker}</div><h1>${copy.title}</h1><p>${copy.body}</p><div class="tags">${copy.tags.map((tag) => `<span>${tag}</span>`).join("")}</div></div><div class="window"><div class="bar"><i></i><i></i><i></i></div><img src="${productImage}"></div></div>
<div class="foot"><span>OLIN · PRODUCT DEMO</span><span>olin-credit.olin-mx.workers.dev</span></div>
</body></html>`;

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: browserPath });
  for (const [language, copy] of Object.entries(languages)) {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await page.setContent(html(copy), { waitUntil: "load" });
    await page.locator(".window img").waitFor();
    await page.screenshot({ path: path.join(root, "renders", `clean-intro-${language}.png`) });
    await page.close();
  }
  await browser.close();
  console.log("Clean English and Spanish intro frames created.");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
