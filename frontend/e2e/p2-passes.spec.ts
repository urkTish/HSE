import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, login, uid, USERS } from "./helpers";
import { createWorker, ensureCourse, ensureGenCourse, makePng, pickMulti, projectIds, recordInduction, selectContaining, uploadPhoto } from "./p2-helpers";

// Committed demo screenshots are only rewritten on demand (SCREENSHOTS=1).
const SHOTS = process.env.SCREENSHOTS ? "../docs/screenshots/phase-2" : "test-results/shots";

function code(prefix: string, len: number): string {
  return `${prefix}${uid()}`.slice(0, len);
}

test.describe.serial("Phase 2 — airport pass setup, applications and passes", () => {
  const cat = code("P", 8);
  const area = code("Q", 4);
  let workerNo = "";
  let appUrl = "";

  test.beforeAll(async () => {
    const api = await apiAs(USERS.faisal);
    const ids = await projectIds(api);
    const gen = await ensureGenCourse(api, ids.pid);
    const air = await ensureCourse(api, ids.pid, "AIR", "airside", ["GEN"]);
    const w = await createWorker(api, ids, `Pass Applicant ${uid()}`);
    await recordInduction(api, ids.pid, w.id, gen);
    await recordInduction(api, ids.pid, w.id, air);
    await uploadPhoto(api, w.id);
    workerNo = w.worker_no;
  });

  test("AP setup: the HSE Manager adds a pass category and an area code", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/pass-setup");
    await page.getByTestId("new-category").click();
    await page.locator("#pc-code").fill(cat);
    await page.locator("#pc-name-en").fill("Permanent unescorted (test)");
    await page.locator("#pc-name-ar").fill("دائم بدون مرافقة");
    await page.locator("#pc-days").fill("700");
    await page.locator("#pc-bg").check();
    await page.locator("#pc-adp").check();
    await page.getByTestId("save-category").click();
    await expect(page.getByTestId("categories-table")).toContainText(cat);

    await page.getByTestId("new-area").click();
    await page.locator("#pa-code").fill(area);
    await page.locator("#pa-kind").selectOption("apron");
    await page.locator("#pa-name-en").fill("Apron test area");
    await page.locator("#pa-name-ar").fill("منطقة الساحة");
    await pickMulti(page, "pa-zones", [/Z-APR-21/]);
    await page.getByTestId("save-area").click();
    await expect(page.getByTestId("areas-table")).toContainText(area);
  });

  async function step(page: Page, k: string) {
    await page.getByTestId(`step-${k}`).click();
  }

  test("AP: a contractor rep applies and submits; the HSE Officer endorses", async ({ page }) => {
    await login(page, USERS.ahmed);
    await page.goto("/en/pass-applications/new");
    await page.getByTestId("pa-worker-search").fill(workerNo);
    await selectContaining(page.getByTestId("pa-worker"), workerNo);
    await page.locator("#pa-type-sel").selectOption("new");
    await page.locator("#pa-letter").fill(`SL-${uid()}`);
    await selectContaining(page.getByTestId("pa-cat"), cat);
    await page.locator("#pa-until").fill("2027-06-30");
    await pickMulti(page, "pa-areas", [new RegExp(area)]);
    await page.locator("#pa-just").fill("Apron paving crew for stand 21 works package.");
    await page.getByTestId("save-application").click();
    await expect(page).toHaveURL(/\/pass-applications\/[0-9a-f-]{36}$/);
    appUrl = new URL(page.url()).pathname.replace(/^\/en/, "");
    // AP-3: the ID copy is uploaded on the draft before submitting.
    const idCopy = page.getByTestId("attachments-pass_application_id_copy");
    await idCopy.getByTestId("file-input").setInputFiles({ name: "id-copy.png", mimeType: "image/png", buffer: makePng() });
    await expect(idCopy.locator("li", { hasText: "id-copy.png" })).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/pass-application-en.png`, fullPage: true });
    await step(page, "submit");
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("application-status")).toHaveAttribute("data-status", "submitted");
    // Background check details are never shown to a contractor rep (AP-13).
    await expect(page.getByTestId("background-check")).toHaveCount(0);

    await login(page, USERS.noura);
    await page.goto(`/en${appUrl}`);
    await step(page, "endorse");
    await selectContaining(page.locator("[role=dialog] select").first(), "Noura");
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("application-status")).toHaveAttribute("data-status", "endorsed");
  });

  test("AP-4: approval needs a cleared background check; then the pass is issued", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto(`/en${appUrl}`);
    await step(page, "lodge");
    await page.locator("#lodge-ref").fill(`GACA-${uid()}`);
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("application-status")).toHaveAttribute("data-status", "lodged");

    await step(page, "approve");
    await page.getByTestId("step-confirm").click();
    await expect(page.getByRole("dialog").getByTestId("form-error")).toBeVisible();
    await page.keyboard.press("Escape");

    await step(page, "bg");
    await page.locator("#bg-status").selectOption("cleared");
    await page.locator("#bg-date").fill("2026-10-01");
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("background-check")).toContainText(/Cleared/i);

    await step(page, "approve");
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("application-status")).toHaveAttribute("data-status", "approved");

    await step(page, "issue");
    await page.locator("#issue-no").fill(`ANIA-AP-26-${uid()}`);
    await page.locator("#issue-expiry").fill("2027-06-30");
    await page.getByTestId("issue-confirm").click();
    await expect(page).toHaveURL(/\/airport-passes\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("limiting-factor").first()).toBeVisible();
  });
});
