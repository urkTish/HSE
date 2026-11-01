import { expect, test } from "../fixtures/test";
import { pickByText } from "./q2-helpers";
import { openQ, pickFirst, QU } from "./q0-helpers";

// Quality Q2 testing and pours (spec 8-quality §C.2): failed set 3 of POUR-0077 with its NCR, the
// pour's sets and mix status, a new test request walked to the lab, test types.

test.describe("Quality Q2 tests and pours", () => {
  test("TST-00388 failed (b) and links its NCR; the pour shows 4 of 4 sets", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/tests?verdict=fail");
    await page.locator('[data-testid="q2-test-row"][data-no="TST-ANIA-EXP-2026-00388"]').getByRole("link").click();
    const d = page.getByTestId("q2-test-detail");
    await expect(d).toHaveAttribute("data-verdict", "fail");
    await expect(page.getByTestId("q2-test-fail")).toContainText("36.00");
    await expect(page.getByTestId("q2-test-ncr-link")).toContainText("NCR-ANIA-EXP-2026-0044");
    await page.getByRole("link", { name: "POUR-ANIA-EXP-2026-0077" }).click();
    await expect(page.getByTestId("q2-pour-detail")).toHaveAttribute("data-status", "closed");
    await expect(page.getByTestId("q2-mix-status")).toBeVisible();
  });

  test("a test request is created, sampled and sent to the lab (Q-TST-03)", async ({ page }) => {
    await openQ(page, QU.joseph, "/quality/tests");
    await page.getByTestId("q2-test-new").click();
    await pickByText(page, "tst-type", /^SLUMP/);
    await page.getByTestId("tst-lab").selectOption({ label: "LAB-RGM" });
    await pickFirst(page, "tst-site");
    await pickByText(page, "tst-engagement", /RAWABI/);
    await page.getByTestId("tst-location").fill("Level 4 slab, bay D2");
    await page.getByTestId("tst-save").click();
    const d = page.getByTestId("q2-test-detail");
    await expect(d).toHaveAttribute("data-status", "requested");
    await page.getByTestId("q2-sample-ref").fill(`S-E2E-${Date.now() % 100000}`);
    await page.getByTestId("q2-sample-save").click();
    await expect(d).toHaveAttribute("data-status", "sampled");
    await page.getByTestId("q2-test-deliver").click();
    await expect(d).toHaveAttribute("data-status", "at_lab");
    await expect(page.getByTestId("q2-results-form")).toBeVisible();
  });

  test("test types are versioned data with profiles", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/test-types");
    await expect(page.locator('[data-testid="q2-test-type-row"][data-code="CONC-CYL"]')).toContainText("CONC-ACI-40");
    await expect(page.locator('[data-testid="q2-test-type-row"][data-code="ATP-SWAB"]')).toBeVisible();
  });
});
