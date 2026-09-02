import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = "/Users/pc/Downloads/olin_scoring_mvp_1";
const OUT = path.join(ROOT, "output/elektra-2026");
const RENDER = path.join(OUT, "rendered");
const HERO = path.join(OUT, "assets/olin-evidence-merchant-hero.png");
const FINAL = path.join(OUT, "Olin_Elektra_Implementation_Deck_2026-09-02.pptx");

const W = 1280, H = 720, M = 68;
const C = {
  ink: "#071310", forest: "#0C5A45", emerald: "#16856B", lime: "#C9FF52",
  paper: "#F4F6F0", white: "#FFFFFF", muted: "#65736C", rule: "#CFD8D2",
  mint: "#CDE9DD", amber: "#E4B84F", coral: "#C7433F", pale: "#E8EEE9",
  blue: "#8EC5D6",
};
const FONT = "Arial";

async function imageBytes(file) {
  const b = await fs.readFile(file);
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
}
async function writeBlob(file, blob) {
  await fs.writeFile(file, new Uint8Array(await blob.arrayBuffer()));
}
function rect(s, x, y, w, h, fill, radius = 0, stroke = "none", sw = 0) {
  return s.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: stroke, width: sw },
    ...(radius ? { borderRadius: radius } : {}),
  });
}
function txt(s, value, x, y, w, h, size = 20, color = C.ink, bold = false, align = "left", opts = {}) {
  const box = s.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  box.text = value;
  box.text.style = {
    typeface: FONT, fontSize: size, color, bold, alignment: align,
    verticalAlignment: opts.vAlign ?? "top", autoFit: "shrinkText",
    lineSpacing: opts.lineSpacing ?? 0.98,
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return box;
}
function dot(s, x, y, r, fill) {
  return s.shapes.add({ geometry: "ellipse", position: { left: x-r, top: y-r, width: r*2, height: r*2 }, fill, line: { style: "solid", fill: "none", width: 0 } });
}
function rule(s, x, y, w, color = C.rule, h = 2) { return rect(s, x, y, w, h, color); }
function pill(s, value, x, y, w, fill = C.pale, color = C.forest) {
  rect(s, x, y, w, 30, fill, 15);
  txt(s, value, x, y+1, w, 27, 12, color, true, "center", { vAlign: "middle" });
}
function chrome(s, section, n, dark = false) {
  txt(s, section.toUpperCase(), M, 30, 500, 22, 11, dark ? C.mint : C.forest, true);
  txt(s, "olin.", 1112, 24, 96, 28, 22, dark ? C.white : C.ink, true, "right");
  txt(s, String(n).padStart(2, "0"), 1184, 675, 24, 16, 10, dark ? C.muted : C.muted, true, "right");
}
function title(s, value, dark = false, y = 76, size = 44, w = 1144) {
  return txt(s, value, M, y, w, 116, size, dark ? C.white : C.ink, true, "left", { lineSpacing: 0.9 });
}
function notes(s, body, sources = []) {
  const block = sources.length ? `\n\n[Sources]\n${sources.map(v => `- ${v}`).join("\n")}` : "\n\n[Sources]\n- Olin internal product architecture and verified local test results, 2 September 2026.";
  s.speakerNotes.textFrame.setText(body + block);
}
function arrow(s, x1, y, x2, color = C.forest) {
  rule(s, x1, y, x2-x1-14, color, 3);
  s.shapes.add({ geometry: "triangle", position: { left: x2-18, top: y-7, width: 14, height: 16 }, fill: color, line: { style: "solid", fill: "none", width: 0 }, rotation: 90 });
}
function node(s, x, y, w, h, heading, body, fill = C.white, accent = C.forest, dark = false) {
  rect(s, x, y, w, h, fill, 22, dark ? "#2D4A40" : C.rule, 1);
  rule(s, x+18, y+18, 50, accent, 4);
  txt(s, heading, x+18, y+36, w-36, 30, 18, dark ? C.white : C.ink, true);
  txt(s, body, x+18, y+74, w-36, h-90, 14, dark ? C.mint : C.muted, false);
}

const p = Presentation.create({ slideSize: { width: W, height: H } });
const hero = await imageBytes(HERO);

// 1
{
  const s = p.slides.add(); s.background.fill = C.ink;
  s.images.add({ blob: hero, contentType: "image/png", alt: "Mexican microbusiness owner with subtle evidence-route lines", fit: "cover", position: { left: 0, top: 0, width: W, height: H } });
  rect(s, 0, 0, 720, H, "linear(0deg, #071310 0%, #071310/96 76%, #071310/0 100%)");
  pill(s, "TECHNICAL EVALUATION", M, 52, 202, C.lime, C.ink);
  txt(s, "olin.", M, 108, 160, 40, 28, C.white, true);
  txt(s, "More complete evidence.\nBanco Azteca keeps the decision.", M, 184, 640, 160, 50, C.white, true, "left", { lineSpacing: 0.87 });
  txt(s, "Implementation proposal for an auditable SME evidence and capacity layer.", M, 380, 550, 70, 22, C.mint, false);
  rule(s, M, 500, 92, C.lime, 4);
  txt(s, "Elektra / Banco Azteca · September 2026", M, 530, 440, 28, 15, C.white, true);
  txt(s, "Controlled shadow evaluation · no automated lending decision", M, 572, 520, 26, 14, "#B6C6BE", false);
  notes(s, "Open with the decision boundary. Olin is not replacing Banco Azteca's model or policy.", ["Original Olin hero asset generated for this deck; no third-party visual source."]);
}

// 2
{
  const s = p.slides.add(); s.background.fill = C.paper; chrome(s, "The Elektra question", 2);
  title(s, "The opportunity is not another score.\nIt is a better evidence path.");
  txt(s, "2,544", M, 242, 250, 72, 58, C.forest, true);
  txt(s, "Banco Azteca contact points", M, 318, 250, 46, 17, C.ink, true);
  txt(s, "5.3%", 358, 242, 220, 72, 58, C.emerald, true);
  txt(s, "delinquency ratio at Jun-26", 358, 318, 248, 46, 17, C.ink, true);
  txt(s, "70%", 650, 242, 180, 72, 58, C.amber, true);
  txt(s, "consumer share of gross portfolio", 650, 318, 260, 54, 17, C.ink, true);
  rect(s, 936, 212, 276, 282, C.ink, 26);
  txt(s, "The implication", 970, 244, 208, 30, 18, C.lime, true);
  txt(s, "Inclusion matters.\nSo do evidence quality, policy control and monitoring.", 970, 302, 208, 126, 23, C.white, true, "left", { lineSpacing: 1.0 });
  txt(s, "Olin should improve the file—not weaken the gate.", M, 500, 820, 50, 25, C.ink, true);
  notes(s, "Use these figures only as context for the control standard, not as a claim that Olin will reduce delinquency.", ["https://www.grupoelektra.com.mx/api/pdfEkt/4259"]);
}

// 3
{
  const s = p.slides.add(); s.background.fill = C.ink; chrome(s, "Positioning", 3, true);
  title(s, "Banco Azteca already owns credit risk.\nOlin closes the evidence gap.", true);
  node(s, M, 240, 310, 250, "Banco Azteca", "KYC · bureau · credit policy · official decision · disbursement · collections", "#10251E", C.lime, true);
  arrow(s, 396, 365, 486, C.lime);
  node(s, 500, 212, 310, 306, "Olin", "Evidence Passport\nCapacity scenarios\nNext-best evidence\nReason codes\nAudit package", C.forest, C.lime, true);
  arrow(s, 826, 365, 916, C.lime);
  node(s, 930, 240, 282, 250, "Bank outcome", "Decision and override reason return to Olin; repayment outcomes enable later validation.", "#10251E", C.mint, true);
  pill(s, "NO POLICY REPLACEMENT", 494, 560, 220, "#173B30", C.lime);
  txt(s, "Banco Azteca's risk materials already describe internal models, backtesting and independent oversight.", M, 620, 1060, 34, 16, "#B6C6BE", false);
  notes(s, "Make the integration boundary explicit. The bank's existing model-risk process is a reason to position Olin as evidence orchestration.", ["https://www.grupoelektra.com.mx/api/pdfEkt/4264"]);
}

// 4
{
  const s = p.slides.add(); s.background.fill = C.white; chrome(s, "Product flow", 4);
  title(s, "One reconstructable evidence journey.");
  const stages = [
    ["01", "Intake", "Partner case reference\nand consent links"],
    ["02", "Evidence Passport", "Source · time · version\nand quality"],
    ["03", "Capacity", "Cash-flow normalization\nand stress scenarios"],
    ["04", "Recommendation", "Amount/term route,\nreasons and gaps"],
    ["05", "Bank decision", "Approve · decline · refer\nor override"],
  ];
  stages.forEach(([n,h,b], i) => {
    const x = 52 + i*246;
    pill(s, n, x, 224, 42, i === 2 ? C.lime : C.pale, C.forest);
    node(s, x, 278, 216, 210, h, b, i === 2 ? C.forest : C.paper, i === 2 ? C.lime : C.forest, i === 2);
    if (i < 4) arrow(s, x+218, 382, x+244, C.rule);
  });
  rect(s, M, 538, 1144, 72, C.ink, 18);
  txt(s, "Every output carries", 98, 558, 202, 28, 14, C.mint, true);
  txt(s, "case · evidence snapshot · engine version · policy version · reason codes · actor history", 306, 550, 840, 40, 18, C.white, true);
  notes(s, "Walk left to right. Olin freezes the evidence snapshot before recommendation and returns a package, not an official approval.");
}

// 5
{
  const s = p.slides.add(); s.background.fill = C.paper; chrome(s, "Evidence governance", 5);
  title(s, "More layers do not mean more score.");
  const rows = [
    ["A", "Capacity candidate", "Bank · POS · suppliers · fiscal · receivables", "Shadow capacity review", C.forest],
    ["B", "Corroboration", "Tenure · DENUE · Places · operating evidence", "Verify activity / permanence", C.emerald],
    ["C", "Context / stress", "Peers · footfall · weather · inflation · night lights", "Portfolio context only", C.amber],
    ["D", "Research only", "Social · sentiment · response time · psychometrics", "Offline validation only", C.coral],
  ];
  rows.forEach(([n,h,e,u,color], i) => {
    const y = 214+i*96;
    dot(s, 96, y+35, 24, color);
    txt(s, n, 76, y+21, 40, 28, 15, i===3?C.white:C.ink, true, "center", {vAlign:"middle"});
    txt(s, h, 142, y+4, 256, 34, 20, C.ink, true);
    txt(s, e, 414, y+4, 480, 34, 16, C.muted, false);
    pill(s, u, 938, y+5, 236, i===3?"#F3DDDA":C.pale, i===3?C.coral:C.forest);
    rule(s, 142, y+70, 1032, C.rule, 1);
  });
  txt(s, "Invariant: no alternative signal may auto-approve, auto-decline or move money.", M, 622, 1060, 32, 19, C.ink, true);
  notes(s, "This is the implemented permitted-use contract. Missing optional evidence is neutral and routes to a next-best evidence path.");
}

// 6
{
  const s = p.slides.add(); s.background.fill = C.ink; chrome(s, "Missing documents", 6, true);
  title(s, "When one document is missing,\nOlin proposes another evidence route.", true);
  txt(s, "PRIMARY PATH", M, 212, 180, 24, 12, C.mint, true);
  rect(s, M, 250, 280, 96, "#10251E", 20, "#2B4A3E", 1);
  txt(s, "Bank cash-flow feed", 94, 276, 228, 34, 20, C.white, true);
  arrow(s, 366, 298, 448, C.lime);
  txt(s, "IF UNAVAILABLE", 458, 212, 180, 24, 12, C.mint, true);
  const routes = ["POS settlements", "Fiscal evidence", "Supplier purchases", "Receivables", "Observed cash route"];
  routes.forEach((v,i) => {
    const x = 446 + (i%3)*250, y = 250 + Math.floor(i/3)*116;
    rect(s, x, y, 220, 88, i===4?"#173B30":"#10251E", 18, i===4?C.lime:"#2B4A3E", i===4?2:1);
    txt(s, v, x+18, y+24, 184, 36, 17, C.white, true, "center", {vAlign:"middle"});
  });
  rect(s, M, 510, 1144, 92, C.white, 20);
  txt(s, "If no route supports capacity", 98, 532, 310, 30, 18, C.coral, true);
  txt(s, "Return “not yet supportable,” explain the missing evidence, and preserve a future evidence-building path.", 414, 526, 754, 52, 18, C.ink, true);
  notes(s, "The observed cash route needs multiple independent origins and conservative manual review. It is not a shortcut around KYC or bureau authorization.", ["https://www.bancoazteca.com.mx/content/dam/azteca/docs/producto/prestamos/prestamos-personales/240905/tyc-mi-negocio-azteca.pdf"]);
}

// 7
{
  const s = p.slides.add(); s.background.fill = C.white; chrome(s, "Business comparison", 7);
  title(s, "Compare the market—never rank the borrower.");
  rect(s, M, 214, 516, 350, C.paper, 26);
  txt(s, "Local peer cohort", 98, 244, 240, 34, 20, C.ink, true);
  const peers = [[156,342],[232,304],[306,382],[380,322],[444,410],[500,286],[286,458]];
  peers.forEach(([x,y],i)=>dot(s,x,y, i===0?12:8, i===0?C.lime:(i%2?C.forest:C.emerald)));
  txt(s, "Target", 130, 366, 80, 24, 12, C.forest, true);
  txt(s, "SCIAN/category · radius · size band when available", 98, 500, 430, 34, 15, C.muted, false);
  rect(s, 636, 214, 576, 350, C.ink, 26);
  const metrics = [["≥5", "minimum cohort"], ["350 m", "median distance"], ["%", "size-band coverage"], ["Δ", "cohort change"]];
  metrics.forEach(([a,b],i)=>{
    const x=674+(i%2)*254, y=256+Math.floor(i/2)*126;
    txt(s,a,x,y,120,54,38,i===0?C.lime:C.mint,true);
    txt(s,b,x,y+58,190,34,14,C.white,true);
  });
  pill(s, "MARKET CONTEXT ONLY", 674, 500, 224, "#173B30", C.lime);
  txt(s, "No peer names · no borrower rank · small cells suppressed", 904, 499, 266, 38, 14, "#B6C6BE", false);
  notes(s, "The local implementation now returns only aggregate peer metrics. DENUE is a directory, not capacity evidence.", ["https://www.inegi.org.mx/servicios/api_denue.html"]);
}

// 8
{
  const s = p.slides.add(); s.background.fill = C.paper; chrome(s, "Intelligence roadmap", 8);
  title(s, "The “crazy stats” belong behind explicit gates.");
  const cols = [
    ["AVAILABLE", "DENUE\nGoogle Place reference\nOpen-Meteo context", C.forest],
    ["PROCURE + VALIDATE", "Licensed footfall\nMexico coverage\nPurpose + retention", C.amber],
    ["OFFLINE RESEARCH", "VIIRS / Sentinel\nSocial presence\nSentiment / behavior", C.coral],
  ];
  cols.forEach(([h,b,color],i)=>{
    const x=M+i*382;
    pill(s,h,x,220,190,i===0?C.mint:(i===1?"#F3E8CB":"#F3DDDA"),i===0?C.forest:color);
    node(s,x,270,344,250,h,b,C.white,color,false);
  });
  txt(s, "Why the gates?", M, 556, 170, 28, 16, C.ink, true);
  txt(s, "Google restricts stored Places content; VIIRS is ~500 m; weather is modeled at kilometre scale; social ownership and lawful purpose require official APIs and controls.", 240, 548, 970, 56, 16, C.muted, false);
  notes(s, "Do not let novelty outrun validity. Show the roadmap as provider capability, not a claim that these features predict default.", [
    "https://developers.google.com/maps/documentation/places/web-service/policies",
    "https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places",
    "https://gis.earthdata.nasa.gov/portal/home/item.html?id=12b97384e1aa435eb2c0853df257b2fe",
    "https://open-meteo.com/en/docs/historical-weather-api",
    "https://docs.foursquare.com/data-products/docs/places-pro-and-premium"
  ]);
}

// 9
{
  const s = p.slides.add(); s.background.fill = C.ink; chrome(s, "Integration architecture", 9, true);
  title(s, "One narrow boundary between the bank and Olin.", true);
  const stages = [
    ["BANK CHANNEL", "Case · KYC · consent · bureau", "#10251E"],
    ["INTAKE GATEWAY", "Auth · tenant · schema · idempotency", C.forest],
    ["EVIDENCE LAYER", "Adapters · provenance · quality · permitted use", "#10251E"],
    ["CAPACITY + POLICY", "Stress · gaps · reasons · recommendation", C.forest],
    ["BANK OUTCOME", "Decision · override · repayment", "#10251E"],
  ];
  stages.forEach(([h,b,fill],i)=>{
    const x=36+i*250;
    node(s,x,260,220,220,h,b,fill,i%2?C.lime:C.mint,true);
    if(i<4) arrow(s,x+222,368,x+248,C.lime);
  });
  rect(s, M, 534, 1144, 74, "#173B30", 18);
  txt(s, "Transport", 98, 554, 108, 26, 13, C.mint, true);
  txt(s, "TLS · signed webhooks · short-lived sessions · provider timeouts · replay protection", 218, 546, 820, 38, 17, C.white, true);
  pill(s, "NO MONEY MOVEMENT", 1038, 552, 148, "#2B4A3E", C.lime);
  notes(s, "This is the target evaluation architecture. Production credentials, bank certificates and a bank-approved cloud account remain dependencies.");
}

// 10
{
  const s = p.slides.add(); s.background.fill = C.white; chrome(s, "Implementation plan", 10);
  title(s, "Seven days to a controlled technical evaluation.");
  const days = [
    ["1", "Freeze", "Scope · owners · data dictionary"], ["2", "Map", "Bank payloads to contracts"],
    ["3", "Secure", "Environment · TLS · secrets · audit"], ["4", "Break", "Replay · outage · withdrawal tests"],
    ["5", "Reconcile", "Historical sample and reasons"], ["6", "UAT", "Analyst workflow and timing"],
    ["7", "Decide", "Go/no-go for 10-case shadow"],
  ];
  days.forEach(([n,h,b],i)=>{
    const x=47+i*175, y=230+(i%2)*88;
    dot(s,x+22,y+22,22,i===6?C.lime:C.forest);
    txt(s,n,x+2,y+7,40,28,14,i===6?C.ink:C.white,true,"center",{vAlign:"middle"});
    txt(s,h,x,y+58,150,28,17,C.ink,true);
    txt(s,b,x,y+90,150,60,13,C.muted,false);
  });
  rule(s, 70, 278, 1100, C.rule, 3);
  rect(s, M, 516, 1144, 94, C.ink, 20);
  txt(s, "Day-7 deliverable", 98, 540, 180, 26, 14, C.lime, true);
  txt(s, "A jointly signed technical-evaluation decision—never a claim that Olin is already production-ready.", 290, 530, 868, 50, 19, C.white, true);
  notes(s, "The week ends with an evaluation gate, not production deployment. Historical replay may precede the 10-case current shadow workflow.");
}

// 11
{
  const s = p.slides.add(); s.background.fill = C.paper; chrome(s, "Pilot design", 11);
  title(s, "Ten cases prove workflow value—not model performance.");
  const kpis = [["minutes", "analyst time"], ["%", "missing-document resolution"], ["%", "recommendation agreement"], ["reasons", "override quality"], ["%", "audit completeness"]];
  kpis.forEach(([a,b],i)=>{
    const x=M+i*226;
    txt(s,a,x,244,190,52,32,i===0?C.forest:C.emerald,true);
    txt(s,b,x,302,190,44,15,C.ink,true);
  });
  rect(s, M, 386, 1144, 170, C.white, 24, C.rule, 1);
  txt(s, "What 10 cases cannot prove", 98, 416, 330, 34, 19, C.coral, true);
  txt(s, "default prediction · calibration · fairness · portfolio loss impact · automated policy eligibility", 98, 466, 1030, 34, 20, C.ink, true);
  txt(s, "Those require a much larger labeled cohort with mature repayment outcomes and bank model-risk review.", 98, 510, 1000, 28, 15, C.muted, false);
  notes(s, "Set expectations before the pilot. The value hypothesis is workflow and evidence completeness; predictive claims come only after outcome validation.");
}

// 12
{
  const s = p.slides.add(); s.background.fill = C.ink; chrome(s, "Control plane", 12, true);
  title(s, "Six owners. One shared go/no-go gate.", true);
  const owners = [
    ["Credit risk", "policy + stop conditions"], ["Model risk", "validation + permitted use"],
    ["Privacy / legal", "purpose + consent + retention"], ["Security", "access + incidents + vendors"],
    ["Engineering", "integration + reliability"], ["Operations / UAT", "exceptions + analyst acceptance"],
  ];
  owners.forEach(([h,b],i)=>{
    const x=M+(i%3)*382, y=222+Math.floor(i/3)*150;
    node(s,x,y,344,118,h,b,"#10251E",i===0?C.lime:C.mint,true);
  });
  pill(s, "ALL REQUIRED", M, 542, 144, C.lime, C.ink);
  txt(s, "No single founder, engineer or vendor can waive a bank control domain.", 232, 536, 920, 38, 20, C.white, true);
  notes(s, "Use named individuals in the implementation workbook. External approvals are evidence, not a checkbox inside Olin.");
}

// 13
{
  const s = p.slides.add(); s.background.fill = C.white; chrome(s, "Technical reality", 13);
  title(s, "The workflow is tested.\nThe backend still needs decomposition.");
  rect(s, M, 224, 520, 314, C.paper, 26);
  pill(s, "VERIFIED NOW", 98, 250, 146, C.mint, C.forest);
  txt(s, "162", 98, 300, 170, 66, 54, C.forest, true);
  txt(s, "backend tests passing", 98, 368, 260, 36, 17, C.ink, true);
  txt(s, "Site build · 338 static checks · visual QA", 98, 424, 410, 48, 16, C.muted, false);
  txt(s, "Evidence governance and aggregate peer benchmark added", 98, 486, 410, 34, 15, C.ink, true);
  rect(s, 636, 224, 576, 314, C.ink, 26);
  pill(s, "TECH DEBT", 670, 250, 120, "#3A2826", "#F0A29C");
  txt(s, "C", 670, 300, 110, 66, 54, C.coral, true);
  txt(s, "backend code-quality grade", 670, 368, 280, 36, 17, C.white, true);
  txt(s, "server.py ≈ 4.1k lines\nstore.py ≈ 1.46k lines\nlegacy decision engine remains coupled", 670, 424, 470, 96, 16, C.mint, false);
  txt(s, "Bank-ready next step: modular services, explicit migrations, contract tests and reproducible clean checkout.", M, 582, 1100, 36, 18, C.ink, true);
  notes(s, "Be direct. Passing tests do not erase maintainability risk. The quality grade comes from the deterministic code-review skill and is a prioritization signal, not a certification.");
}

// 14
{
  const s = p.slides.add(); s.background.fill = C.ink; chrome(s, "Decision requested", 14, true);
  title(s, "Approve the evaluation boundary—\nthen give us the mapping owners.", true, 86, 46, 820);
  rect(s, M, 248, 702, 260, "#10251E", 26, "#2B4A3E", 1);
  txt(s, "Banco Azteca provides", 98, 278, 280, 32, 19, C.lime, true);
  const asks = ["data dictionary + sample payloads", "credit / model-risk / privacy / security owners", "historical sample + decision/outcome fields", "approved environment and integration route"];
  asks.forEach((v,i)=>{dot(s,108,340+i*40,5,C.mint);txt(s,v,126,327+i*40,580,28,15,C.white,i===0,"left",{vAlign:"middle"});});
  rect(s, 814, 248, 398, 260, C.forest, 26);
  txt(s, "Olin returns", 848, 278, 230, 32, 19, C.lime, true);
  txt(s, "A reproducible evidence package, capacity scenarios, missing-evidence routes, reason codes and an evaluation report.", 848, 340, 316, 126, 21, C.white, true);
  pill(s, "NO FUNDS · NO AUTO-DECISION", M, 558, 244, "#173B30", C.lime);
  txt(s, "Next meeting output: signed technical-evaluation charter and Day-1 working session.", 340, 552, 820, 40, 18, C.white, true);
  notes(s, "Close on a concrete decision: accept the boundary and name the owners. Do not ask the room to approve production lending.");
}

await fs.mkdir(RENDER, { recursive: true });
for (const [i, s] of p.slides.items.entries()) {
  const stem = `slide-${String(i+1).padStart(2,"0")}`;
  await writeBlob(path.join(RENDER, `${stem}.png`), await p.export({ slide: s, format: "png", scale: 1 }));
  const layout = await s.export({ format: "layout" });
  await fs.writeFile(path.join(RENDER, `${stem}.layout.json`), await layout.text());
}
await writeBlob(path.join(OUT, "Olin_Elektra_Implementation_Deck_montage.webp"), await p.export({ format: "webp", montage: true, scale: 1 }));
const pptx = await PresentationFile.exportPptx(p);
await pptx.save(FINAL);
console.log(JSON.stringify({ slides: p.slides.items.length, final: FINAL, rendered: RENDER }, null, 2));
