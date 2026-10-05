import { expect, test } from "@playwright/test";
import { login, USERS } from "./helpers";

test.describe("Design system (Phase 0 design pass)", () => {
  test("Theme toggle switches to dark, survives a reload, and returns to the device setting", async ({ page }) => {
    await page.goto("/en/login");
    await page.getByTestId("theme-toggle").click();
    await page.getByTestId("theme-dark").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByTestId("theme-toggle").click();
    await page.getByTestId("theme-system").click();
    await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
  });

  test("Phone layout: drawer navigation, 44px controls and stacked table rows with labels (AR)", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, USERS.faisal, "ar");
    await page.goto("/ar/projects");
    await expect(page.getByTestId("sidebar")).toBeHidden();
    const menu = page.getByTestId("open-menu");
    expect((await menu.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    // Stacked rows: each cell carries its column name.
    const firstCell = page.getByTestId("project-row").first().locator("td").first();
    await expect(firstCell).toHaveAttribute("data-label", "رمز المشروع");
    await menu.click();
    await expect(page.getByTestId("mobile-nav")).toBeVisible();
    await page.getByTestId("mobile-nav").getByTestId("nav-contractors").click();
    await expect(page).toHaveURL(/\/ar\/contractors$/);
    await expect(page.getByTestId("mobile-nav")).toBeHidden();
  });
});
