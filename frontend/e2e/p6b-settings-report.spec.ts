import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Heat settings and regime table, action panel, KPIs K-97…K-103 and the season report (6b §3.14, §8.4, AC1–2, AC54, AC57–58). */
test.describe("Heat settings and reporting", () => {
  test("Noura sees settings read-only; Faisal's +0.5 offset and a loosened limit are refused, a tightened one saved", async ({ page }) => {
    await openAs(page, USERS.noura, "/heat-settings");
    await expect(page.getByTestId("heat-settings-form")).toBeVisible();
    await expect(page.getByTestId("hs-save")).toHaveCount(0);
    await expect(page.getByTestId("regime-save")).toHaveCount(0);

    await page.context().clearCookies();
    await openAs(page, USERS.faisal, "/heat-settings");
    await page.getByTestId("hs-wbgt_limit_offset_c").fill("0.5");
    await page.getByTestId("hs-save").click();
    await expect(page.getByTestId("heat-settings-form").getByTestId("form-error")).toBeVisible();

    const table = page.getByTestId("regime-table");
    const loose = table.getByTestId("limit-acclimatised-R2-heavy");
    const v = Number(await loose.inputValue());
    await loose.fill((v + 0.5).toFixed(1));
    await page.getByTestId("regime-save").click();
    await expect(table.getByTestId("form-error")).toHaveAttribute("data-code", "REGIME_LOOSENING");
    await loose.fill(v.toFixed(1));
    const tight = table.getByTestId("limit-unacclimatised-R3-very_heavy");
    const w = Number(await tight.inputValue());
    await tight.fill((w - 0.1).toFixed(1));
    await page.getByTestId("regime-save").click();
    await expect(table.getByTestId("form-error")).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("limit-unacclimatised-R3-very_heavy")).toHaveValue((w - 0.1).toFixed(1));
  });

  test("September KPIs match HS7; the action panel lists heat items", async ({ page }) => {
    await openAs(page, USERS.faisal, "/heat-stress?period=month&anchor=2026-09-15");
    const tile = (k: string) => page.locator(`[data-testid="heat-tile"][data-metric="${k}"]`).getByTestId("heat-value");
    await expect(tile("K-97")).toContainText("97.0");
    await expect(tile("K-98")).toContainText("141.0");
    await expect(tile("K-101")).toContainText("97.1");
    await expect(tile("K-102")).toContainText("91.7");
    await page.goto("/en/heat-actions");
    await expect(page.getByTestId("heat-actions")).toBeVisible();
  });

  test("season 2026 draft (HS8); Faisal issues r1; Noura cannot issue", async ({ page }) => {
    await openAs(page, USERS.noura, "/heat-season-report?year=2026");
    await expect(page.getByTestId("season-report")).toHaveAttribute("data-status", "draft");
    await expect(page.getByTestId("season-k01")).toContainText("4,210,000");
    await expect(page.getByTestId("report-issue")).toHaveCount(0);

    await page.context().clearCookies();
    await openAs(page, USERS.faisal, "/heat-season-report?year=2026");
    await page.getByTestId("report-issue").click();
    const dlg = page.getByRole("dialog");
    await dlg.getByTestId("sr-en").fill("Season closed with one control gap at the S-AIR rest station.");
    await dlg.getByTestId("report-issue-confirm").click();
    await expect(dlg).toBeHidden();
    const rev = page.locator("#sr-rev");
    await expect(rev.locator("option", { hasText: /r1|R1|-01/ }).first()).toBeAttached();
    const value = await rev.evaluate((el) => Array.from((el as HTMLSelectElement).options).find((o) => o.value && o.value !== "draft")?.value ?? "");
    await rev.selectOption(value);
    await expect(page.getByTestId("season-report")).toHaveAttribute("data-status", "issued");
  });
});
