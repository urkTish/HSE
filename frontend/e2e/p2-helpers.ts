import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { deflateSync } from "node:zlib";
import { apiAs, getJson, USERS } from "./helpers";

/** Select the first <option> whose text contains `text`. */
export async function selectContaining(select: Locator, text: string): Promise<void> {
  await expect(select.locator("option", { hasText: text }).first()).toBeAttached();
  const value = await select.evaluate((el, p) => Array.from((el as HTMLSelectElement).options).find((o) => o.text.includes(p))?.value ?? "", text);
  if (!value) throw new Error(`no option containing ${text}`);
  await select.selectOption(value);
}

/** Ensure options are selected in a MultiSelect popover (trigger has the given id), then close it. */
export async function pickMulti(page: Page, id: string, labels: (string | RegExp)[]): Promise<void> {
  await page.locator(`button#${id}`).click();
  const list = page.getByRole("listbox");
  for (const l of labels) {
    const opt = list.getByRole("option", { name: l }).first();
    if ((await opt.getAttribute("aria-selected")) !== "true") await opt.getByRole("button").click();
    await expect(opt).toHaveAttribute("aria-selected", "true");
  }
  await page.keyboard.press("Escape");
  await expect(list).toBeHidden();
}

/** Draw a stroke on a signature pad canvas. */
export async function sign(page: Page, testId: string): Promise<void> {
  const pad = page.getByTestId(testId);
  await pad.scrollIntoViewIfNeeded();
  const box = await pad.boundingBox();
  if (!box) throw new Error("signature pad not visible");
  await page.mouse.move(box.x + 20, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + 15, { steps: 8 });
  await page.mouse.move(box.x + box.width - 20, box.y + box.height - 15, { steps: 8 });
  await page.mouse.up();
  await expect(pad).toHaveAttribute("data-signed", "true");
}

/** Random valid-looking iqama number (2 + 9 digits). */
export function iqama(): string {
  return `2${Math.floor(100_000_000 + Math.random() * 899_999_999)}`;
}

export interface Ids {
  pid: string;
  site: (code: string) => string;
  zone: (code: string) => string;
  eng: (code: string) => { id: string; site_ids: string[] };
}

