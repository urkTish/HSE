import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";

/** Project training settings (5-training §3.16): ranges, shorten-only validity, HSE Manager only. */
test.describe("Training settings", () => {
  test("Out-of-range values are flagged; a longer course validity is refused; a shorter one and the warning threshold are saved", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/training-settings");
    await expect(page.getByTestId("training-settings")).toBeVisible();
    await expect(page.getByTestId("training-hooks-state")).toBeVisible();

    const pct = page.getByTestId("ts-training_matrix_warning_pct");
    await pct.fill("120");
    await page.getByTestId("save-training-settings").click();
    await expect(pct).toHaveAttribute("aria-invalid", "true");
    await pct.fill("97.5");

    await page.getByTestId("ts-validity-WAH").fill("30");
    await page.getByTestId("save-training-settings").click();
    await expect(page.getByTestId("form-error")).toBeVisible();

    await page.getByTestId("ts-validity-WAH").fill("20");
    await page.getByTestId("save-training-settings").click();
    await expect(page.getByText("Training settings saved")).toBeVisible();
    await expect(page.getByTestId("form-error")).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("ts-training_matrix_warning_pct")).toHaveValue("97.5");
    await expect(page.getByTestId("ts-validity-WAH")).toHaveValue("20");
  });

  test("The HSE Officer reads the settings without editing them", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-settings");
    await expect(page.getByTestId("training-settings")).toBeVisible();
    await expect(page.getByTestId("ts-training_pass_mark_pct")).toBeDisabled();
    await expect(page.getByTestId("save-training-settings")).toHaveCount(0);
  });
});
