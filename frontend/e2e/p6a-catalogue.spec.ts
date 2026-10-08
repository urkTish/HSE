import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Fitness catalogue: codes, clinics and examiners (6a §3.1–3.3). */
test.describe("Fitness catalogue", () => {
  test("codes, clinics and examiners; the clinic detail shows its examiners", async ({ page }) => {
    await openAs(page, USERS.faisal, "/fitness-codes");
    await expect(page.locator('[data-testid="fitness-code-row"][data-code="WAH-FIT"]')).toBeVisible();
    await expect(page.getByTestId("new-fitness-code")).toBeVisible();

    await page.goto("/en/medical-providers");
    await expect(page.locator('[data-testid="med-provider-row"][data-code="QUICKMED"]').getByTestId("med-provider-status")).toHaveAttribute("data-status", "suspended");
    await page.locator('[data-testid="med-provider-row"][data-code="SALAMA"]').getByRole("link").first().click();
    await expect(page).toHaveURL(/\/medical-providers\/[0-9a-f-]{36}$/);
    await expect(page.getByText("EXR-0003")).toBeVisible();

    await page.goto("/en/medical-examiners");
    await expect(page.locator('[data-testid="examiner-row"][data-no="EXR-0001"]')).toContainText("Huda");
  });

  test("a contractor rep sees the catalogue read-only", async ({ page }) => {
    await openAs(page, USERS.ahmed, "/fitness-codes");
    await expect(page.locator('[data-testid="fitness-code-row"][data-code="GEN-FIT"]')).toBeVisible();
    await expect(page.getByTestId("new-fitness-code")).toHaveCount(0);
    await page.goto("/en/medical-providers");
    await expect(page.getByTestId("new-med-provider")).toHaveCount(0);
  });

  test("OH practitioner sees the examiner licence; nav lists the occupational health section", async ({ page }) => {
    await openAs(page, USERS6.huda, "/medical-examiners");
    await expect(page.locator('[data-testid="examiner-row"][data-no="EXR-0002"]')).toContainText("SCFHS-TEST");
    await expect(page.getByTestId("nav-medical")).toBeVisible();
    await expect(page.getByTestId("nav-fitness-assessments")).toBeVisible();
  });
});
