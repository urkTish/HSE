import { expect, test } from "../fixtures/test";
import { pickByText } from "./q2-helpers";
import { openQ, QU } from "./q0-helpers";

// Quality Q2 materials (spec 8-quality §C.3): MAR register and decision, MIR with the heat-number
// panel, quarantine red tag. Seed: Appendix A.4 (MAR-0021/0022/0027/0030, MIR-0112 → QTN-0009).

const ABDULLAH = "abdullah.dossary@example.com";

test.describe("Quality Q2 materials", () => {
  test("MAR register shows the seeded approval codes; Revise and Resubmit is flagged", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/materials");
    await expect(page.getByTestId("nav-q-materials")).toBeVisible();
    await expect(page.locator('[data-testid="q2-mar-row"][data-no="MAR-ANIA-EXP-2026-0027"]')).toHaveAttribute("data-status", "revise_resubmit");
    await page.locator('[data-testid="q2-mar-row"][data-no="MAR-ANIA-EXP-2026-0021"]').getByRole("link").click();
    await expect(page.getByTestId("q2-mar-detail")).toHaveAttribute("data-status", "approved");
    await expect(page.getByRole("heading", { name: "Compliance table" })).toBeVisible();
  });

  test("MAR drafted by the contractor and decided by the consultant (Q-MAT-01)", async ({ page }) => {
    await openQ(page, QU.bilal, "/quality/materials");
    await page.getByTestId("q2-mar-new").click();
    await pickByText(page, "mar-engagement", /RAWABI/);
    await page.getByTestId("mar-category").selectOption("waterproofing");
    await page.getByTestId("mar-title").fill("Podium waterproofing, second source");
    await page.getByTestId("mar-req").first().fill("Tensile strength ≥ 800 N/50 mm");
    await page.getByTestId("mar-save").click();
    const detail = page.getByTestId("q2-mar-detail");
    await expect(detail).toHaveAttribute("data-status", "draft");
    await page.getByTestId("q2-mar-submit").click();
    await expect(page.getByRole("alert").filter({ hasText: /technical data sheet/i })).toBeVisible();
    await page.locator('input[type="file"]').first().setInputFiles({ name: "tds.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%%EOF\n") });
    await expect(page.getByText("tds.pdf")).toBeVisible();
    await page.getByTestId("q2-mar-submit").click();
    await expect(detail).toHaveAttribute("data-status", "submitted");
    const url = page.url();

    await openQ(page, ABDULLAH, url.replace(/^https?:\/\/[^/]+\/en/, ""));
    await page.getByTestId("q2-mar-decide").click();
    await page.getByTestId("q2-decision").selectOption("A");
    await page.getByTestId("q2-decision-confirm").click();
    await expect(page.getByTestId("q2-mar-detail")).toHaveAttribute("data-status", "approved");
    await expect(page.getByTestId("q2-signoff").first()).toHaveAttribute("data-decision", "A");
  });

  test("MIR-0112 shows the rejected quantity and its red tag (Q-MAT-05)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/material-inspections");
    await page.locator('[data-testid="q2-mir-row"][data-no="MIR-ANIA-EXP-2026-0112"]').getByRole("link").click();
    await expect(page.getByTestId("q2-mir-detail")).toHaveAttribute("data-status", "decided");
    await page.getByTestId("q2-mir-quarantine-link").first().click();
    await expect(page.getByTestId("q2-red-tag")).toContainText("QTN-ANIA-EXP-2026-0009");
    await expect(page.getByTestId("q2-qtn-status")).toHaveAttribute("data-status", "quarantined");
  });

  test("Arabic: quarantine register is RTL with Arabic labels and LTR tag numbers", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/quarantine", { locale: "ar" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "المواد المحجوزة" })).toBeVisible();
    const row = page.locator('[data-testid="q2-qtn-row"][data-tag="QTN-ANIA-EXP-2026-0009"]');
    await expect(row).toContainText("محجوز");
  });
});
