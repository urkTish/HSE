import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { getJson } from "./helpers";
import { makePng } from "./p2-helpers";

/** A minimal valid one-page PDF (accreditation certificates, certificate scans). */
export function makePdf(): Buffer {
  const body = [
    "%PDF-1.4",
    "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj",
    "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj",
    "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj",
    "trailer<</Root 1 0 R>>",
    "%%EOF",
  ].join("\n");
  return Buffer.from(body, "latin1");
}

export const PDF = (name = "certificate.pdf") => ({
  name,
  mimeType: "application/pdf",
  buffer: makePdf(),
});
export const PNG = (name = "scan.png") => ({
  name,
  mimeType: "image/png",
  buffer: makePng(640),
});

/** Upload through an UploadField (the input testid is the field id) and wait for the "uploaded" mark. */
export async function uploadInto(
  page: Page,
  id: string,
  file: { name: string; mimeType: string; buffer: Buffer },
): Promise<void> {
  await page.getByTestId(id).setInputFiles(file);
  await expect(page.getByTestId(`${id}-done`)).toBeVisible({ timeout: 20_000 });
}

interface Pg<T> {
  items: T[];
}

/** Find a record id by a field value in a project-scoped Phase 4 list (`q` search). */
export async function findIn(
  api: APIRequestContext,
  url: string,
  key: string,
  value: string,
): Promise<string> {
  const sep = url.includes("?") ? "&" : "?";
  const list = await getJson<Pg<Record<string, unknown>>>(
    api,
    `${url}${sep}q=${encodeURIComponent(value)}&page_size=100`,
  );
  const hit = list.items.find((x) => x[key] === value);
  if (!hit) throw new Error(`${value} not found in ${url}`);
  return String(hit.id);
}

/** Phase 3 seed users used by the Phase 4 ACs (3-ptw Appendix A). */
export const USERS4 = {
  fahad: "fahad.mutairi@example.com",
  lina: "lina.haddad@example.com",
} as const;

/** Wait until the certification check page has hydrated (its test hook is installed in an effect). */
export async function certCheckReady(page: Page): Promise<void> {
  await page.waitForFunction(
    () =>
      typeof (window as unknown as { __hseCertScan?: unknown })
        .__hseCertScan === "function",
  );
}
