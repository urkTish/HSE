import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Scorecard KPIs K-132…K-135, exactly as the server returns them (6g §5; AC 54–56). */
test.describe("Scorecard KPIs", () => {
  test("September: mean score, watch list, disputes and on-time packs", async ({ page }) => {
    await openAs(page, USERS.faisal, "/scorecard-kpis?period=month&anchor=2026-09-15");
    const tile = (m: string) => page.locator(`[data-testid="sk-tile"][data-metric="${m}"]`).getByTestId("sk-value");
    await expect(tile("K-132")).toHaveText("84.2");
    await expect(tile("K-133")).toHaveText("1");
    await expect(tile("K-135")).toHaveText("100.0 %");
    await expect(page.getByTestId("sk-breakdown")).toBeVisible();
  });

  test("Arabic: the KPI page renders right-to-left with the four tiles", async ({ page }) => {
    await openAs(page, USERS.faisal, "/scorecard-kpis?period=month&anchor=2026-09-15", "ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("sk-tile")).toHaveCount(4);
  });
});
