import { expect, test } from "./fixtures/test";
import { apiAs, login, USERS } from "./helpers";
import { deploymentOf } from "./p5-helpers";

/** Worker training panel, passport, data-subject report and training profile (5-training §5.6, §5.17, §7; AC35, AC143). */
test.describe("Worker training passport", () => {
  test("Worker page shows requirements and the passport for Imran Hussain; the deployment card shows the matrix state", async ({ page }) => {
    const imran = await deploymentOf("ANIA-EXP", "WKR-000001");
    await login(page, USERS.noura);
    await page.goto(`/en/workers/${imran.worker_id}`);
    const panel = page.getByTestId("training-passport");
    await expect(panel).toBeVisible();
    await expect(panel.locator('[data-testid="passport-entry"][data-course="WAH"]')).toHaveAttribute("data-in-force", "yes");
    await expect(page.locator('[data-testid="requirement-row"][data-course="WAH"]').first()).toHaveAttribute("data-state", /met|expiring/);
    await expect(page.getByTestId("deployment-training")).toBeVisible();

    await panel.getByTestId("open-passport").click();
    await expect(page).toHaveURL(new RegExp(`/workers/${imran.worker_id}/training$`));
    await expect(page.getByTestId("passport-print")).toBeVisible();
    await expect(page.locator("main")).not.toContainText(/\b[12]\d{9}\b/);
  });

  test("AC143: Faisal runs the data-subject report for Biju Thomas with his nominations", async ({ page }) => {
    const biju = await deploymentOf("ANIA-EXP", "WKR-000017");
    await login(page, USERS.faisal);
    await page.goto(`/en/workers/${biju.worker_id}`);
    await page.getByTestId("open-dsr").click();
    await expect(page).toHaveURL(new RegExp(`/workers/${biju.worker_id}/training-report$`));
    const report = page.getByTestId("dsr-report");
    await expect(report).toBeVisible();
    await expect(report.getByTestId("dsr-attendances")).toContainText("TRS-ANIA-EXP-2026-00057");
    await expect(report.getByTestId("dsr-records")).toBeVisible();
  });

  test("AC35: Ahmed adds the first_aider matrix role to a NAJD worker; a QIMMA worker is outside his scope", async ({ page }) => {
    const osman = await deploymentOf("ANIA-EXP", "WKR-000009");
    await login(page, USERS.ahmed);
    await page.goto(`/en/workers/${osman.worker_id}`);
    const profile = page.getByTestId("training-profile");
    await expect(profile).toBeVisible();
    await profile.getByTestId("edit-profile").click();
    await page.getByTestId("pf-roles").getByLabel("First aider").check();
    await page.getByTestId("save-profile").click();
    await expect(profile.getByTestId("profile-roles")).toContainText("First aider");

    const joel = await deploymentOf("RBT-52", "WKR-000108");
    const ahmed = await apiAs(USERS.ahmed);
    const res = await ahmed.patch(`/api/v1/deployments/${joel.id}/training-profile`, { data: { matrix_roles: ["first_aider"] } });
    expect([403, 404]).toContain(res.status());
  });
});
