#!/usr/bin/env node
// Validator for the Canada knowledge base (SPEC §2.8). No dependencies.
//
//   node knowledge-base/scripts/validate.mjs            validate every lane
//   node knowledge-base/scripts/validate.mjs <dir|file>  validate given paths
//
// Checks each *.json record (GeoJSON FeatureCollections are skipped) against
// record.schema.json, then its `attributes` against the category schema when
// one exists (clim, school, re). Also checks that the file name equals the id,
// that the id's category and province segments agree with the record, and that
// created <= updated <= today. Exit code 1 when any error is found.

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, dirname, basename, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const kbRoot = resolve(here, "..");
const schemaDir = join(kbRoot, "schema");

const loadSchema = (name) => JSON.parse(readFileSync(join(schemaDir, name), "utf8"));
const recordSchema = loadSchema("record.schema.json");
const categorySchemas = {
  clim: loadSchema("climate-normals.schema.json"),
  school: loadSchema("school.schema.json"),
  re: loadSchema("market-observation.schema.json"),
};

const SKIP_DIRS = new Set(["schema", "scripts", "node_modules", ".git"]);

function walk(path, out = []) {
  const st = statSync(path);
  if (st.isDirectory()) {
    for (const name of readdirSync(path).sort()) {
      if (SKIP_DIRS.has(name)) continue;
      walk(join(path, name), out);
    }
  } else if (path.endsWith(".json")) {
    out.push(path);
  }
  return out;
}

const typeOf = (v) => (v === null ? "null" : Array.isArray(v) ? "array" : typeof v);
const isDate = (s) => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s));

function validate(schema, value, path, errors) {
  if (schema.type) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    const t = typeOf(value);
    const ok = types.some((x) => x === t || (x === "integer" && t === "number" && Number.isInteger(value)));
    if (!ok) {
      errors.push(`${path}: expected ${types.join("|")}, got ${t}`);
      return;
    }
  }
  if (schema.const !== undefined && value !== schema.const) errors.push(`${path}: must equal ${JSON.stringify(schema.const)}`);
  if (schema.enum && !schema.enum.includes(value)) errors.push(`${path}: ${JSON.stringify(value)} is not one of [${schema.enum.map(String).join(", ")}]`);
  if (typeof value === "string") {
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) errors.push(`${path}: "${value}" does not match /${schema.pattern}/`);
    if (schema.format === "date" && !isDate(value)) errors.push(`${path}: "${value}" is not a YYYY-MM-DD date`);
    if (schema.minLength !== undefined && value.length < schema.minLength) errors.push(`${path}: must not be empty`);
  }
  if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push(`${path}: ${value} < minimum ${schema.minimum}`);
    if (schema.maximum !== undefined && value > schema.maximum) errors.push(`${path}: ${value} > maximum ${schema.maximum}`);
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push(`${path}: needs at least ${schema.minItems} items, has ${value.length}`);
    if (schema.maxItems !== undefined && value.length > schema.maxItems) errors.push(`${path}: allows at most ${schema.maxItems} items, has ${value.length}`);
    if (schema.items) value.forEach((v, i) => validate(schema.items, v, `${path}[${i}]`, errors));
  }
  if (typeOf(value) === "object") {
    for (const req of schema.required || []) if (!(req in value)) errors.push(`${path}: missing required "${req}"`);
    const props = schema.properties || {};
    for (const [k, v] of Object.entries(value)) {
      if (props[k]) validate(props[k], v, `${path}.${k}`, errors);
      else if (schema.additionalProperties === false) errors.push(`${path}: unexpected property "${k}"`);
    }
  }
}

function crossChecks(rec, file, errors, warnings) {
  const expectedName = `${rec.id}.json`;
  if (basename(file) !== expectedName) errors.push(`file name must be ${expectedName}`);
  if (typeof rec.id === "string") {
    const [cat, prov] = rec.id.split("-");
    if (rec.category && cat !== rec.category) errors.push(`id category "${cat}" differs from category "${rec.category}"`);
    if (rec.geo && rec.geo.province && prov !== String(rec.geo.province).toLowerCase()) errors.push(`id province "${prov}" differs from geo.province "${rec.geo.province}"`);
  }
  const today = new Date().toISOString().slice(0, 10);
  if (isDate(rec.created) && isDate(rec.updated) && rec.created > rec.updated) errors.push(`created ${rec.created} is after updated ${rec.updated}`);
  if (isDate(rec.updated) && rec.updated > today) errors.push(`updated ${rec.updated} is in the future`);
  if (rec.verification && isDate(rec.verification.last_verified) && rec.verification.last_verified > today) errors.push(`verification.last_verified is in the future`);
  if (rec.verification && isDate(rec.verification.next_review) && rec.verification.next_review < today) warnings.push(`next_review ${rec.verification.next_review} has passed`);
  if (rec.category === "clim" && rec.attributes && Array.isArray(rec.attributes.months)) {
    const months = rec.attributes.months.map((m) => m && m.month);
    for (let i = 1; i <= 12; i++) if (!months.includes(i)) errors.push(`attributes.months is missing month ${i}`);
    for (const m of rec.attributes.months) {
      if (m && typeof m.tmax_c === "number" && typeof m.tmin_c === "number" && m.tmax_c < m.tmin_c) errors.push(`month ${m.month}: tmax_c below tmin_c`);
    }
  }
  if (rec.category === "school" && rec.attributes && rec.attributes.qualifying === "qualifying" && rec.verification && rec.verification.status !== "verified") {
    errors.push(`a qualifying school must have verification.status "verified" (SPEC §7)`);
  }
  if (rec.geo && (rec.geo.lat === undefined) !== (rec.geo.lon === undefined)) errors.push(`geo.lat and geo.lon must be given together`);
}

function main() {
  const args = process.argv.slice(2);
  const targets = args.length ? args.map((a) => resolve(a)) : [kbRoot];
  for (const t of targets) if (!existsSync(t)) { console.error(`not found: ${t}`); process.exit(2); }

  const files = targets.flatMap((t) => walk(t));
  let records = 0, skipped = 0, failed = 0, warningCount = 0;
  for (const file of files) {
    const rel = relative(process.cwd(), file);
    let data;
    try {
      data = JSON.parse(readFileSync(file, "utf8"));
    } catch (e) {
      failed++;
      console.log(`✗ ${rel}\n    invalid JSON: ${e.message}`);
      continue;
    }
    if (data && data.type === "FeatureCollection") { skipped++; continue; }
    if (data && data.$schema && !data.id) { skipped++; continue; }
    records++;
    const errors = [], warnings = [];
    validate(recordSchema, data, "record", errors);
    const catSchema = data && categorySchemas[data.category];
    if (catSchema && data.attributes && typeOf(data.attributes) === "object") validate(catSchema, data.attributes, "attributes", errors);
    if (data && typeof data === "object") crossChecks(data, file, errors, warnings);
    warningCount += warnings.length;
    if (errors.length) {
      failed++;
      console.log(`✗ ${rel}`);
      for (const e of errors) console.log(`    ${e}`);
    }
    for (const w of warnings) console.log(`  ! ${rel}: ${w}`);
  }
  console.log(`\n${records} record(s) checked, ${failed} failed, ${warningCount} warning(s), ${skipped} non-record JSON file(s) skipped.`);
  process.exit(failed ? 1 : 0);
}

main();
