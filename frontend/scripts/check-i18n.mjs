// Fails when a key exists in one locale but not the other, or when a value is empty (spec rule 41, AC 29).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "messages");
const locales = ["en", "ar"];

function flatten(obj, prefix = "", out = new Map()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object") flatten(v, key, out);
    else out.set(key, v);
  }
  return out;
}

const maps = Object.fromEntries(
  locales.map((l) => [l, flatten(JSON.parse(readFileSync(join(root, `${l}.json`), "utf8")))]),
);

const problems = [];
for (const a of locales) {
  for (const b of locales) {
    if (a === b) continue;
    for (const key of maps[a].keys()) {
      if (!maps[b].has(key)) problems.push(`missing in ${b}.json: ${key}`);
    }
  }
  for (const [key, value] of maps[a]) {
    if (typeof value !== "string" || value.trim() === "") problems.push(`empty value in ${a}.json: ${key}`);
  }
}
const arabicScript = /[؀-ۿ]/;
const allowLatinOnly = new Set(["common.english", "shell.switchToEnglish", "common.dash"]);
for (const [key, value] of maps.ar) {
  if (typeof value === "string" && !arabicScript.test(value) && !allowLatinOnly.has(key)) {
    problems.push(`untranslated (no Arabic script) in ar.json: ${key}`);
  }
}

const unique = [...new Set(problems)];
if (unique.length) {
  console.error(`i18n check failed (${unique.length} problem(s)):\n  ${unique.join("\n  ")}`);
  process.exit(1);
}
console.log(`i18n check passed: ${maps.en.size} keys in ${locales.join(", ")}.`);
