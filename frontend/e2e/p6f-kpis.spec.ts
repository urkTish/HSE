import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Follow-up overview (band, action panel) and K-127…K-131 (6f §6.2, §8.1, §8.2; AC 18, 31). */
test.describe("Follow-up overview and KPIs", () => {
  test("Noura sees the follow-up nav, the band and the overdue SAHARA acknowledgement", async ({ page }) => {
    await openAs(page, USERS.noura, "/followup-overview");
    await expect(page.getByTestId("nav-followup")).toBeVisible();
    await expect(page.getByTestId("fu-band").getByTestId("band-tile")).toHaveCount(4);
    const ack = page.locator('[data-testid="fu-action"][data-kind="acknowledgements_overdue"]');
    await expect(ack).toContainText("LL-2026-007 SAHARA");
  });

  test("October KPIs for ANIA-EXP match FU2 and FU5 at the clock", async ({ page }) => {
    await openAs(page, USERS.noura, "/followup-kpis?period=month");
    const tile = (k: string) => page.locator(`[data-testid="fk-tile"][data-metric="${k}"]`).getByTestId("fk-value");
    await expect(tile("K-127")).toHaveText("100.0 %");
    await expect(tile("K-128")).toHaveText("0");
    await expect(tile("K-130")).toHaveText("75.0 %");
    await expect(page.getByTestId("fk-breakdown")).toBeVisible();

    await page.goto("/ar/followup-kpis?period=month");
    await expect(page.getByTestId("fk-note").first()).toContainText("يستبعد K-127");
  });
});
