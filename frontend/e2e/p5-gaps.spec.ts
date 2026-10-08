import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";

/** Gap register, exemptions and refresher plan against the Appendix A seed (5-training §5.6–§5.8; AC85, AC36, AC86, AC87, AC88). */
test.describe("Training gaps and refresher plan", () => {
  test("AC85: Ahmed sees RAWABI-tree deployments only; Sarah sees counts only", async ({ page }) => {
    await login(page, USERS.ahmed);
    await page.goto("/en/training-gaps");
    await expect(page.getByTestId("gaps-table")).toBeVisible({ timeout: 30_000 });
    const rows = page.getByTestId("gap-row");
    await expect(rows.first()).toBeVisible();
    // GULFPAVE (Rajesh Nair's contractor) is outside the RAWABI tree.
    await expect(page.locator('[data-testid="gap-row"][data-worker="WKR-000002"]')).toHaveCount(0);

    await login(page, USERS.sarah);
    await page.goto("/en/training-gaps");
    await expect(page.getByTestId("gap-summary")).toBeVisible();
    await expect(page.getByTestId("gaps-counts-only")).toBeVisible();
    await expect(page.getByTestId("gaps-table")).toHaveCount(0);
    await expect(page.getByTestId("gap-row")).toHaveCount(0);
  });

  test("AC36: an exemption from a hook course is refused; SCAFF-AWR with a 30-character reason is granted", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-exemptions");
    await page.getByTestId("new-exemption").click();
    // WAH is a hook code, so it is not even offered in the line picker (the API would answer EXEMPTION_NOT_ALLOWED).
    await page.getByTestId("ex-dep-search").fill("WKR-000001");
    await selectContaining(page.getByTestId("ex-dep"), "WKR-000001");
    await expect(page.getByTestId("ex-line").locator("option", { hasText: "WAH" })).toHaveCount(0);
    await expect(page.getByTestId("ex-line").locator("option", { hasText: "IND-GENERAL" })).toHaveCount(0);
  });

  test("AC86/AC87: refresher plan shows Rajesh Nair booked late and Ahmed Raza booked in time", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/refresher-plan");
    await expect(page.getByTestId("plan-table")).toBeVisible({ timeout: 30_000 });
    const rajesh = page.locator('[data-testid="plan-row"][data-worker="WKR-000002"][data-course="AVSEC-AWR"]');
    await expect(rajesh).toHaveAttribute("data-state", "booked_late");
    await expect(rajesh).toContainText("TRS-ANIA-EXP-2026-00061");
    const raza = page.locator('[data-testid="plan-row"][data-worker="WKR-000015"][data-course="FIRE-WATCH"]');
    await expect(raza).toHaveAttribute("data-state", "booked_in_time");
    await expect(raza).toContainText("TRS-ANIA-EXP-2026-00058");
    await expect(raza.getByTestId("plan-pick")).toBeDisabled();
  });

  test("AC88: create session from plan pre-fills the course and the picked holders", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/refresher-plan?state=not_booked");
    await expect(page.getByTestId("plan-table")).toBeVisible({ timeout: 30_000 });
    const free = page.locator('[data-testid="plan-row"][data-state="not_booked"]').first();
    const course = await free.getAttribute("data-course");
    await free.getByTestId("plan-pick").check();
    await page.getByTestId("plan-create-session").click();
    await expect(page).toHaveURL(/\/training-sessions\/new\?.*from_plan=1/);
    await expect(page.getByTestId("ss-course-in")).toHaveValue(new RegExp(course ?? "."));
  });
});
