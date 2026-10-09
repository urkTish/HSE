import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Environmental overview band and action panel, K-118…K-126 and settings (6e §6, §7, §8; 202, 213). */
test.describe("Environmental overview, KPIs and settings", () => {
  test("Noura sees the Environmental nav, the band and the action panel", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-overview");
    await expect(page.getByTestId("nav-env")).toBeVisible();
    const band = page.getByTestId("env-band");
    await expect(band.getByTestId("band-tile")).toHaveCount(6);
    await expect(band.locator('[data-testid="band-tile"][data-kind="expiring_permits"]').getByTestId("band-value")).toHaveText("1");
    await expect(band.locator('[data-testid="band-tile"][data-kind="haz_storage_due"]').getByTestId("band-value")).toHaveText("1");
    await expect(page.getByTestId("overview-reading")).toBeVisible();
  });

  test("September KPIs for ANIA-EXP match the seed, with the K-120 target note", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-kpis?period=month&anchor=2026-09-15");
    const tile = (k: string) => page.locator(`[data-testid="ek-tile"][data-metric="${k}"]`).getByTestId("ek-value");
    await expect(tile("K-119")).toHaveText("717.4");
    await expect(tile("K-120")).toHaveText("89.5 %");
    await expect(tile("K-122")).toHaveText("96.9 %");
    await expect(tile("K-124")).toHaveText("4");
    await expect(tile("K-126")).toHaveText("6,960");
    await expect(page.getByTestId("ek-note").first()).toHaveText("K-120 target: 70.0 %");
    await expect(page.getByTestId("ek-breakdown")).toBeVisible();

    await page.goto("/ar/env-kpis?period=month&anchor=2026-09-15");
    await expect(page.getByTestId("ek-note").first()).toContainText("مستهدف K-120");
  });

  test("only the HSE Manager edits the settings (213)", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-settings");
    await expect(page.getByTestId("settings-readonly")).toBeVisible();
    await expect(page.getByTestId("es-save")).toHaveCount(0);

    await openAs(page, USERS.faisal, "/env-settings");
    await page.getByTestId("es-exceedance_review_days").fill("2");
    await page.getByTestId("es-save").click();
    await expect(page.getByText("Settings saved")).toBeVisible();
  });
});
