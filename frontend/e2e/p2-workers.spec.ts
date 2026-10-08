import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, uid, USERS } from "./helpers";
import { createWorker, ensureGenCourse, iqama, pickMulti, projectIds, recordInduction, selectContaining, sign } from "./p2-helpers";

const SHOTS = "../docs/screenshots/phase-2";

test.describe.serial("Phase 2 — workers, inductions, zone profiles", () => {
  const code = `G${uid()}`.slice(0, 8);
  let workerNo = "";
  let idNumber = "";

  test("WK: register a worker with a first deployment; the ID is masked and unmasking needs a reason", async ({ page }) => {
    idNumber = iqama();
    await login(page, USERS.faisal);
    await page.goto("/en/workers/new");
    const f = page.getByTestId("worker-form");
    await f.locator("#person_type").selectOption("contractor_worker");
    await f.locator("#primary_language").selectOption("ur");
    await f.locator("#full_name_en").fill("Imran Test");
    await f.locator("#full_name_ar").fill("عمران اختبار");
    await f.locator("#nationality").fill("PK");
    await f.locator("#id_type").selectOption("iqama");
    await f.locator("#id_number").fill(idNumber);
    await f.locator("#id_expiry_date").fill("2029-03-01");
    await f.locator("#adult_attestation").check();
    await selectContaining(f.locator("[id='dep.engagement_id']"), "RAWABI");
    await f.locator("[id='dep.trade']").selectOption("labourer");
    await pickMulti(page, "dep-sites", [/S-AIR/]);
    await f.locator("[id='dep.mobilised_on']").fill("2026-09-01");
    await page.getByTestId("save-worker").click();

    await expect(page.getByTestId("worker-title")).toBeVisible();
    workerNo = (await page.getByTestId("worker-no").innerText()).trim();
    expect(workerNo).not.toBe("");
    const masked = page.getByTestId("id-number-masked").first();
    await expect(masked).toContainText("*");
    await expect(page.locator("body")).not.toContainText(idNumber);

    await page.getByTestId("reveal-id").first().click();
    await expect(page.getByTestId("reveal-confirm")).toBeDisabled();
    await page.locator("#unmask-reason").selectOption("identity_verification");
    await page.getByTestId("reveal-confirm").click();
    await expect(page.getByTestId("id-number-full")).toHaveText(idNumber);
    // Never cached: a reload shows the masked number again.
    await page.reload();
    await expect(page.getByTestId("id-number-masked").first()).toContainText("*");
    await expect(page.getByTestId("deployment-card").first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/worker-detail-masked-id-en.png`, fullPage: true });
  });

  test("IN: create an induction course and require it on an airside zone", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/induction-courses/new");
    await page.locator("#c-code").fill(code);
    await page.locator("#c-type").selectOption("zone_specific");
    await page.locator("#c-name-en").fill(`Zone briefing ${code}`);
    await page.locator("#c-name-ar").fill("تعريف المنطقة");
    await page.locator("#c-version").fill("1.0");
    await page.locator("#c-months").fill("12");
    await page.locator("#c-min").fill("60");
    await pickMulti(page, "c-langs", ["English", "Arabic"]);
    await pickMulti(page, "c-roles", ["HSE Manager", "HSE Officer"]);
    await page.getByTestId("save-course").click();
    await expect(page.locator("h1")).toContainText(code);

    await page.goto("/en/zone-profiles");
    const row = page.locator("[data-testid=zone-profile-row][data-zone='Z-TWB']");
    await row.getByTestId("edit-zone-profile").click();
    await pickMulti(page, "zp-req", [code]);
    await page.getByTestId("save-zone-profile").click();
    await expect(row).toContainText(code);
  });

  test("IN: recording an induction in a language the worker does not speak shows an amber warning, not an error", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/inductions/new");
    await page.getByTestId("in-worker-search").fill(workerNo);
    await selectContaining(page.getByTestId("in-worker"), workerNo);
    await selectContaining(page.getByTestId("in-course-sel"), code);
    await page.getByTestId("in-lang").selectOption("en");
    const warn = page.getByTestId("language-mismatch");
    await expect(warn).toBeVisible();
    await expect(page.getByTestId("form-error")).toHaveCount(0);
    await page.locator("#in-duration").fill("60");
    await sign(page, "in-signature");
    await page.getByTestId("save-induction").click();
    await expect(page).toHaveURL(/\/inductions\/[0-9a-f-]{36}/);
    await expect(page.getByTestId("language-mismatch")).toBeVisible();
  });

  test("WK: the worker's eligibility for Z-TWB reflects the new induction; the access card has a QR and printed ref", async ({ page }) => {
    // The access card is issued once the site general induction is passed (recorded here through the API).
    const api = await apiAs(USERS.faisal);
    const ids = await projectIds(api);
    const found = await getJson<{ items: { id: string; worker_no: string }[] }>(api, `/api/v1/workers?project_id=${ids.pid}&q=${workerNo}`);
    const worker = found.items.find((w) => w.worker_no === workerNo);
    expect(worker).toBeTruthy();
    await recordInduction(api, ids.pid, worker!.id, await ensureGenCourse(api, ids.pid));
    await login(page, USERS.faisal);
    await page.goto(`/en/workers?q=${workerNo}`);
    await page.locator(`[data-testid=worker-row][data-worker-no='${workerNo}'] a`).first().click();
    await expect(page.getByTestId("worker-inductions")).toContainText(code);
    await expect(page.getByTestId("access-card")).toBeVisible();
    await expect(page.getByTestId("printed-ref")).not.toBeEmpty();
    await expect(page.getByTestId("access-card").locator("svg, img").first()).toBeVisible();
  });

  test("WK: a contractor rep only sees their own contractor's workers", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const ids = await projectIds(api);
    const other = await createWorker(api, ids, `Najd Hidden ${uid()}`, "NAJD");
    await login(page, USERS.ahmed);
    await page.goto(`/en/workers?q=${other.worker_no}`);
    await expect(page.getByTestId("worker-row")).toHaveCount(0);
  });
});
