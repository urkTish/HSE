import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

const TARIQ = "tariq.mutairi@example.com";

/** Contractor watch list: seeded SAHARA entry, one open entry per engagement, manual open and close (6g §3.6 WL-1, WL-2, WL-6; AC 27–29, 33). */
test.describe("Contractor watch list", () => {
  test("Faisal sees the SAHARA entry with its trigger and review CA; a second entry is refused (WL-1, WL-2)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/watch-list");
    const sahara = page.locator('[data-testid="wl-row"][data-engagement="SAHARA"]');
    await expect(sahara).toHaveAttribute("data-status", "open");
    await expect(sahara.getByTestId("sc-watch-level")).toHaveAttribute("data-level", "watch");
    await expect(page.locator('[data-testid="wl-row"][data-engagement="GULFPAVE"][data-status="closed"]').first()).toBeVisible();

    await page.getByTestId("wl-open").click();
    await page.getByTestId("wl-engagement").selectOption({ label: "SAHARA" });
    await page.getByTestId("wl-reason").fill("Second entry attempt for the same engagement (TEST).");
    await page.getByTestId("wl-open-confirm").click();
    await expect(page.getByText("This contractor already has an open watch-list entry.")).toBeVisible();
    await page.keyboard.press("Escape");

    await sahara.getByRole("link").click();
    await expect(page.getByTestId("wl-no")).toHaveText("WL-ANIA-EXP-2026-002");
    await expect(page.getByTestId("wl-triggers")).toContainText("SCR-ANIA-EXP-SAHARA-2026-08");
    await expect(page.getByText(/^CA-ANIA-EXP-2026-\d{5}$/).first()).toBeVisible();
  });

  test("Faisal opens GULFPAVE manually and closes it with a reason (WL-1d, WL-6)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/watch-list");
    await page.getByTestId("wl-open").click();
    await page.getByTestId("wl-engagement").selectOption({ label: "GULFPAVE" });
    await page.getByTestId("wl-reason").fill("Repeated permit lapses observed on site this month (TEST e2e).");
    await page.getByTestId("wl-open-confirm").click();
    const row = page.locator('[data-testid="wl-row"][data-engagement="GULFPAVE"][data-status="open"]');
    await expect(row).toHaveCount(1);
    await row.getByRole("link").click();
    await expect(page.getByTestId("wl-status")).toHaveAttribute("data-status", "open");
    await page.getByTestId("wl-close").click();
    await page.getByTestId("wl-act-reason").fill("Permit performance recovered after the toolbox campaign (TEST).");
    await page.getByTestId("wl-transition-confirm").click();
    await expect(page.getByTestId("wl-status")).toHaveAttribute("data-status", "closed");
    await expect(page.getByTestId("wl-actions")).toHaveCount(0);
  });

  test("Tariq sees his own SAHARA entry read-only (role scope)", async ({ page }) => {
    await openAs(page, TARIQ, "/watch-list");
    await expect(page.locator('[data-testid="wl-row"][data-engagement="SAHARA"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="wl-row"][data-engagement="GULFPAVE"]')).toHaveCount(0);
    await expect(page.getByTestId("wl-open")).toHaveCount(0);
    await page.locator('[data-testid="wl-row"][data-engagement="SAHARA"]').getByRole("link").click();
    await expect(page.getByTestId("wl-no")).toHaveText("WL-ANIA-EXP-2026-002");
    await expect(page.getByTestId("wl-close")).toHaveCount(0);
  });
});
