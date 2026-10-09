import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

/** Acclimatisation plans and rest-station welfare checks (6b §5–6, AC33–34, AC38). */
test.describe("Acclimatisation and welfare", () => {
  test("Noura sees Ganesh's plan waiting on the restriction with its hold reference (HS4d, P6b-3)", async ({ page }) => {
    await openAs(page, USERS.noura, "/acclimatisation-plans");
    const row = page.locator('[data-testid="plan-row"][data-no="ACP-ANIA-EXP-2026-00412"]');
    await expect(row).toHaveAttribute("data-status", "waiting_restriction");
    await expect(row).toHaveAttribute("data-type", "post_heat_illness");
    await row.getByTestId("plan-link").click();
    await expect(page).toHaveURL(/\/acclimatisation-plans\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("plan-waiting")).toBeVisible();
    await expect(page.getByTestId("plan-trigger-ref")).toContainText("MFH-ANIA-EXP-2026-00019");
  });

  test("Omar checks RS-SAIR-01 with HW05 failed: a corrective action is raised", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS.omar, "/heat-welfare-checks/new");
    await selectContaining(page.getByTestId("wc-station"), "RS-SAIR-01");
    await page.getByTestId("wc-water").fill("12.5");
    await page.getByTestId("wc-all-pass").click();
    await page.getByTestId("wc-HW05-fail").click();
    await page.getByTestId("wc-save").click();
    await expect(page.getByTestId("check-saved")).toHaveAttribute("data-critical", "yes");
    await expect(page.getByTestId("check-ca")).toContainText("CA-");
  });
});
