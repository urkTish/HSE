import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Fitness holds and referrals (6a §4.4–4.5, FH/FR). */
test.describe("Holds and referrals", () => {
  test("the officer sees Sunil's active hold and open referral without clinical detail and cannot cancel", async ({ page }) => {
    await openAs(page, USERS.noura, "/fitness-holds?status=active");
    const hold = page.locator('[data-testid="hold-row"][data-no="MFH-ANIA-EXP-2026-00027"]');
    await expect(hold).toHaveAttribute("data-status", "active");
    await expect(hold.getByTestId("hold-reason")).toHaveCount(0);
    await expect(hold.getByTestId("hold-cancel")).toHaveCount(0);

    await page.goto("/en/fitness-referrals");
    const ref = page.locator('[data-testid="referral-row"][data-no="MFR-ANIA-EXP-2026-00031"]');
    await expect(ref).toHaveAttribute("data-status", "open");
    await expect(ref.getByTestId("referral-note")).toHaveCount(0);
  });

  test("the OH practitioner sees the referral note and can place a hold", async ({ page }) => {
    await openAs(page, USERS6.huda, "/fitness-referrals");
    const ref = page.locator('[data-testid="referral-row"][data-no="MFR-ANIA-EXP-2026-00031"]');
    await expect(ref.getByTestId("referral-note")).toContainText("Dizzy");
    await expect(ref.getByTestId("referral-assess")).toBeVisible();
    await page.goto("/en/fitness-holds");
    await expect(page.locator('[data-testid="hold-row"][data-no="MFH-ANIA-EXP-2026-00027"]').getByTestId("hold-reason")).toBeVisible();
    await expect(page.getByTestId("place-hold")).toBeVisible();
  });
});