export async function projectIds(api: APIRequestContext, code = "ANIA-EXP"): Promise<Ids> {
  const projects = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects?q=${code}`);
  const pid = projects.items.find((p) => p.code === code)?.id ?? "";
  const sites = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects/${pid}/sites?page_size=100`);
  const zones = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects/${pid}/zones?page_size=100`);
  const engs = await getJson<{ items: { id: string; site_ids: string[]; contractor: { short_code: string } }[] }>(api, `/api/v1/projects/${pid}/engagements?page_size=100`);
  return {
    pid,
    site: (c) => sites.items.find((s) => s.code === c)?.id ?? "",
    zone: (c) => zones.items.find((z) => z.code === c)?.id ?? "",
    eng: (c) => {
      const e = engs.items.find((x) => x.contractor.short_code === c);
      return { id: e?.id ?? "", site_ids: e?.site_ids ?? [] };
    },
  };
}

/** Create a contractor worker with a first deployment through the API (test setup). */
export async function createWorker(api: APIRequestContext, ids: Ids, name: string, contractor = "RAWABI", lang = "en") {
  const e = ids.eng(contractor);
  const res = await api.post("/api/v1/workers", {
    data: {
      person_type: "contractor_worker",
      full_name_en: name,
      full_name_ar: "عامل اختبار",
      id_type: "iqama",
      id_number: iqama(),
      id_expiry_date: "2029-01-01",
      nationality: "PK",
      adult_attestation: true,
      primary_language: lang,
      deployment: { project_id: ids.pid, engagement_id: e.id, trade: "labourer", site_ids: e.site_ids, mobilised_on: "2026-09-01" },
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const w = (await res.json()) as { id: string; worker_no: string };
  const deps = await getJson<{ items: { id: string; worker_id: string }[] }>(api, `/api/v1/projects/${ids.pid}/deployments?q=${w.worker_no}`);
  const dep = deps.items.find((d) => d.worker_id === w.id);
  return { ...w, deploymentId: dep?.id ?? "" };
}

/** 1×1 transparent PNG used as a drawn signature in API setup. */
export const SIGNATURE_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

/** The project's site general induction course "GEN" (created when the seed has none). */
export async function ensureGenCourse(api: APIRequestContext, pid: string): Promise<string> {
  const list = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects/${pid}/induction-courses`);
  const found = list.items.find((c) => c.code === "GEN");
  if (found) return found.id;
  const res = await api.post(`/api/v1/projects/${pid}/induction-courses`, {
    data: {
      code: "GEN",
      induction_type: "general_site",
      name_en: "General site induction",
      name_ar: "التعريف العام بالموقع",
      version: "1.0",
      validity_months: 12,
      min_duration_minutes: 60,
      test_required: false,
      languages_offered: ["en", "ar", "ur", "hi"],
      delivered_by_roles: ["hse_manager", "hse_officer"],
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { id: string }).id;
}

/**
 * Record a completed induction through the API (test setup). It is recorded by the HSE Officer, a deliverer
 * every seeded course allows (IN-3); the duration and test score follow the course's own rules.
 * `_api` is kept for call-site symmetry.
 */
export async function recordInduction(_api: APIRequestContext, pid: string, workerId: string, courseId: string, lang = "en"): Promise<void> {
  const officer = await apiAs(USERS.noura);
  const course = await getJson<{ min_duration_minutes: number; test_required: boolean }>(officer, `/api/v1/induction-courses/${courseId}`);
  const res = await officer.post(`/api/v1/projects/${pid}/inductions`, {
    data: {
      worker_id: workerId,
      course_id: courseId,
      delivery_language: lang,
      privacy_notice_version: "WPN-1.0",
      signature_png_base64: SIGNATURE_PNG,
      delivered_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
      duration_minutes: Math.max(60, course.min_duration_minutes),
      test_score_pct: course.test_required ? "100" : null,
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}

export async function accessCard(api: APIRequestContext, deploymentId: string): Promise<{ printed_ref: string; qr_payload: string }> {
  return getJson(api, `/api/v1/deployments/${deploymentId}/access-card`);
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (const byte of buf) c = (CRC_TABLE[(c ^ byte) & 0xff] ?? 0) ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

/** A real grey PNG of `size`×`size` pixels (worker photos must be at least 400×400). */
export function makePng(size = 480): Buffer {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr.writeUInt8(8, 8); // bit depth
  ihdr.writeUInt8(2, 9); // RGB
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(size * 3, 0xa0)]);
  const raw = Buffer.concat(Array.from({ length: size }, () => row));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", deflateSync(raw)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

export async function uploadPhoto(api: APIRequestContext, workerId: string): Promise<void> {
  const res = await api.post("/api/v1/attachments", {
    multipart: { owner_type: "worker_photo", owner_id: workerId, file: { name: "photo.png", mimeType: "image/png", buffer: makePng() } },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}

/** Ensure a course with this code exists (airside courses require GEN first). */
export async function ensureCourse(api: APIRequestContext, pid: string, code: string, type: string, prereq: string[] = []): Promise<string> {
  const list = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects/${pid}/induction-courses`);
  const found = list.items.find((c) => c.code === code);
  if (found) return found.id;
  const res = await api.post(`/api/v1/projects/${pid}/induction-courses`, {
    data: {
      code,
      induction_type: type,
      name_en: `${code} induction`,
      name_ar: `تعريف ${code}`,
      version: "1.0",
      validity_months: 12,
      min_duration_minutes: 60,
      test_required: false,
      languages_offered: ["en", "ar", "ur", "hi"],
      delivered_by_roles: ["hse_manager", "hse_officer"],
      prerequisite_codes: prereq,
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { id: string }).id;
}

/**
 * GC-14 setup: a banned worker is DENIED at a new site gate and recorded as admitted anyway, so the
 * dashboard's "admitted despite denial" item (last 7 days, §8.1) exists without relying on an earlier spec.
 */
export async function admitDespiteDenial(api: APIRequestContext, ids: Ids, site = "S-AIR"): Promise<string> {
  const gen = await ensureGenCourse(api, ids.pid);
  const bad = await createWorker(api, ids, `Admit Banned ${Date.now().toString(36)}`);
  await recordInduction(api, ids.pid, bad.id, gen);
  const ref = (await accessCard(api, bad.deploymentId)).printed_ref;
  const ban = await api.post(`/api/v1/workers/${bad.id}/transitions`, { data: { to_status: "banned", reason: "Repeated unsafe acts on site (test)" } });
  expect(ban.ok(), await ban.text()).toBeTruthy();
  const gate = await api.post(`/api/v1/projects/${ids.pid}/gates`, {
    data: { gate_code: `GA${Date.now().toString(36).slice(-6).toUpperCase()}`, name_en: "E2E admit gate", name_ar: "بوابة اختبار", site_id: ids.site(site), gate_type: "site_gate" },
  });
  expect(gate.ok(), await gate.text()).toBeTruthy();
  const gateId = ((await gate.json()) as { id: string }).id;
  const check = await api.post("/api/v1/gate-checks", { data: { gate_id: gateId, printed_ref: ref } });
  expect(check.ok(), await check.text()).toBeTruthy();
  const res = (await check.json()) as { check_id: string; result: string };
  expect(res.result).toBe("DENIED");
  const admit = await api.post(`/api/v1/gate-checks/${res.check_id}/admitted-despite-denial`, { data: { reason: "Escorted by site manager to collect tools" } });
  expect(admit.ok(), await admit.text()).toBeTruthy();
  return res.check_id;
}
