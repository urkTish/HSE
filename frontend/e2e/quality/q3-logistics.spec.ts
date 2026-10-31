import { expect, test } from "../fixtures/test";
import { openQ, pickFirst, QU } from "./q0-helpers";

// Quality Q3 logistics (spec 8-quality Part D) on the RUH-CCH seed (Appendix A.5 / A.6, D-358).
// ANIA-EXP is Construction: the Q3 items are hidden and the pages show the other-profile notice (Q-NAV-01).

test.describe("Quality Q3 logistics", () => {
  test("construction project hides the logistics screens", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/storage");
    const nav = page.getByTestId("nav-quality");
    await expect(nav.getByTestId("nav-q-ncrs")).toBeVisible();
    await expect(nav.getByTestId("nav-q3-storage")).toHaveCount(0);
    await expect(nav.getByTestId("nav-q3-receiving")).toHaveCount(0);
    await expect(page.getByTestId("q3-other-profile")).toBeVisible();
  });

  test("storage: zones, live status and the zone profile chart (Q-STO-01, C48)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/storage", { project: "RUH-CCH" });
    const nav = page.getByTestId("nav-quality");
    for (const id of ["receiving", "storage", "excursions", "holds", "stock", "transport", "recalls"]) {
      await expect(nav.getByTestId(`nav-q3-${id}`)).toBeVisible();
    }
    const chl1 = page.locator('[data-testid="q3-zone-card"][data-code="Z-CHL1"]');
    await expect(chl1).toBeVisible();
    await expect(page.getByTestId("q3-zone-card")).toHaveCount(7);
    await chl1.click();
    await expect(page.getByTestId("q3-zone-detail")).toHaveAttribute("data-code", "Z-CHL1");
    await expect(page.getByTestId("q3-zone-chart")).toBeVisible();
    await expect(page.getByTestId("q3-point").first()).toBeVisible();
  });

  test("excursions: QX13 major excursion with impact assessment (Q-EXC)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/excursions", { project: "RUH-CCH" });
    const row = page.locator('[data-testid="q3-exc-row"][data-no="EXC-RUH-CCH-2026-0041"]');
    await expect(row).toBeVisible();
    await row.getByRole("link").click();
    const detail = page.getByTestId("q3-exc-detail");
    await expect(detail).toBeVisible();
    await expect(page.getByTestId("q3-exc-duration")).toBeVisible();
  });

  test("holds: HLD-0112 lines, blockers and the WMS export (Q-HLD)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/holds", { project: "RUH-CCH" });
    const row = page.locator('[data-testid="q3-hold-row"][data-no="HLD-RUH-CCH-2026-0112"]');
    await expect(row).toBeVisible();
    await expect(page.getByTestId("q3-hold-export")).toBeVisible();
    await row.getByRole("link").first().click();
    await expect(page.getByTestId("q3-hold-detail")).toBeVisible();
    await expect(page.getByTestId("q3-hold-line")).toHaveCount(14);
    // NCR-0034's disposition is not approved in the Q0 seed, so release is blocked (Q-HLD-04, D-358).
    await expect(page.getByTestId("q3-hold-blockers")).toContainText("NCR-RUH-CCH-2026-0034");
  });

  test("stock: September KPIs and the expired batch on the expiry tab (K-160…K-168, Q-STK-02)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/stock", { project: "RUH-CCH" });
    await page.getByTestId("q3-stock-tab-metrics").click();
    await expect(page.getByTestId("q3-metrics")).toBeVisible();
    // The month is computed from about 70,000 readings on the minute grid (D-351): allow for it.
    await expect(page.getByTestId("k161")).toContainText("0.71", { timeout: 30_000 });
    await expect(page.getByTestId("k163")).toContainText("93.2");
    await page.getByTestId("q3-stock-tab-expiry").click();
    const expired = page.locator('[data-testid="q3-expiry-row"][data-batch="NDC-L-2633"]');
    await expect(expired).toHaveAttribute("data-kind", "expired");
  });

  test("transport: TRP-00921 with its transit excursion (Q-TRP)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/transport", { project: "RUH-CCH" });
    await page.locator("#q3-trip-q").fill("00921");
    const row = page.locator('[data-testid="q3-trip-row"][data-no="TRP-RUH-CCH-2026-00921"]');
    await expect(row).toBeVisible();
    await row.getByRole("link").first().click();
    await expect(page.getByTestId("q3-trip-detail")).toBeVisible();
  });

  test("recalls: mock recall RCL-0002 at 100 % effectiveness (Q-RCL-05)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/recalls", { project: "RUH-CCH" });
    const row = page.locator('[data-testid="q3-recall-row"][data-no="RCL-RUH-CCH-2026-0002"]');
    await expect(row).toBeVisible();
    await row.getByRole("link").first().click();
    await expect(page.getByTestId("q3-recall-eff")).toContainText("100");
  });

  test("receiving on the dock: Warehouse QC starts a receipt and adds a line (Q-RCV-01)", async ({ page }) => {
    await openQ(page, QU.imran, "/quality/receiving/new", { project: "RUH-CCH" });
    await expect(page.getByTestId("q3-rcv-form")).toBeVisible();
    await pickFirst(page, "rcv-dock");
    await pickFirst(page, "rcv-owner");
    await page.getByTestId("rcv-asn").fill("ASN-E2E-0001");
    await page.getByTestId("rcv-save").click();
    const detail = page.getByTestId("q3-rcv-detail");
    await expect(detail).toHaveAttribute("data-status", "draft");
    await page.getByTestId("q3-rcv-add-line").click();
    await pickFirst(page, "ln-product");
    await page.getByTestId("ln-batch").fill("E2E-B1");
    await page.getByTestId("ln-expiry").fill("2027-12-31");
    await page.getByTestId("ln-qty").fill("10");
    // Frozen and chilled lines need the product temperature with a registered probe (Q-RCV-07).
    await page.getByTestId("ln-temp").fill("-19.5");
    await pickFirst(page, "ln-mte");
    await page.getByTestId("ln-save").click();
    await expect(page.getByTestId("q3-line")).toHaveCount(1);
  });

  test("Arabic: right-to-left with temperatures left-to-right", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/storage", { locale: "ar", project: "RUH-CCH" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const card = page.locator('[data-testid="q3-zone-card"][data-code="Z-CHL1"]');
    await expect(card).toBeVisible();
    await expect(card.locator("[data-temp]").first()).toHaveAttribute("dir", "ltr");
  });
});
