import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";
import { pinProject } from "./p6a-helpers";

// Phase 6b demo screenshots for docs/screenshots/phase-6b (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6b");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(600_000);

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

for (const locale of ["en", "ar"] as const) {
  test(`Phase 6b screenshots (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const plans = await getJson<{ items: { id: string; plan_no: string }[] }>(api, `/api/v1/projects/${pid}/acclimatisation-plans?status=waiting_restriction&page_size=5`);
    const log = await getJson<{ items: { id: string; entry_no: string }[] }>(api, `/api/v1/projects/${pid}/heat-illness-log?page_size=50`);
    const plan = plans.items.find((p) => p.plan_no === "ACP-ANIA-EXP-2026-00412");
    const entry = log.items.find((e) => e.entry_no === "HIL-ANIA-EXP-2026-014");
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");

    await go("/heat-board");
    await expect(page.getByTestId("zone-card").first()).toBeVisible();
    await shot(page, `01-heat-board-${locale}.png`, true);

    await go("/wbgt-readings");
    await expect(page.getByTestId("reading-row").first()).toBeVisible();
    await shot(page, `02-wbgt-readings-${locale}.png`);

    await go("/wbgt-readings/new");
    await expect(page.getByTestId("rd-point")).toBeVisible();
    await shot(page, `03-reading-entry-${locale}.png`, true);

    await go("/heat-duty-list");
    await expect(page.getByTestId("duty-not-for-heat")).toBeVisible();
    await shot(page, `04-heat-duty-list-${locale}.png`, true);

    await go("/heat-instruments");
    await expect(page.getByTestId("instrument-row").first()).toBeVisible();
    await shot(page, `05-heat-instruments-${locale}.png`);

    await go("/monitoring-points");
    await expect(page.getByTestId("point-row").first()).toBeVisible();
    await shot(page, `06-monitoring-points-${locale}.png`);

    await go("/rest-stations");
    await expect(page.getByTestId("station-row").first()).toBeVisible();
    await shot(page, `07-rest-stations-${locale}.png`);

    await go("/acclimatisation-plans");
    await expect(page.getByTestId("plan-row").first()).toBeVisible();
    await shot(page, `08-acclimatisation-plans-${locale}.png`);

    if (plan) {
      await go(`/acclimatisation-plans/${plan.id}`);
      await expect(page.getByTestId("plan-waiting")).toBeVisible();
      await shot(page, `09-acclimatisation-plan-${locale}.png`, true);
    }

    await go("/heat-welfare-checks");
    await expect(page.getByTestId("check-row").first()).toBeVisible();
    await shot(page, `10-welfare-checks-${locale}.png`);

    await go("/heat-welfare-checks/new");
    await selectContaining(page.getByTestId("wc-station"), "RS-SAIR-01");
    await shot(page, `11-welfare-check-entry-${locale}.png`, true);

    await go("/ban-patrols");
    await expect(page.getByTestId("patrol-row").first()).toBeVisible();
    await shot(page, `12-ban-patrols-${locale}.png`);

    await go("/ban-exemptions");
    await expect(page.getByTestId("exemption-row").first()).toBeVisible();
    await shot(page, `13-ban-exemptions-${locale}.png`);

    await go("/heat-illness-log");
    await expect(page.getByTestId("log-row").first()).toBeVisible();
    await shot(page, `14-heat-illness-log-${locale}.png`);

    if (entry) {
      await go(`/heat-illness-log/${entry.id}`);
      await expect(page.getByTestId("log-context")).toBeVisible();
      await shot(page, `15-heat-illness-entry-${locale}.png`, true);
    }

    await go("/heat-actions");
    await expect(page.getByTestId("heat-actions")).toBeVisible();
    await shot(page, `16-heat-actions-${locale}.png`, true);

    await go("/heat-stress?period=month&anchor=2026-09-15");
    await expect(page.getByTestId("heat-tile").first()).toBeVisible({ timeout: 30_000 });
    await shot(page, `17-heat-kpis-${locale}.png`, true);

    await go("/heat-season-report?year=2026");
    await expect(page.getByTestId("season-report")).toBeVisible({ timeout: 30_000 });
    await shot(page, `18-season-report-${locale}.png`, true);

    // Phone (390 px): the board and the reading entry, for field use.
    await page.setViewportSize({ width: 390, height: 844 });
    await go("/heat-board");
    await expect(page.getByTestId("zone-card").first()).toBeVisible();
    await shot(page, `20-heat-board-phone-${locale}.png`);
    await go("/wbgt-readings/new");
    await expect(page.getByTestId("rd-point")).toBeVisible();
    await shot(page, `21-reading-entry-phone-${locale}.png`, true);
    await page.setViewportSize({ width: 1440, height: 900 });

    // The HSE Manager's settings and regime table.
    await page.context().clearCookies();
    await login(page, USERS.faisal, locale);
    await pinProject(page, "ANIA-EXP");
    await go("/heat-settings");
    await expect(page.getByTestId("regime-table")).toBeVisible();
    await shot(page, `19-heat-settings-${locale}.png`, true);
  });
}
