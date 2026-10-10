import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Generic exports, export log, subscriptions, register entry points and the dashboard PDF (6g §3.10 EX-1…EX-11; AC 46–53). */
test.describe("Exports", () => {
  test("Incidents with names needs a purpose; with GOSI it runs and is logged (EX-4, EX-5)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/exports?dataset=incidents");
    await expect(page.locator('[data-testid="xp-column"][data-column="nationality"] input')).toBeDisabled();
    await page.locator('[data-testid="xp-column"][data-column="person_name"] input').check();
    await expect(page.getByTestId("xp-subscribe")).toBeDisabled();
    await page.getByTestId("xp-run").click();
    await expect(page.getByText("Choose a purpose for this export.")).toBeVisible();
    await page.getByTestId("xp-purpose").selectOption("gosi");
    await page.getByTestId("xp-run").click();
    await expect(page.getByTestId("xp-form").getByTestId("xp-download")).toBeVisible();
    const job = page.locator('[data-testid="xp-job"][data-dataset="incidents"]').first();
    await expect(job).toHaveAttribute("data-status", "ready");
    await expect(job).toContainText("GOSI");
  });

  test("Heat patrols: default export runs, a weekly subscription is added and removed (EX-9)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/exports?dataset=heat_patrols");
    await page.getByTestId("xp-run").click();
    await expect(page.getByTestId("xp-form").getByTestId("xp-download")).toBeVisible();
    await page.getByTestId("xp-subscribe").click();
    const sub = page.locator('[data-testid="xp-subscription"][data-dataset="heat_patrols"]');
    await expect(sub).toHaveCount(1);
    await sub.getByTestId("xp-unsubscribe").click();
    await expect(sub).toHaveCount(0);
  });

  test("The ban-patrol register offers a quick export; the dashboard prints to PDF (EX-1, EX-11)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/ban-patrols");
    const entry = page.getByTestId("registry-export");
    await expect(entry).toBeVisible();
    const csv = page.waitForEvent("download");
    await entry.getByTestId("export-csv").click();
    expect((await csv).suggestedFilename()).toMatch(/\.csv$/);
    await entry.getByTestId("registry-export-more").click();
    await expect(page.getByTestId("xp-form")).toBeVisible();

    await page.goto("/en");
    const pdf = page.waitForEvent("download");
    await page.getByTestId("dashboard-print").click();
    expect((await pdf).suggestedFilename()).toMatch(/\.pdf$/);
  });

  test("Ramesh only sees the datasets he may export and has no dashboard print (EX-2)", async ({ page }) => {
    await openAs(page, USERS.ramesh, "/");
    await expect(page.getByTestId("dashboard-print")).toHaveCount(0);
    await page.getByTestId("nav-xp-exports").click();
    await expect(page.getByTestId("xp-dataset")).toBeVisible();
    await expect(page.getByTestId("xp-dataset").locator('option[value="incidents"]')).toHaveCount(0);
  });
});
