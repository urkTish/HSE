import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";

/** Course catalogue against the Appendix A seed (5-training §3.1, §5.2; AC1, AC4, AC5, AC10). */
test.describe("Training course catalogue", () => {
  test("AC1: a Phase 4 certificate code cannot become a training course; an existing code is refused as a duplicate", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/training-courses");
    await expect(page.getByTestId("course-row").first()).toBeVisible();
    await expect(page.locator('[data-testid="course-row"][data-code="GAS-TEST"]')).toBeVisible();

    await page.getByTestId("new-course").click();
    await page.getByTestId("course-code").fill("GAS-TESTER");
    await page.getByTestId("course-name-en").fill("Gas tester (duplicate of a Phase 4 code)");
    await page.getByTestId("course-name-ar").fill("فاحص الغاز");
    await page.getByTestId("course-min-hours").fill("4");
    await page.getByTestId("save-course").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "CODE_IN_OTHER_CATALOGUE");

    await page.getByTestId("course-code").fill("GAS-TEST");
    await page.getByTestId("save-course").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", /DUPLICATE|CONFLICT|EXISTS/);
  });

  test("AC4: the HSE Officer reads the catalogue but cannot edit a course", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-courses/WAH");
    await expect(page.locator("h1")).toContainText("WAH");
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("edit-course")).toHaveCount(0);
    await page.goto("/en/training-courses");
    await expect(page.getByTestId("new-course")).toHaveCount(0);
  });

  test("AC5/AC10: a longer WAH validity is refused (tighten only); a course in use cannot be deleted", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/training-courses/WAH");
    await expect(page.getByTestId("edit-course")).toBeVisible();
    await expect(page.getByTestId("delete-course")).toHaveCount(0);
    await page.getByTestId("edit-course").click();
    await page.getByTestId("course-validity-months").fill("36");
    await page.getByTestId("course-reason").fill("Trying to extend WAH validity to 36 months");
    await page.getByTestId("save-course").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "CATALOGUE_LOOSENING");
  });
});
