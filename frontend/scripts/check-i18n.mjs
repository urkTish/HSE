// Fails when a key exists in one locale but not the other, or when a value is empty (spec rule 41, AC 29).
// 8-quality §3.3a: also checks the Quality parts' files messages/quality/q<n>.<locale>.json (parity,
// empty values, Arabic script, a key defined twice across parts), and runs a self-test first that a
// key missing from q1.ar.json is caught.
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "messages");
const locales = ["en", "ar"];
const QUALITY_PARTS = [0, 1, 2, 3, 4];
const arabicScript = /[؀-ۿ]/;
const allowLatinOnly = new Set(["common.english", "shell.switchToEnglish", "common.dash"]);

function flatten(obj, prefix = "", out = new Map()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object") flatten(v, key, out);
    else out.set(key, v);
  }
  return out;
}

/** Parity, empty values and untranslated Arabic for one set of { en: Map, ar: Map }. */
function checkMaps(maps, label, problems) {
  for (const a of locales) {
    for (const b of locales) {
      if (a === b) continue;
      for (const key of maps[a].keys()) {
        if (!maps[b].has(key)) problems.push(`missing in ${label(b)}: ${key}`);
      }
    }
    for (const [key, value] of maps[a]) {
      if (typeof value !== "string" || value.trim() === "") problems.push(`empty value in ${label(a)}: ${key}`);
    }
  }
  for (const [key, value] of maps.ar) {
    if (typeof value === "string" && !arabicScript.test(value) && !allowLatinOnly.has(key)) {
      problems.push(`untranslated (no Arabic script) in ${label("ar")}: ${key}`);
    }
  }
}

/** The Quality parts: each pair is checked on its own; a key may live in one part only. */
function checkQuality(files, problems) {
  const owner = new Map();
  for (const n of QUALITY_PARTS) {
    const maps = { en: flatten(files[n].en), ar: flatten(files[n].ar) };
    checkMaps(maps, (l) => `quality/q${n}.${l}.json`, problems);
    for (const key of maps.en.keys()) {
      if (owner.has(key) && owner.get(key) !== n) problems.push(`quality key in q${owner.get(key)} and q${n}: ${key}`);
      owner.set(key, n);
    }
  }
}

function selfTest() {
  const files = QUALITY_PARTS.map(() => ({ en: {}, ar: {} }));
  files[1] = { en: { itp: { title: "ITP" } }, ar: {} };
  const problems = [];
  checkQuality(files, problems);
  if (!problems.some((p) => p === "missing in quality/q1.ar.json: itp.title")) {
    console.error("i18n check self-test failed: a key missing from q1.ar.json was not caught.");
    process.exit(1);
  }
}

selfTest();
const problems = [];
const maps = Object.fromEntries(
  locales.map((l) => [l, flatten(JSON.parse(readFileSync(join(root, `${l}.json`), "utf8")))]),
);
checkMaps(maps, (l) => `${l}.json`, problems);
for (const key of maps.en.keys()) if (key === "quality" || key.startsWith("quality.")) problems.push(`en.json must not define quality.*: ${key}`);
const files = QUALITY_PARTS.map((n) =>
  Object.fromEntries(
    locales.map((l) => {
      const f = join(root, "quality", `q${n}.${l}.json`);
      if (!existsSync(f)) {
        problems.push(`missing file quality/q${n}.${l}.json`);
        return [l, {}];
      }
      return [l, JSON.parse(readFileSync(f, "utf8"))];
    }),
  ),
);
checkQuality(files, problems);

const unique = [...new Set(problems)];
if (unique.length) {
  console.error(`i18n check failed (${unique.length} problem(s)):\n  ${unique.join("\n  ")}`);
  process.exit(1);
}
const qKeys = files.reduce((n, f) => n + flatten(f.en).size, 0);
console.log(`i18n check passed: ${maps.en.size} keys + ${qKeys} Quality keys in ${locales.join(", ")}.`);
