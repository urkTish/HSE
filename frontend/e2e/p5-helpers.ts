import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { apiAs, getJson, projectId, USERS } from "./helpers";
import { certCheckReady } from "./p4-helpers";

/** Phase 3/4 seed users the Phase 5 ACs also use (5-training §9 "Users"). */
export const USERS5 = {
  lina: "lina.haddad@example.com",
  fahad: "fahad.mutairi@example.com",
  majed: "majed.shammari@example.com",
} as const;

interface Pg<T> {
  items: T[];
}

/** Id of a training session by its number (TRS-…). */
export async function sessionId(api: APIRequestContext, code: string, sessionNo: string): Promise<string> {
  const pid = await projectId(api, code);
  const list = await getJson<Pg<{ id: string; session_no: string }>>(api, `/api/v1/projects/${pid}/training-sessions?page_size=200`);
  const hit = list.items.find((x) => x.session_no === sessionNo);
  if (!hit) throw new Error(`${sessionNo} not found on ${code}`);
  return hit.id;
}

/** Id of a worker's training record for a course on a project (the newest one). */
export async function recordOf(api: APIRequestContext, code: string, workerNo: string, course: string): Promise<{ id: string; record_no: string; status: string }> {
  const pid = await projectId(api, code);
  const list = await getJson<Pg<{ id: string; record_no: string; status: string; course_code: string; worker: { worker_no: string } }>>(
    api,
    `/api/v1/projects/${pid}/training-records?q=${encodeURIComponent(workerNo)}&course_code=${encodeURIComponent(course)}&page_size=50`,
  );
  const hit = list.items.find((x) => x.worker.worker_no === workerNo && x.course_code === course);
  if (!hit) throw new Error(`${workerNo} has no ${course} record on ${code}`);
  return hit;
}

/** A worker's id and current deployment id on a project. */
export async function deploymentOf(code: string, workerNo: string): Promise<{ id: string; worker_id: string }> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, code);
  const list = await getJson<Pg<{ id: string; worker_id: string }>>(api, `/api/v1/projects/${pid}/deployments?q=${workerNo}`);
  const d = list.items[0];
  if (!d) throw new Error(`${workerNo} has no deployment on ${code}`);
  return d;
}

/** Select the project in the shell so project-scoped pages open on it. */
export async function useProject(page: Page, code: string): Promise<void> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, code);
  await page.goto(`/en?project=${pid}`);
  await expect(page.getByTestId("topbar")).toBeVisible();
}

/** QR payload of a session-issued training record's certificate (HSE2:TR:…). */
export async function trQr(recordId: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const c = await getJson<{ qr_payload: string }>(api, `/api/v1/training-records/${recordId}/certificate`);
  return c.qr_payload;
}

/** Open the certification check and feed it a scanned payload. */
export async function scan(page: Page, payload: string): Promise<void> {
  await page.goto("/en/cert-check");
  await certCheckReady(page);
  await page.evaluate((p) => (window as unknown as { __hseCertScan: (x: string) => Promise<void> }).__hseCertScan(p), payload);
}

