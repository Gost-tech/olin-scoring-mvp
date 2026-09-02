#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const sourcePath = join(root, "index.html");
const outputPath = join(root, "index-en.render.html");
let html = readFileSync(sourcePath, "utf8");

const replacements = [
  ['<html lang="es">', '<html lang="en">'],
  ["DEMOSTRACIÓN REAL DEL PRODUCTO · DATOS SINTÉTICOS", "REAL PRODUCT DEMO · SYNTHETIC DATA"],
  ["Un expediente. Una decisión defendible.", "One case. One defensible decision."],
  ["Vea la evidencia", "See the evidence"],
  ["detrás", "behind"],
  ["de la recomendación.", "the recommendation."],
  ["Olin organiza datos autorizados para el equipo de crédito. La institución conserva la decisión.", "Olin organizes authorized data for the credit team. The institution keeps the final decision."],
  ["PRODUCTO FUNCIONAL", "WORKING PRODUCT"],
  ["ENTORNO SINTÉTICO", "SYNTHETIC ENVIRONMENT"],
  ["SIN MOVIMIENTO DE DINERO", "NO MONEY MOVEMENT"],
  ["01 · Registro + consentimiento", "01 · Case + consent"],
  ["El caso comienza antes del score.", "The case starts before the score."],
  ["Propósito, monto, comercio y autorización quedan ligados al mismo expediente.", "Purpose, amount, business and authorization stay linked to one case."],
  ["CONSENTIMIENTO REGISTRADO", "CONSENT RECORDED"],
  ["02 · Evidencia", "02 · Evidence"],
  ["La fuente y el faltante permanecen visibles.", "Sources and gaps remain visible."],
  ["Olin no convierte datos ausentes o sintéticos en certeza.", "Olin never turns missing or synthetic data into certainty."],
  ["FUENTE + ESTADO + LIMITACIÓN", "SOURCE + STATUS + LIMIT"],
  ["03 · Recomendación", "03 · Recommendation"],
  ["El equipo puede inspeccionar el porqué.", "The team can inspect the why."],
  ["Score, ruta, cobertura, razones y política quedan juntos.", "Score, route, coverage, reasons and policy stay together."],
  ["RAZONES, NO SÓLO UN NÚMERO", "REASONS, NOT JUST A NUMBER"],
  ["04 · Revisión institucional", "04 · Institutional review"],
  ["La decisión final sigue siendo del socio.", "The partner keeps the final decision."],
  ["El analista compara casos, solicita evidencia y registra su decisión por separado.", "The analyst compares cases, requests evidence and records a separate decision."],
  ["Bitácora del caso", "Case audit trail"],
  ["Recomendación y decisión no se confunden.", "Recommendation and decision stay separate."],
  ["La discrepancia también produce evidencia útil para calibrar la política.", "Disagreement also creates evidence to calibrate policy."],
  ["La prueba que falta", "The proof still missing"],
  ["10 casos.<br>4 semanas.<br>Una decisión go / no-go.", "10 cases.<br>4 weeks.<br>One go / no-go decision."],
  ["Medir cobertura, tiempo de revisión, desacuerdo y evidencia faltante antes de integrar o mover dinero.", "Measure coverage, review time, disagreement and missing evidence before integration or money movement."],
  ["SIGUIENTE HITO · PILOTO SOMBRA CON UN SOCIO", "NEXT MILESTONE · ONE PARTNER SHADOW PILOT"],
  ["OLIN · FLUJO DEL PRODUCTO · SYNTHETIC ENVIRONMENT", "OLIN · PRODUCT FLOW · SYNTHETIC ENVIRONMENT"],
];

for (const [source, target] of replacements) {
  if (!html.includes(source)) throw new Error(`Missing source text: ${source}`);
  html = html.replaceAll(source, target);
}

for (const stem of ["01", "02", "03", "04", "06", "08"]) {
  html = html.replace(
    `src="assets/voice/es/vo-${stem}.wav"`,
    `src="assets/voice/en/vo-${stem}.wav"`,
  );
}

writeFileSync(outputPath, html);
console.log(`Generated ${outputPath}`);
