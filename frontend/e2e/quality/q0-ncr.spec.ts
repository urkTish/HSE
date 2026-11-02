import { expect, test } from "../fixtures/test";
import { selectByPrefix, uid } from "../helpers";
import { openQ, pickFirst, QU } from "./q0-helpers";

// Quality Q0 NCR core (spec 8-quality Part A §A.4): raise on the phone form, open, detail tabs.

test.describe("Quality Q0 NCRs", () => {
  test("QC inspector raises and opens an NCR from the one-screen form (Q-NCR-01)", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openQ(page, QU.joseph, "/quality/ncrs/new");
    const title = `Honeycombing at column C-12 ${uid().slice(0, 6)}`;
    await page.getByTestId("ncr-title").fill(title);
    await page.getByTestId("ncr-finding").fill("Honeycombing over 300 mm at the column base after stripping.");
    await page.getByTestId("ncr-requirement").fill("Spec 03 30 00 §3.10: no honeycombing on exposed faces.");
    await page.getByTestId("ncr-category").selectOption("workmanship");
    await pickFirst(page, "ncr-site");
    // Joseph works for RAWABI: his NCRs name his own contractor tree (scope C).
    await selectByPrefix(page.getByTestId("ncr-engagement"), "RAWABI");
    await page.getByTestId("ncr-open").click();
    const detail = page.getByTestId("q-ncr-detail");
    await expect(detail).toHaveAttribute("data-status", "open");
    await expect(page.getByRole("heading", { name: /NCR-ANIA-EXP-2026-/ })).toBeVisible();
    await page.getByTestId("q-ncr-tab-containment").click();
    await expect(page.getByTestId("q-containment-text")).toBeVisible();
    await page.getByTestId("q-ncr-tab-history").click();
  });

  test("register filters by class and opens a seeded NCR", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/ncrs?classification=major");
    const rows = page.getByTestId("q-ncr-row");
    await expect(rows.first()).toBeVisible();
    await rows.first().getByRole("link").first().click();
    await expect(page.getByTestId("q-ncr-detail")).toBeVisible();
    for (const tab of ["rca", "disposition", "actions", "costs", "signoffs", "links"]) {
      await page.getByTestId(`q-ncr-tab-${tab}`).click();
    }
  });
});
