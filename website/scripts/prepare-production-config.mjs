import { access, writeFile, copyFile } from "node:fs/promises";
import { constants } from "node:fs";

const target = new URL("../public/config.js", import.meta.url);
const template = new URL("../public/config.production.example.js", import.meta.url);

try {
  await access(target, constants.F_OK);
  console.log("Production website config exists; preserving it.");
} catch {
  const demoUrl = process.env.OLIN_DEMO_URL || "https://olin-scoring-mvp.fly.dev/";
  const waitlistUrl = process.env.OLIN_WAITLIST_API_URL || "https://olin-scoring-mvp.fly.dev/api/v1/waitlist";
  if (process.env.OLIN_DEMO_URL || process.env.OLIN_WAITLIST_API_URL) {
    await writeFile(
      target,
      `const OLIN_DEMO_URL = ${JSON.stringify(demoUrl)};\nconst OLIN_WAITLIST_API_URL = ${JSON.stringify(waitlistUrl)};\n`,
      "utf8",
    );
    console.log("Created public/config.js from deployment environment variables.");
  } else {
    await copyFile(template, target);
    console.log("Created public/config.js from the production waitlist template.");
  }
}
