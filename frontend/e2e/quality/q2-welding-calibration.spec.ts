import { expect, test } from "../fixtures/test";
import { openQ, QU } from "./q0-helpers";

// Quality Q2 welding, calibration and competence (spec 8-quality §C.4–§C.6). Seed: the QX8 lot
// PB-ROOF-RT10, W-021 lapsed (QX9), MTE-0012 calibrated, the QX11 review OOT-RUH-CCH-2026-0003.

test.describe("Quality Q2 welding, calibration, competence", () => {
  test("welding: QX8 lot at 15.0 % and W-021 lapsed on the continuity board", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/welding");
    await page.locator("#q2-weld-q").fill("J07");
    await expect(page.locator('[data-testid="q2-weld-row"][data-joint="PB-RT-T12-J07"]')).toBeVisible();
    await page.getByTestId("q2-wld-tab-lots").click();
    await page.getByTestId("q2-lot-pick").selectOption("PB-ROOF-RT10");
    await expect(page.getByTestId("q2-lot-achieved")).toHaveText("15.0 %");
    await expect(page.getByTestId("q2-lot-examined")).toHaveText("6");
    await page.getByTestId("q2-wld-tab-continuity").click();
    await expect(page.locator('[data-testid="q2-continuity"] [data-stamp="W-021"]')).toHaveAttribute("data-status", "lapsed");
  });

  test("M&TE page gains the calibration, OOT and label tabs (tabs-q2)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/mte?q=MTE-0012");
    await page.locator('[data-testid="q-mte-row"][data-no="MTE-0012"]').getByRole("link").click();
    await page.getByTestId("q-mte-tab-calibrations").click();
    await expect(page.getByTestId("q2-cal-row").first()).toHaveAttribute("data-status", "accepted");
    await page.getByTestId("q-mte-tab-label").click();
    await expect(page.getByTestId("q2-label")).toHaveAttribute("data-colour", "green");
    await expect(page.getByTestId("q2-label")).toContainText("MTE-0012");
    await page.getByTestId("q2-label-open").click();
    await expect(page.getByTestId("q2-label-page")).toBeVisible();
  });

  test("calibration board lists overdue items; the QX11 review is open with 36 of 37 decided", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/calibration", { project: "RUH-CCH" });
    await expect(page.getByTestId("q2-cal-chips")).toBeVisible();
    await page.locator('[data-testid="q2-oot-list"] [data-no="OOT-RUH-CCH-2026-0003"]').getByRole("link").click();
    await expect(page.getByTestId("q2-oot-detail")).toHaveAttribute("data-status", "open");
    await expect(page.getByTestId("q2-oot-progress")).toHaveText("36 / 37");
    await expect(page.locator('[data-testid="q2-oot-item"][data-proposed="recheck"]')).toHaveCount(2);
  });

  test("Arabic competence matrix: Joseph's concrete field course is expiring", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/competence", { locale: "ar" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "الكفاءة" })).toBeVisible();
    await expect(page.locator('[data-testid="q2-cpt-matrix"] td[data-code="CONC-FIELD-TECH"][data-state="expiring"]').first()).toBeVisible();
  });
});
