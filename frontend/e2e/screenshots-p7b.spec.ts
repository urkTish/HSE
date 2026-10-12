import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { pinProject } from "./p6a-helpers";

// Option 7b (Prototype) demo screenshots: writes to docs/screenshots/phase-7b only with SCREENSHOTS=1 (fresh seed);
// otherwise the run is skipped. SHOT_DIR overrides the folder (e.g. test-results/shots).
const OUT = process.env.SHOT_DIR ?? join(__dirname, "..", "..", "docs", "screenshots", "phase-7b");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(600_000);

async function shot(page: Page, name: string, fullPage = true) {
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

type V = { id: string; vehicle_no: string };
type A = { id: string; worker: { worker_no: string } };

for (const locale of ["en", "ar"] as const) {
  test(`option 7b screens (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    const api = await apiAs(USERS.faisal);
    const pid = await projectId(api, "ANIA-EXP");
    const veh = await getJson<{ items: V[] }>(api, `/api/v1/projects/${pid}/site-vehicles?page_size=200`);
    const vid = (no: string) => veh.items.find((v) => v.vehicle_no === no)?.id ?? "";
    const auths = await getJson<{ items: A[] }>(api, `/api/v1/projects/${pid}/driver-authorisations?page_size=200`);
    const jomar = auths.items.find((a) => a.worker.worker_no === "WKR-000003")?.id ?? "";
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.faisal, locale);
    await pinProject(page, "ANIA-EXP");

    await go("/site-vehicles");
    await expect(page.getByTestId("sv-vehicle-row").first()).toBeVisible();
    await shot(page, `01-site-vehicles-${locale}.png`);
    await go(`/site-vehicles/${vid("VEH-0107")}`);
    await expect(page.getByTestId("sv-vehicle-detail")).toBeVisible();
    await shot(page, `02-vehicle-docs-expiring-${locale}.png`);
    await go(`/site-vehicles/${vid("VEH-0119")}`);
    await expect(page.getByTestId("sv-not-certified")).toBeVisible();
    await shot(page, `03-vehicle-not-certified-${locale}.png`);
    await go("/site-vehicles/authorisations");
    await expect(page.getByTestId("sv-auth-row").first()).toBeVisible();
    await shot(page, `04-authorisations-${locale}.png`);
    await go(`/site-vehicles/authorisations/${jomar}`);
    await expect(page.getByTestId("sv-auth-detail")).toBeVisible();
    await shot(page, `05-authorisation-detail-${locale}.png`);
    await go("/site-vehicles/checks");
    await expect(page.getByTestId("sv-missing")).toBeVisible();
    await shot(page, `06-pre-use-checks-${locale}.png`);
    await go(`/site-vehicles/checks/new?vehicle=${vid("VEH-0105")}`);
    await expect(page.getByTestId("pu-item").first()).toBeVisible();
    await page.getByTestId("pu-all-ok").click();
    const item = page.getByTestId("pu-item").nth(1);
    const code = (await item.getAttribute("data-code")) ?? "";
    await page.getByTestId(`pu-fail-${code}`).click();
    await expect(item).toHaveAttribute("data-state", "non_compliant");
    await page.getByTestId(`pu-note-${code}`).fill(locale === "ar" ? "المقود ثقيل ويسحب إلى اليسار" : "Steering pulls hard to the left");
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, `07-pre-use-form-${locale}.png`);
    await go(`/site-vehicles/journeys/new?vehicle=${vid("VEH-0101")}`);
    await page.getByTestId("jp-dest").fill(locale === "ar" ? "ميناء الدمام" : "Dammam port gate 3");
    await page.getByTestId("jp-km").fill("160");
    await page.getByTestId("jp-depart").fill("2026-10-07T04:30");
    await page.getByTestId("jp-arrive-at").fill("2026-10-07T07:00");
    await expect(page.getByTestId("jp-hint")).toBeVisible();
    await shot(page, `08-journey-form-hint-${locale}.png`);
    await go("/site-vehicles/journeys");
    await expect(page.getByTestId("sv-journey-row").first()).toBeVisible();
    await shot(page, `09-journeys-${locale}.png`);
    await go("/site-vehicles/settings");
    await expect(page.getByTestId("sv-settings")).toBeVisible();
    await shot(page, `10-settings-${locale}.png`);
    await go("");
    const tiles = page.getByTestId("sv-tiles");
    await expect(tiles).toBeVisible();
    await tiles.scrollIntoViewIfNeeded();
    await shot(page, `11-dashboard-tiles-${locale}.png`, false);

    // Viewer: aggregates only.
    await page.context().clearCookies();
    await login(page, USERS.sarah, locale);
    await pinProject(page, "ANIA-EXP");
    await go("/site-vehicles");
    await expect(page.getByTestId("sv-aggregates-only")).toBeVisible();
    await shot(page, `12-viewer-aggregates-${locale}.png`);

    // Phone (390 px): compact cards and the pre-use form as a driver would see it.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.context().clearCookies();
    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");
    await go("/site-vehicles");
    await expect(page.getByTestId("sv-vehicle-row").first()).toBeVisible();
    await shot(page, `13-site-vehicles-390-${locale}.png`);
    await go(`/site-vehicles/checks/new?vehicle=${vid("VEH-0102")}`);
    await expect(page.getByTestId("pu-item").first()).toBeVisible();
    await shot(page, `14-pre-use-form-390-${locale}.png`);
    await go("/site-vehicles/journeys");
    await expect(page.getByTestId("sv-journey-row").first()).toBeVisible();
    await shot(page, `15-journeys-390-${locale}.png`);
  });
}
