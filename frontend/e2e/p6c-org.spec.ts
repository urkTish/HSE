import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Emergency roster, coverage and rescue teams (6c §3.4, §3.5, EO-1…EO-7, RT-1…RT-3). */
test.describe("Emergency organisation", () => {
  test("roster shows the privacy note and training state; Fahad can assign, Sarah cannot", async ({ page }) => {
    await openAs(page, USERS6.fahad, "/emergency-roster?role=first_aider");
    await expect(page.getByTestId("em-privacy-note")).toBeVisible();
    await expect(page.getByTestId("roster-row").first()).toBeVisible();
    await expect(page.locator('[data-testid="roster-row"][data-qualified="yes"]').first()).toBeVisible();
    await expect(page.getByTestId("roster-new")).toBeVisible();

    await page.context().clearCookies();
    await openAs(page, USERS.sarah, "/emergency-roster");
    await expect(page.getByTestId("roster-new")).toHaveCount(0);
  });

  test("coverage: S-AIR night on 2026-09-14 is short of first aiders", async ({ page }) => {
    await openAs(page, USERS.noura, "/emergency-coverage?from=2026-09-14&to=2026-09-14");
    await expect(page.locator('[data-testid="coverage-row"][data-site="S-AIR"][data-day="2026-09-14"][data-shift="night"]')).toHaveAttribute("data-state", "short");
  });

  test("rescue teams: the confined-space and height teams are current with their members", async ({ page }) => {
    await openAs(page, USERS.noura, "/rescue-teams");
    const cse = page.locator('[data-testid="team-card"][data-code="RT-ANIA-CSE-01"]');
    await expect(cse).toHaveAttribute("data-current", "yes");
    await expect(cse.getByTestId("team-members").locator("li")).toHaveCount(3);
    await expect(page.locator('[data-testid="team-card"][data-code="RT-ANIA-WAH-01"]')).toHaveAttribute("data-current", "yes");
  });
});
