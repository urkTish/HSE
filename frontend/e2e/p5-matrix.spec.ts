import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";
import { pickMulti } from "./p2-helpers";

/** Training matrix against the Appendix A seed (5-training §3.4, §5.5, TR7; AC28, AC29, AC30, AC32, AC33). */
test.describe("Training matrix", () => {
  test("AC28: the WAH line on ANIA-EXP as of 2026-09-30 counts 519 requirements, 507 met or expiring and 12 gaps", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-matrix?as_of=2026-09-30");
    const wah = page.locator('[data-testid="matrix-line"][data-line="MXL-ANIA-EXP-003"]');
    await expect(wah).toBeVisible();
    await expect(wah).toContainText("519");

    await page.goto("/en/training-gaps?as_of=2026-09-30");
    const row = page.getByTestId("gap-byCourse").locator('tr[data-key="WAH"]');
    await expect(row.locator("td").nth(1)).toHaveText("519");
    await expect(row.locator("td").nth(2)).toHaveText("12");
  });

  test("AC29/AC30: hook-derived lines are read-only and enforcement-only crew lines are not counted", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-matrix");
    const hook = page.locator('[data-testid="matrix-line"][data-source="hook"]');
    await expect(hook.first()).toBeVisible();
    await expect(hook.first().getByTestId("line-hook")).toBeVisible();
    await expect(hook.getByTestId("edit-line")).toHaveCount(0);
    await expect(page.locator('[data-testid="matrix-line"][data-source="hook"][data-counted="no"]').first()).toBeVisible();
    await expect(page.locator('[data-testid="matrix-line"][data-line="MXL-ANIA-EXP-001"]').getByTestId("edit-line")).toBeVisible();
  });

  test("AC32: an any-of group of two hook codes is refused", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-matrix");
    await page.getByTestId("new-matrix-line").click();
    await page.getByTestId("mx-kind-in").selectOption("trade");
    await pickMulti(page, "mx-values", ["Scaffolder"]);
    await page.getByTestId("mx-any-of").check();
    await pickMulti(page, "mx-anyof-in", [/^WAH —/, /^SCAFF-AWR —/]);
    await page.getByTestId("save-line").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "ANY_OF_NOT_ALLOWED");
  });

  test("AC33: the HSE Officer cannot remove a mandatory line (loosening is for the HSE Manager)", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-matrix");
    await page.locator('[data-testid="matrix-line"][data-line="MXL-ANIA-EXP-002"]').getByTestId("remove-line").click();
    await page.getByTestId("mx-rm-reason").fill("Heat stress awareness is covered by the toolbox talks now");
    await page.getByTestId("remove-line-confirm").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "MATRIX_LOOSENING");
  });
});
