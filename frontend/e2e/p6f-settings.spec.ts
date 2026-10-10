import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Rule profile and 6f settings: tighten-only, HSE Manager only (6f §3.1, §3.10, NR-3; AC 6, 46). */
test.describe("Notification rules and follow-up settings", () => {
  test("Noura reads the profile; only Faisal edits", async ({ page }) => {
    await openAs(page, USERS.noura, "/followup-settings");
    await expect(page.getByTestId("fu-settings-readonly")).toBeVisible();
    await expect(page.locator('[data-testid="rule-row"][data-rule="GOSI-W"]')).toBeVisible();
    await expect(page.getByTestId("rule-edit")).toHaveCount(0);
    await expect(page.getByTestId("fs-save")).toHaveCount(0);
  });

  test("statutory GOSI-W can be lowered, not raised; settings only tighten", async ({ page }) => {
    await openAs(page, USERS.faisal, "/followup-settings");
    const row = page.locator('[data-testid="rule-row"][data-rule="GOSI-W"]');
    await row.getByTestId("rule-edit").click();
    await page.getByTestId("rule-hours-input").fill("96");
    await page.getByTestId("rule-save").click();
    await expect(page.getByText("Statutory rules can only be tightened")).toBeVisible();
    await page.getByTestId("rule-hours-input").fill("48");
    await page.getByTestId("rule-save").click();
    await expect(row.getByTestId("rule-hours")).toHaveText("48 hours");

    await page.getByTestId("fs-lesson_ack_days").fill("10");
    await page.getByTestId("fs-save").click();
    await expect(page.getByText("Settings can only be tightened.")).toBeVisible();
    await page.getByTestId("fs-lesson_ack_days").fill("5");
    await page.getByTestId("fs-save").click();
    await expect(page.getByText("Settings saved")).toBeVisible();
  });
});
