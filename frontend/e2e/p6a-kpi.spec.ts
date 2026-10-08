import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Occupational health KPIs K-89…K-96 (6a §8, MK-3 small-cell suppression). */
test.describe("Occupational health KPIs", () => {
  test("the client viewer sees eight tiles; active holds at 2026-09-30 are suppressed as <5", async ({ page }) => {
    await openAs(page, USERS.sarah, "/occupational-health?as_of=2026-09-30");
    await expect(page.getByTestId("oh-tile")).toHaveCount(8, { timeout: 30_000 });
    await expect(page.locator('[data-testid="oh-tile"][data-metric="K-93"]').getByTestId("oh-value")).toHaveText("<5");
    await expect(page.locator('[data-testid="oh-cell"][data-suppressed="1"]').first()).toHaveText("<5");
  });
});
