import { expect, test } from "./fixtures/test";
import { selectContaining } from "./p2-helpers";
import { USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Heat board, duty list and the phone-first WBGT reading entry (6b §4.1–4.3, WR-4, A.4). */
test.describe("Heat board and readings", () => {
  test("board at the clock: Z-APR-21 at 27.8 °C is R2 (HS3); the duty list names Ganesh not for heat work", async ({ page }) => {
    await openAs(page, USERS.faisal, "/heat-board");
    await expect(page.getByTestId("nav-heat")).toBeVisible();
    const apr = page.locator('[data-testid="zone-card"][data-zone="Z-APR-21"]');
    await expect(apr).toHaveAttribute("data-regime", "R2");
    await expect(apr.getByTestId("zone-wbgt")).toContainText("27.8");
    await expect(apr.locator('[data-testid="cell"][data-basis="acclimatised"][data-workload="heavy"]')).toHaveAttribute("data-regime", "R2");
    await expect(page.getByTestId("board-record")).toBeVisible();

    await page.goto("/en/heat-duty-list");
    await expect(page.getByTestId("duty-not-for-heat")).toContainText("WKR-000033");
  });

  test("a client viewer sees the board without the record button or the log", async ({ page }) => {
    await openAs(page, USERS.sarah, "/heat-board");
    await expect(page.locator('[data-testid="zone-card"][data-zone="Z-APR-21"]')).toBeVisible();
    await expect(page.getByTestId("board-record")).toHaveCount(0);
    await expect(page.getByTestId("zone-record")).toHaveCount(0);
    await expect(page.getByTestId("nav-heat-log")).toHaveCount(0);
  });

  test("phone: Fahad records a manual reading from the Z-LAY1 card; Noura voids it with a reason", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS6.fahad, "/heat-board");
    await page.locator('[data-testid="zone-card"][data-zone="Z-LAY1"]').getByTestId("zone-record").click();
    await expect(page).toHaveURL(/\/wbgt-readings\/new\?zone=/);
    await expect(page.getByTestId("rd-point").locator("option:checked")).toContainText("P-SLAND-M1");
    await selectContaining(page.getByTestId("rd-instrument"), "HSM-ANIA-EXP-02");
    await page.getByTestId("rd-wbgt").fill("27.1");
    await page.getByTestId("rd-save").click();
    const saved = page.getByTestId("reading-saved");
    await expect(saved).toBeVisible();
    await expect(page.getByTestId("saved-wbgt")).toContainText("27.1");
    await expect(page.getByTestId("regime-cells")).toBeVisible();
    const no = await saved.getAttribute("data-no");
    expect(no).toMatch(/^WBG-ANIA-EXP-/);

    await page.context().clearCookies();
    await page.setViewportSize({ width: 1440, height: 900 });
    await openAs(page, USERS.noura, "/wbgt-readings");
    const row = page.locator(`[data-testid="reading-row"][data-no="${no}"]`);
    await row.getByTestId("reading-void").click();
    const dlg = page.getByRole("dialog");
    await dlg.getByTestId("heat-reason").fill("Entered on the wrong point by mistake.");
    await dlg.getByTestId("heat-reason-confirm").click();
    await expect(row).toHaveAttribute("data-status", "voided");
  });
});
