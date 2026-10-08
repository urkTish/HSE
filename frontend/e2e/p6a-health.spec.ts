import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { deploymentOf } from "./p5-helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Medical plan, fitness gaps and the worker health page with the three data tiers (6a §6.3, P6-1). */
test.describe("Medical plan, gaps and worker health", () => {
  test("AC23: WAH-FIT line at 2026-09-30 counts 519, met 504, gaps 15; Osman's WAH-FIT gap is a restriction", async ({ page }) => {
    await openAs(page, USERS.noura, "/medical-plan?as_of=2026-09-30");
    const line = page.locator('[data-testid="plan-line"][data-line="MRL-ANIA-EXP-002"]');
    await expect(line.getByTestId("line-counted")).toHaveText("519");
    await expect(line.getByTestId("line-met")).toHaveText("504");
    await expect(line.getByTestId("line-gaps")).toHaveText("15");

    await page.goto("/en/fitness-gaps?code=WAH-FIT");
    const gap = page.locator('[data-testid="gap-row"][data-worker="WKR-000009"][data-code="WAH-FIT"]');
    await expect(gap.getByTestId("gap-category")).toContainText("Restriction");
  });

  test("worker health shows what each tier may see (Sunil Gurung on hold)", async ({ page }) => {
    const dep = await deploymentOf("ANIA-EXP", "WKR-000034");
    // Tier 3: the hold reason code is shown.
    await openAs(page, USERS6.huda, `/worker-health/${dep.worker_id}?dep=${dep.id}`);
    await expect(page.getByTestId("fitness-tier")).toHaveAttribute("data-tier", "clinical_admin");
    await expect(page.getByTestId("on-hold")).toBeVisible();
    await expect(page.getByTestId("item-reason").first()).toBeVisible();
    await expect(page.getByTestId("wh-report")).toBeVisible();
    await expect(page.getByTestId("req-row").first()).toBeVisible();

    // Tier 2: outcomes but no reason codes, no data-subject report.
    await page.context().clearCookies();
    await openAs(page, USERS6.fahad, `/worker-health/${dep.worker_id}`);
    await expect(page.getByTestId("fitness-tier")).toHaveAttribute("data-tier", "functional");
    await expect(page.getByTestId("fitness-item").first()).toBeVisible();
    await expect(page.getByTestId("item-reason")).toHaveCount(0);
    await expect(page.getByTestId("wh-report")).toHaveCount(0);
    await expect(page.getByTestId("health-profile")).toBeVisible();

    // Tier 1 (permit issuer): status only, no profile edits, no hold actions.
    await page.context().clearCookies();
    await openAs(page, USERS.khalid, `/worker-health/${dep.worker_id}`);
    await expect(page.getByTestId("fitness-tier")).toHaveAttribute("data-tier", "status");
    await expect(page.getByTestId("fitness-item").first()).toBeVisible();
    await expect(page.getByTestId("edit-exposure")).toHaveCount(0);
    await expect(page.getByTestId("wh-hold")).toHaveCount(0);
    await expect(page.getByTestId("item-reason")).toHaveCount(0);
  });
});
