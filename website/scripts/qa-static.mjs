import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";

const root = new URL("../", import.meta.url).pathname;
const dist = join(root, "dist");
const failures = [];
const checks = [];

const walk = (directory) => readdirSync(directory).flatMap((name) => {
  const path = join(directory, name);
  return statSync(path).isDirectory() ? walk(path) : [path];
});

const record = (condition, message) => {
  if (condition) checks.push(message);
  else failures.push(message);
};

const routeToFile = (value) => {
  const clean = value.split("#")[0].split("?")[0];
  if (!clean || clean === "/") return join(dist, "index.html");
  const direct = join(dist, clean.replace(/^\//, ""));
  if (extname(direct)) return direct;
  return join(direct, "index.html");
};

record(existsSync(dist), "dist existe");

const htmlFiles = walk(dist).filter((path) => path.endsWith(".html"));
record(htmlFiles.length >= 7, "pages statiques générées");

for (const path of htmlFiles) {
  const html = readFileSync(path, "utf8");
  const label = relative(dist, path);
  const h1Count = (html.match(/<h1\b/gi) || []).length;
  record(h1Count === 1, `${label}: un seul h1`);
  record(!html.includes("http://127.0.0.1"), `${label}: aucune URL 127.0.0.1 intégrée`);
  record(!html.includes("http://localhost"), `${label}: aucune URL localhost intégrée`);

  const attributes = [...html.matchAll(/(?:href|src)="([^"]+)"/g)].map((match) => match[1]);
  for (const value of attributes) {
    if (!value.startsWith("/") || value.startsWith("//")) continue;
    record(existsSync(routeToFile(value)), `${label}: ressource interne ${value}`);
  }
}

const home = readFileSync(join(dist, "index.html"), "utf8");
record(home.includes("¿Puede este negocio"), "accueil: question principale explicite");
record(home.includes("Nadie puede garantizar el pago"), "accueil: aucune promesse de remboursement");
record(home.includes("Tiendas de abarrotes") && home.includes("Taquerías y fondas") && home.includes("Papelerías y ferreterías"), "accueil: plusieurs types de petits commerces");
record(!/microcomercios|corner stores|tiendas de esquina|un abarrotes|garantiza el reembolso/i.test(home), "accueil: terminologie interdite absente");

const explorer = readFileSync(join(root, "src", "components", "DecisionExplorer.tsx"), "utf8");
record(explorer.includes('C3 · D2 · S1 a la Ruta 11'), "cas synthétique: C3 · D2 · S1 mène à la route 11");
record(explorer.includes('tier: "Ruta 13"') && explorer.includes('inferior a 1,5× activa la Ruta 13'), "cas synthétique: D3 mène à la route 13");

const decisionScene = readFileSync(join(dist, "demo-scenes", "decision", "index.html"), "utf8");
record(decisionScene.includes("R11") && !decisionScene.includes("T8"), "scène de démonstration: route 11 cohérente");

if (failures.length) {
  console.error(`QA statique: ${failures.length} échec(s)`);
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`QA statique: ${checks.length} contrôles réussis`);
