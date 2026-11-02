import { expect, test } from "../fixtures/test";
import { openQ, QU } from "./q0-helpers";

// Quality Q0 foundation (spec 8-quality Part A): sidebar group per profile, home, settings, RTL.
// Seed: ANIA-EXP is Construction, RUH-CCH is Logistics (Appendix A.2).

test.describe("Quality Q0 foundation", () => {
  test("construction home: Quality group, profile badge, stop-use banner and tiles (Q-NAV-01/02)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality");
    const nav = page.getByTestId("nav-quality");
    await expect(nav).toBeVisible();
    await expect(nav.getByTestId("nav-q-ncrs")).toBeVisible();
    await expect(nav.getByTestId("nav-q-systems")).toBeVisible();
    await expect(nav.getByTestId("nav-q-settings")).toBeVisible();
    await expect(page.getByTestId("q-profile-badge")).toHaveAttribute("data-profile", "construction");
    await expect(page.getByTestId("q-stop-use").first()).toBeVisible();
    await expect(page.getByTestId("q-tile-open")).toBeVisible();
    await expect(page.getByTestId("q-raise-ncr")).toBeVisible();
  });

  test("logistics profile hides construction-only items (Q-PRF-03)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality", { project: "RUH-CCH" });
    await expect(page.getByTestId("q-profile-badge")).toHaveAttribute("data-profile", "logistics");
    const nav = page.getByTestId("nav-quality");
    await expect(nav.getByTestId("nav-q-ncrs")).toBeVisible();
    await expect(nav.getByTestId("nav-q-complaints")).toBeVisible();
    await expect(nav.getByTestId("nav-q-systems")).toHaveCount(0);
  });

  test("settings: matrix, positions and numbering preview (Q-RPM, Q-NUM)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/settings");
    await expect(page.getByTestId("q-profile-construction")).toBeChecked();
    await page.getByTestId("q-settings-tab-matrix").click();
    await expect(page.getByTestId("q-rp-row").first()).toBeVisible();
    const ir = page.locator('[data-testid="q-rp-row"][data-record-type="ncr"][data-step="disposition"]');
    await expect(ir.first()).toBeVisible();
    await page.getByTestId("q-settings-tab-positions").click();
    await expect(page.getByTestId("q-position").first()).toBeVisible();
    await page.getByTestId("q-settings-tab-numbering").click();
    const ncr = page.locator('[data-testid="q-numbering-row"][data-record-type="ncr"]');
    await expect(ncr.getByTestId("q-numbering-preview")).toContainText("NCR-ANIA-EXP-");
    await page.getByTestId("q-settings-tab-parts").click();
    await expect(page.getByTestId("q-part-settings")).toBeVisible();
  });

  test("Arabic: register heading and right-to-left layout", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/ncrs", { locale: "ar" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "تقارير عدم المطابقة" })).toBeVisible();
    await expect(page.getByTestId("q-ncr-row").first()).toBeVisible();
  });

  test("awaiting my sign-off lists pending steps", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/awaiting");
    await expect(page.getByTestId("q-awaiting-count")).toBeVisible();
  });
});
