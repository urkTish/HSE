import { expect, test } from "./fixtures/test";
import { selectByPrefix, USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Phone reading entry, exceedances with the airside alert, review and limits (6e §3.8–§3.12, MON-1…MON-6, EXD-1…EXD-6, AIR-1, LIM-1…LIM-3). */
test.describe("Environmental monitoring", () => {
  test("Omar records visual dust 3 at V-SAIR on his phone; Noura reviews the exceedance as project activity and a CA is raised", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS.omar, "/env-readings/new");
    await page.getByTestId("rd-point-V-SAIR").click();
    // V-SAIR has one requirement (visual dust, spot), so it is picked for him.
    await expect(page.getByTestId("rd-limit")).toBeVisible();
    await page.getByTestId("rd-visual-3").click();
    await page.getByTestId("rd-save").click();
    const saved = page.getByTestId("reading-saved");
    await expect(saved).toHaveAttribute("data-result", "exceedance");
    await page.getByTestId("saved-exceedance").click();
    await expect(page.getByTestId("airside-alert")).toBeVisible();
    // A site engineer records readings but does not review exceedances (210).
    await expect(page.getByTestId("exceedance-review")).toHaveCount(0);
    const path = new URL(page.url()).pathname.replace(/^\/en/, "");

    await page.setViewportSize({ width: 1280, height: 900 });
    await openAs(page, USERS.noura, path);
    await page.getByTestId("exceedance-review").click();
    await page.getByTestId("rv-cause").selectOption("project_activity");
    await selectByPrefix(page.getByTestId("rv-engagement"), "GULFPAVE");
    await page.getByTestId("rv-activity").fill("Paving on the taxiway link road");
    await page.getByTestId("rv-action").fill("Water bowser sent to the haul road and paving paused for 30 minutes.");
    await page.getByTestId("review-confirm").click();
    await expect(page.getByTestId("env-status").first()).toHaveAttribute("data-status", "reviewed");
    await expect(page.getByTestId("exceedance-ca")).toBeVisible();
  });

  test("a project limit can only be tightened (LIM-2); the viewer sees the register without write buttons", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-points");
    await page.getByTestId("point-row").filter({ hasText: "D-SAIR-01" }).getByRole("link").first().click();
    await expect(page.getByTestId("requirement-row").first()).toBeVisible();
    await page.getByTestId("limits-edit").click();
    await page.getByTestId("lm-limit-0").fill("99999");
    await page.getByTestId("limits-save").click();
    await expect(page.getByRole("dialog").getByText("A project limit can only be stricter than the limit in force.")).toBeVisible();
    await page.keyboard.press("Escape");

    await openAs(page, USERS.sarah, "/env-readings");
    await expect(page.getByTestId("reading-row").first()).toBeVisible();
    await expect(page.getByTestId("reading-new")).toHaveCount(0);
    await expect(page.getByTestId("reading-void")).toHaveCount(0);
    await page.goto("/en/env-points");
    await expect(page.getByTestId("point-row").first()).toBeVisible();
    await expect(page.getByTestId("point-new")).toHaveCount(0);
  });

  test("Arabic: the exceedance register labels background dust", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-exceedances", "ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("التجاوزات");
    await expect(page.getByTestId("exceedance-row").filter({ hasText: "ENX-ANIA-EXP-2026-0018" })).toContainText("غبار");
  });
});
