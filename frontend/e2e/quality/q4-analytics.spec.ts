import { expect, test } from "../fixtures/test";
import { openQ, QU } from "./q0-helpers";

// Quality Q4 (spec 8-quality Part E) on the Appendix A seed: KPIs for both profiles (A.8), documents
// with read-and-acknowledge (A.7), quality audits and programme, management review, supplier scores
// (QX19), SPC (QX22) and the Quality report packs. Arabic pages are right-to-left with numbers LTR.

const NAVEEN = "naveen.kumar@example.com";

test.describe("Quality Q4 analytics", () => {
  test("construction KPIs: tiles, targets and the E27 warning (AC-Q4-17, -28, -33)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/kpis");
    const nav = page.getByTestId("nav-quality");
    await expect(nav.getByTestId("nav-q4-kpis")).toBeVisible();
    const k141 = page.locator('[data-testid="q4-tile"][data-kpi="K-141"]');
    await expect(k141).toContainText("80.0 %");
    await expect(k141).toHaveAttribute("data-rag", "red");
    await expect(page.locator('[data-testid="q4-tile"][data-kpi="K-160"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="q4-warning"][data-code="E27"]')).toBeVisible();
    await expect(page.getByTestId("q4-pareto")).toBeVisible();
  });

  test("logistics KPIs in Arabic: RTL page, numbers left-to-right (AC-Q4-26, -34)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/kpis", { project: "RUH-CCH", locale: "ar" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const k161 = page.locator('[data-testid="q4-tile"][data-kpi="K-161"]');
    await expect(k161).toContainText("0.71");
    await expect(k161.locator('[dir="ltr"]').first()).toBeVisible();
    await expect(page.locator('[data-testid="q4-tile"][data-kpi="K-141"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="q4-warning"]')).toHaveCount(0);
  });

  test("documents: register and read-and-acknowledge on the phone (Q-DOC-05)", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openQ(page, NAVEEN, "/quality/documents", { project: "RUH-CCH" });
    const acks = page.getByTestId("q4-my-acks");
    await expect(acks).toContainText("RUH-CCH-QA-SOP-007");
    await acks.getByTestId("q4-ack").first().click();
    await expect(page.getByTestId("q4-my-acks")).toHaveCount(0);
    await expect(page.getByTestId("q4-doc-row").first()).toBeVisible();
  });

  test("documents: PQP Rev.B for review and the superseded Rev.0 (Q-DOC-01…03)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/documents");
    const row = page.getByTestId("q4-doc-row").filter({ hasText: "ANIA-EXP-QA-PQP-001" });
    await expect(row).toContainText("1 → B");
    await row.getByRole("link").click();
    await expect(page.locator('[data-testid="q4-rev-row"][data-rev="0"]')).toContainText(/Superseded/);
    await expect(page.locator('[data-testid="q4-rev-row"][data-rev="B"]')).toBeVisible();
  });

  test("audits, programme and management review (Q-AUD, Q-MRV)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/audits", { project: "RUH-CCH" });
    const a = page.getByTestId("q4-audit-row").filter({ hasText: "QAU-RUH-CCH-2026-0006" });
    await expect(a).toBeVisible();
    await expect(a.locator('[data-status="issued"]')).toBeVisible();
    await a.getByRole("link").click();
    await expect(page.getByText("ISO 9001")).toBeVisible();
    await page.goto("/en/quality/audit-programme");
    await page.getByTestId("q4-prog-year").fill("2026");
    await expect(page.getByTestId("q4-prog-cell").first()).toBeVisible();
    await page.goto("/en/quality/management-reviews");
    const m = page.getByTestId("q4-mrv-row").filter({ hasText: "MRV-RUH-CCH-2026-0001" });
    await expect(m.locator('[data-status="minutes_issued"]')).toBeVisible();
    await m.getByRole("link").click();
    await expect(page.getByTestId("q4-mrv-snapshot")).toBeVisible();
  });

  test("supplier scores and SPC (QX19, QX22)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/supplier-scores");
    const rmx = page.getByTestId("q4-score-row").filter({ hasText: "Riyadh Readymix" });
    await expect(rmx).toContainText("72.2");
    await expect(rmx.locator('[data-band="B"]')).toBeVisible();
    await page.goto("/en/quality/spc");
    const c = page.locator('[data-testid="q4-spc-chart"][data-code="C40-STRENGTH"]');
    await expect(c.getByTestId("q4-spc-cpk")).toContainText("Cpk 1.24");
  });

  test("quality report pack: QMR prepared for September (Q-RPT-01)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/reports");
    await page.getByTestId("q4-pack-month").fill("2026-09");
    await page.getByTestId("q4-pack-create").click();
    const row = page.getByTestId("q4-pack-row").filter({ hasText: "QMR-ANIA-EXP-2026-09" });
    await expect(row).toBeVisible();
    await row.getByTestId("q4-pack-submit").click();
    await expect(row.locator('[data-status="in_review"]')).toBeVisible();
  });
});
