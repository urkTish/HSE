import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

const REVIEW = ["HC1", "HC2", "HC3", "HC4", "HC5", "HC6"] as const;

/** Heat-illness log and the controls review (6b §8, AC48, AC53, P6b-2). */
test.describe("Heat-illness log", () => {
  test("Noura opens Ganesh's entry with its exposure context, reopens and re-reviews it with a control gap", async ({ page }) => {
    await openAs(page, USERS.noura, "/heat-illness-log");
    await expect(page.getByTestId("heat-sensitive-note")).toBeVisible();
    const row = page.locator('[data-testid="log-row"][data-no="HIL-ANIA-EXP-2026-014"]');
    await expect(row).toHaveAttribute("data-status", "reviewed");
    await expect(row.getByTestId("control-gap")).toHaveAttribute("data-gap", "yes");
    await row.getByTestId("log-link").click();
    await expect(page).toHaveURL(/\/heat-illness-log\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("log-context")).toBeVisible();
    await expect(page.getByTestId("ctx-wbgt")).toContainText("°C");
    await expect(page.getByTestId("review-answer").first()).toBeVisible();

    await page.getByTestId("log-reopen").click();
    const dlg = page.getByRole("dialog");
    await dlg.getByTestId("heat-reason").fill("Re-check the welfare answer with the site team.");
    await dlg.getByTestId("heat-reason-confirm").click();
    await expect(page.getByTestId("review-form")).toBeVisible();
    for (const q of REVIEW) await page.getByTestId(`rv-${q}-${q === "HC2" ? "no" : "yes"}`).click();
    await page.getByTestId("rv-factors").fill("Water at the rest station was warm during the afternoon.");
    await page.getByTestId("rv-save").click();
    await expect(page.getByTestId("log-review")).toBeVisible();
    await expect(page.getByTestId("log-reopen")).toBeVisible();
  });

  test("a client viewer and a permit receiver have no heat-illness log", async ({ page }) => {
    await openAs(page, USERS.ramesh, "/heat-illness-log");
    await expect(page.getByTestId("log-table")).toHaveCount(0);
    await expect(page.getByTestId("nav-heat-log")).toHaveCount(0);
  });
});
