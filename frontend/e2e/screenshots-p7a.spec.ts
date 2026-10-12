import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { pinProject } from "./p6a-helpers";

// Option 7a demo screenshots: writes to docs/screenshots/phase-7a only with SCREENSHOTS=1 (fresh seed);
// otherwise the run is skipped. SHOT_DIR overrides the folder (e.g. test-results/shots).
const OUT = process.env.SHOT_DIR ?? join(__dirname, "..", "..", "docs", "screenshots", "phase-7a");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(600_000);

async function shot(page: Page, name: string, fullPage = true) {
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

type Item = { id: string; title: string };

for (const locale of ["en", "ar"] as const) {
  test(`option 7a screens (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    const noura = await apiAs(USERS.noura);
    const pid = await projectId(noura, "ANIA-EXP");
    const list = await getJson<{ items: Item[] }>(noura, `/api/v1/projects/${pid}/incidents?vehicle_involved=true&page_size=200`);
    const byTitle = (t: string) => list.items.find((x) => x.title.startsWith(t))?.id ?? "";
    const i0201 = byTitle("Pickup struck a private car");
    const i0215 = byTitle("Crew bus struck by a private car");
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");

    await go(`/incidents/${i0201}`);
    await expect(page.getByTestId("vehicle-section")).toBeVisible();
    await page.getByTestId("vehicle-section").scrollIntoViewIfNeeded();
    await shot(page, `01-incident-vehicles-${locale}.png`);
    await go(`/incidents/${i0215}`);
    await expect(page.getByTestId("rnc-badge").first()).toBeVisible();
    await shot(page, `02-incident-commuting-rnc-${locale}.png`);
    await go("/incidents?vehicle_involved=true");
    await expect(page.getByTestId("incident-row").first()).toBeVisible();
    await shot(page, `03-register-vehicle-filter-${locale}.png`);
    await go("/incidents?recorded_not_counted=true");
    await expect(page.getByTestId("incident-row").first()).toBeVisible();
    await shot(page, `04-register-recorded-not-counted-${locale}.png`);
    await go("?period=month&anchor=2026-09-15");
    const tile = page.locator("[data-testid=kpi-tile][data-metric='K-136']");
    await expect(tile).toBeVisible();
    await tile.scrollIntoViewIfNeeded();
    await shot(page, `05-dashboard-k136-${locale}.png`, false);
    const c41 = page.getByTestId("chart-card-C41");
    await c41.scrollIntoViewIfNeeded();
    await expect(c41.getByTestId("chart-C41")).toBeVisible();
    await shot(page, `06-dashboard-c41-${locale}.png`, false);
    await go(`/incidents/${i0201}`);
    await page.getByTestId("veh-add").click();
    await expect(page.getByTestId("veh-dialog")).toBeVisible();
    await shot(page, `07-vehicle-dialog-${locale}.png`, false);

    // Viewer: identity and report files withheld (P7a-1, VA-15).
    await page.context().clearCookies();
    await login(page, USERS.sarah, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/incidents/${i0201}`);
    await expect(page.getByTestId("vehicle-section")).toBeVisible();
    await page.getByTestId("vehicle-section").scrollIntoViewIfNeeded();
    await shot(page, `08-incident-viewer-masked-${locale}.png`);

    // Phone (390 px): compact vehicle cards and the report archive card.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.context().clearCookies();
    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/incidents/${i0201}`);
    await expect(page.getByTestId("veh-row").first()).toBeVisible();
    await page.getByTestId("vehicle-section").scrollIntoViewIfNeeded();
    await shot(page, `09-incident-vehicles-390-${locale}.png`);
    await go("/incidents?recorded_not_counted=true");
    await expect(page.getByTestId("incident-row").first()).toBeVisible();
    await shot(page, `10-register-390-${locale}.png`);
  });
}
