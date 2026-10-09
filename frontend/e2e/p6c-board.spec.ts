import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { pickMulti } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

/** Emergency board, action panel, emergency info and KPIs (6c §4.1, §6.8, §8.2, PE-6). */
test.describe("Emergency board and reports", () => {
  test("Faisal sees both sites, the plan in force and the declare / check buttons; Arabic is right-to-left", async ({ page }) => {
    await openAs(page, USERS.faisal, "/emergency-board");
    await expect(page.getByTestId("nav-emergency")).toBeVisible();
    await expect(page.locator('[data-testid="board-site"][data-site="S-AIR"]')).toBeVisible();
    await expect(page.locator('[data-testid="board-site"][data-site="S-LAND"]')).toBeVisible();
    await expect(page.getByTestId("board-erp")).toHaveAttribute("data-in-force", "yes");
    await expect(page.getByTestId("board-erp")).toContainText("ERP-ANIA-EXP");
    await expect(page.getByTestId("board-declare")).toBeVisible();
    await expect(page.getByTestId("board-check")).toBeVisible();

    await page.goto("/ar/emergency-board");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("board-erp")).toContainText("ERP-ANIA-EXP");
  });

  test("the client viewer sees the board but no declare, check or KPI action buttons", async ({ page }) => {
    await openAs(page, USERS.sarah, "/emergency-board");
    await expect(page.locator('[data-testid="board-site"][data-site="S-AIR"]')).toBeVisible();
    await expect(page.getByTestId("board-declare")).toHaveCount(0);
    await expect(page.getByTestId("board-check")).toHaveCount(0);
  });

  test("action panel lists overdue checks and out-of-service equipment; emergency info for Z-PIERB", async ({ page }) => {
    await openAs(page, USERS.noura, "/emergency-actions");
    await expect(page.locator('[data-testid="em-action"][data-kind="asset_checks_overdue"]')).toBeVisible();
    await expect(page.locator('[data-testid="em-action"][data-kind="assets_out_of_service"]')).toBeVisible();

    await page.goto("/en/emergency-info");
    await pickMulti(page, "ei-zones", [/Z-PIERB/]);
    await expect(page.getByTestId("ei-ap")).toHaveText("AP-SLAND-01");
    await expect(page.getByTestId("ei-numbers")).toContainText("998");
    await expect(page.getByTestId("ei-numbers")).toContainText("997");
  });

  test("KPI page shows K-104…K-109 from the server", async ({ page }) => {
    await openAs(page, USERS.faisal, "/emergency-kpis?anchor=2026-09-15&period=month");
    // The six KPIs are computed on request (a few seconds on the full seed).
    await expect(page.getByTestId("em-tiles")).toBeVisible({ timeout: 45_000 });
    for (const k of ["K-104", "K-105", "K-106", "K-107", "K-108", "K-109"]) await expect(page.locator(`[data-testid="em-tile"][data-metric="${k}"]`)).toBeVisible();
    await expect(page.locator('[data-testid="em-tile"][data-metric="K-107"]').getByTestId("em-value")).not.toHaveText("");
  });
});
