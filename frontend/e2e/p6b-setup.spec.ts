import { expect, test } from "./fixtures/test";
import { uid, USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

/** Instruments, monitoring points and rest stations (6b §3.2–3.4, AC4–AC5). */
test.describe("Heat setup", () => {
  test("Noura adds a handheld meter and quarantines it; a second point on Z-LAY1 is refused", async ({ page }) => {
    await openAs(page, USERS.noura, "/heat-instruments");
    await expect(page.locator('[data-testid="instrument-row"][data-no="HSM-ANIA-EXP-01"]')).toBeVisible();
    await page.getByTestId("new-instrument").click();
    const dlg = page.getByRole("dialog");
    await dlg.getByTestId("in-kind").selectOption("handheld_meter");
    await dlg.getByTestId("in-model").fill("QuestTemp 46");
    const serial = `QT-TEST-${uid()}`;
    await dlg.getByTestId("in-serial").fill(serial);
    await dlg.getByTestId("in-until").fill("2027-06-30");
    await dlg.getByTestId("in-cert").fill(`CAL-TEST-${uid()}`);
    await dlg.getByTestId("instrument-confirm").click();
    const row = page.getByTestId("instrument-row").filter({ hasText: serial });
    await expect(row).toBeVisible();
    // A compliant meter with a valid calibration starts Active; quarantine needs a reason.
    await expect(row).toHaveAttribute("data-status", "active");
    await row.getByTestId("instrument-quarantine").click();
    await page.getByRole("dialog").getByTestId("it-reason").fill("Dropped on site; send for a calibration check.");
    await page.getByRole("dialog").getByTestId("instrument-transition-confirm").click();
    await expect(row).toHaveAttribute("data-status", "quarantined");

    await page.goto("/en/monitoring-points");
    await expect(page.locator('[data-testid="point-row"][data-code="P-SLAND-M1"]')).toBeVisible();
    await page.getByTestId("new-point").click();
    const pd = page.getByRole("dialog");
    await pd.getByTestId("pt-code").fill(`P-E2E-${uid()}`);
    await selectContaining(pd.getByTestId("pt-site"), "S-LAND");
    await pd.getByTestId("pt-source").selectOption("manual");
    await pickMulti(page, "pt-zones", [/Z-LAY1/]);
    await selectContaining(pd.getByTestId("pt-inst"), "HSM-ANIA-EXP-02");
    await pd.getByTestId("point-confirm").click();
    await expect(pd.getByTestId("form-error")).toHaveAttribute("data-code", "ZONE_ALREADY_COVERED");
  });

  test("rest stations list; a site engineer sees setup read-only", async ({ page }) => {
    await openAs(page, USERS.omar, "/rest-stations");
    await expect(page.locator('[data-testid="station-row"][data-code="RS-SAIR-01"]')).toBeVisible();
    await expect(page.getByTestId("new-station")).toHaveCount(0);
    await page.goto("/en/heat-instruments");
    await expect(page.getByTestId("new-instrument")).toHaveCount(0);
  });
});
