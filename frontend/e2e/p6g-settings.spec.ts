import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Scorecard settings and profile versions (6g §3.1 SP-1…SP-5, §8 settings; AC 1, 2, 5, 52). */
test.describe("Scorecard settings", () => {
  test("Noura (officer) has no settings menu or page", async ({ page }) => {
    await openAs(page, USERS.noura, "/scorecard-settings");
    await expect(page.getByText("Not available to your role")).toBeVisible();
    await expect(page.getByTestId("nav-sc-settings")).toHaveCount(0);
    await expect(page.getByTestId("sc-settings")).toHaveCount(0);
  });

  test("Faisal: an out-of-range value is refused, a valid one saves", async ({ page }) => {
    await openAs(page, USERS.faisal, "/scorecard-settings");
    const exposure = page.getByTestId("ss-scorecard_min_exposure_hours");
    const original = await exposure.inputValue();
    await exposure.fill("20000");
    await page.getByTestId("ss-save").click();
    await expect(page.getByText("This value is outside the allowed range.")).toBeVisible();
    await exposure.fill(String(Number(original) + 10000));
    await page.getByTestId("ss-save").click();
    await expect(page.getByText("This value is outside the allowed range.")).toHaveCount(0);
    await page.reload();
    await expect(exposure).toHaveValue(String(Number(original) + 10000));
    await exposure.fill(original);
    await page.getByTestId("ss-save").click();
    await page.reload();
    await expect(exposure).toHaveValue(original);
  });

  test("Faisal: a draft profile must weigh 100 and cannot start in a Final month (SP-1, SP-4)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/scorecard-settings");
    await expect(page.locator('[data-testid="sp-item"][data-status="active"]')).toHaveCount(1);
    if ((await page.locator('[data-testid="sp-item"][data-status="draft"]').count()) === 0) {
      await page.getByTestId("sp-new").click();
      await page.getByTestId("sp-create-confirm").click();
    }
    await expect(page.getByTestId("sp-editor")).toHaveAttribute("data-status", "draft");
    const lag = page.getByTestId("sp-pillar-LAG");
    const weight = await lag.inputValue();
    const from = await page.getByTestId("sp-from").inputValue();

    await lag.fill(String(Number(weight) + 5));
    await expect(page.getByTestId("sp-sum")).toContainText("105.0");
    await page.getByTestId("sp-save").click();
    await expect(page.getByTestId("sp-activate")).toBeEnabled();
    await page.getByTestId("sp-activate").click();
    await expect(page.getByText("The pillar weights must add up to exactly 100.")).toBeVisible();

    await lag.fill(weight);
    await page.getByTestId("sp-from").fill("2026-08");
    await page.getByTestId("sp-save").click();
    await expect(page.getByTestId("sp-activate")).toBeEnabled();
    await page.getByTestId("sp-activate").click();
    await expect(page.getByText("The profile cannot start in a month that is already Final.")).toBeVisible();

    await page.getByTestId("sp-from").fill(from);
    await page.getByTestId("sp-save").click();
    await expect(page.getByTestId("sp-activate")).toBeEnabled();
    await expect(page.locator('[data-testid="sp-item"][data-status="active"]')).toHaveCount(1);
  });
});
