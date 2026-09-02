#!/usr/bin/env node

import { mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const HEYGEN_TTS = join(
  ROOT,
  "../../hyperframes-source/skills/media-use/audio/scripts/heygen-tts.mjs",
);

const languages = {
  en: {
    language: "en",
    speed: "0.98",
    voice: "02880d1c6fd94b7799d91135581ed810", // Blanka - Lifelike
    scripts: [
      "A small business asks for funding. Olin turns authorized data into one decision-ready credit file. This case is synthetic.",
      "The owner explains what the money is for. Before any data is checked, Olin records her consent, the channel, and the exact text.",
      "With permission, Olin brings together identity, credit history, bank cash flow, point-of-sale data, and operating evidence. Missing signals stay visible.",
      "The engine applies a versioned policy. It returns a recommendation, a confidence level, and clear reasons. It never promises approval.",
      "The case enters the credit team's queue. The analyst reviews repayment capacity, stress, identity, and every signal behind the recommendation.",
      "Olin recommends. The institution decides. Its final decision and rationale are recorded separately.",
      "After the partner completes its controls and contract, it can authorize the transfer. This is a simulation. Olin does not move the money.",
      "The outcome stays connected to the original evidence and decision. That creates an auditable learning loop. The next step is a ten-case parallel pilot.",
    ],
  },
  es: {
    language: "es",
    speed: "0.97",
    voice: "1eca26cb214c4f66976339251282b341", // Camila Vega - Friendly
    scripts: [
      "Un negocio pide financiamiento. Olin convierte datos autorizados en un expediente listo para decidir. Caso sintético.",
      "La dueña explica para qué necesita el dinero. Antes de consultar cualquier dato, Olin registra su consentimiento, el canal y el texto exacto.",
      "Con autorización, Olin reúne identidad, crédito, flujo bancario, ventas y evidencia operativa. Los datos faltantes siguen visibles.",
      "El motor entrega una recomendación, su confianza y razones claras. La institución conserva la decisión final.",
      "El caso entra a la fila de crédito. El analista revisa capacidad de pago, estrés, identidad y cada señal.",
      "Olin recomienda. La institución decide. Su decisión final y la justificación se registran por separado.",
      "Después de completar sus controles y el contrato, el socio puede autorizar el depósito. Esta escena es una simulación. Olin no mueve el dinero.",
      "El resultado queda conectado con la evidencia original, creando un aprendizaje auditable. El siguiente paso es un piloto paralelo de diez casos.",
    ],
  },
};

const selectors = new Set(process.argv.slice(2));

for (const [code, config] of Object.entries(languages)) {
  const outputDir = join(ROOT, "assets", "voice", code);
  mkdirSync(outputDir, { recursive: true });

  for (let index = 0; index < config.scripts.length; index += 1) {
    const stem = `vo-${String(index + 1).padStart(2, "0")}`;
    if (
      selectors.size > 0 &&
      !selectors.has(code) &&
      !selectors.has(`${code}:${stem}`)
    ) {
      continue;
    }
    const wav = join(outputDir, `${stem}.wav`);
    const words = join(outputDir, `${stem}.words.json`);

    console.log(`\n[${code.toUpperCase()}] ${stem}`);
    const result = spawnSync(
      process.execPath,
      [
        HEYGEN_TTS,
        config.scripts[index],
        "-o",
        wav,
        "--words",
        words,
        "--voice",
        config.voice,
        "--speed",
        config.speed,
        "--lang",
        config.language,
      ],
      { cwd: ROOT, stdio: "inherit" },
    );

    if (result.status !== 0) {
      process.exit(result.status ?? 1);
    }
  }
}

console.log("\nHeyGen narration generated for English and Spanish.");
