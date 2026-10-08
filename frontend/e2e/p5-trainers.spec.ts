import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";

async function fillAuthorisation(page: import("@playwright/test").Page, who: string, to: string): Promise<void> {
  await page.goto("/en/trainer-authorisations");
  await page.getByTestId("new-trainer").click();
  await selectContaining(page.getByTestId("ta-user"), who);
  await selectContaining(page.getByTestId("ta-provider"), "INT-HSE");
  await pickMulti(page, "ta-courses", [/^HEAT-AWR/]);
  await page.getByTestId("ta-basis").fill("Completed the train-the-trainer course and five years of site HSE delivery.");
  await page.getByTestId("ta-from").fill("2026-10-06");
  await page.getByTestId("ta-to").fill(to);
}

/** Trainer authorisations against the Appendix A seed (5-training §3.3, §5.4; AC20, AC22). */
test.describe("Trainer authorisations", () => {
  test("AC20: the HSE Officer cannot authorise herself as a trainer", async ({ page }) => {
    await login(page, USERS.noura);
    await fillAuthorisation(page, "Noura", "2027-06-30");
    await page.getByTestId("save-trainer").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "SOD_CONFLICT");
  });

  test("AC22: an authorisation longer than 24 months is refused; the seed register lists the four authorisations", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/trainer-authorisations");
    await expect(page.locator('[data-testid="trainer-row"][data-no="TA-ANIA-EXP-0001"]')).toBeVisible();
    await expect(page.locator('[data-testid="trainer-row"][data-no="TA-ANIA-EXP-0003"]')).toBeVisible();
    await fillAuthorisation(page, "Noura", "2028-10-06");
    await page.getByTestId("save-trainer").click();
    await expect(page.getByTestId("form-error")).toBeVisible();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", /VALIDATION_ERROR|AUTHORISATION_TOO_LONG|TRAINER/);
  });
});
