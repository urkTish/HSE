import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";

/** Training providers against the Appendix A seed (5-training §3.2, §4.1, §5.3; AC11, AC12, AC13, AC15). */
test.describe("Training providers", () => {
  test("AC11: the HSE Officer creates and submits a provider but cannot approve it; the HSE Manager approves it", async ({ page }) => {
    const code = `TU-${uid()}`;
    await login(page, USERS.noura);
    await page.goto("/en/training-providers");
    await page.getByTestId("new-provider").click();
    await page.getByTestId("prov-code").fill(code);
    await page.getByTestId("prov-kind").selectOption("internal");
    await page.getByTestId("prov-name-en").fill("Site HSE Training Cell (test)");
    await page.getByTestId("prov-name-ar").fill("خلية تدريب السلامة بالموقع (تجريبي)");
    await page.getByTestId("save-provider").click();
    await expect(page).toHaveURL(/\/training-providers\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("provider-status").first()).toHaveAttribute("data-status", "draft");
    await page.getByTestId("provider-submit").click();
    await page.getByTestId("provider-confirm").click();
    await expect(page.getByTestId("provider-status").first()).toHaveAttribute("data-status", "pending_approval");
    await expect(page.getByTestId("provider-approve")).toHaveCount(0);
    const url = page.url().replace(/^https?:\/\/[^/]+/, "");

    await login(page, USERS.faisal);
    await page.goto(url);
    await page.getByTestId("provider-approve").click();
    await page.getByTestId("provider-confirm").click();
    await expect(page.getByTestId("provider-status").first()).toHaveAttribute("data-status", "approved");
    await expect(page.getByTestId("provider-accepted")).toBeVisible();
  });

  test("AC12/AC13/AC15: accreditations count only when the register was checked; acceptability follows the accreditation and suspension dates", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-providers");
    await page.locator('[data-testid="provider-row"][data-code="HAYAT"]').getByRole("link").first().click();
    await expect(page.getByTestId("accreditation-row").first()).toHaveAttribute("data-counts", "yes");

    // HAYAT srca/aha valid to 2027-06-30: FIRST-AID completed that day is acceptable, the day after is not.
    const card = page.getByTestId("acceptability");
    await card.locator("select").first().selectOption("FIRST-AID");
    await card.locator('input[type="date"]').fill("2027-06-30");
    await card.getByTestId("acc-check").click();
    await expect(card.getByTestId("acceptability-result").locator("li").first()).toHaveAttribute("data-acceptable", "yes");
    await card.locator('input[type="date"]').fill("2027-07-01");
    await card.getByTestId("acc-check").click();
    await expect(card.getByTestId("acceptability-result").locator("li").first()).toHaveAttribute("data-reason", "ACCREDITATION_INVALID");

    // QUICKTRAIN: the claimed accreditation was never register-checked, and the provider is suspended from 2026-09-22.
    await page.goto("/en/training-providers");
    await page.locator('[data-testid="provider-row"][data-code="QUICKTRAIN"]').getByRole("link").first().click();
    await expect(page.getByTestId("provider-status").first()).toHaveAttribute("data-status", "suspended");
    await expect(page.getByTestId("accreditation-row").first()).toHaveAttribute("data-counts", "no");
    await page.getByTestId("acceptability").locator("select").first().selectOption("FIRST-AID");
    await page.getByTestId("acceptability").locator('input[type="date"]').fill("2026-09-22");
    await page.getByTestId("acc-check").click();
    await expect(page.getByTestId("acceptability-result").locator("li").first()).toHaveAttribute("data-acceptable", "no");
  });
});
