import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Midday-ban patrols and HSE Manager exemptions for non-permit work (6b §7, AC43–AC44). */
test.describe("Midday ban", () => {
  test("patrol list shows the September violations; a violation needs its details and a time inside the ban", async ({ page }) => {
    await openAs(page, USERS6.fahad, "/ban-patrols?outcome=violation");
    await expect(page.getByTestId("ban-window")).toBeVisible();
    await expect(page.locator('[data-testid="patrol-row"][data-no="MBP-ANIA-EXP-2026-00188"]')).toHaveAttribute("data-outcome", "violation");
    await page.getByTestId("new-patrol").click();
    const dlg = page.getByRole("dialog");
    await selectContaining(dlg.getByTestId("bp-zone"), "Z-LAY1");
    await dlg.getByTestId("bp-violation").click();
    await selectContaining(dlg.getByTestId("bp-eng"), "SAHARA");
    // A violation needs the contractor, headcount and activity (MB-3).
    await expect(dlg.getByTestId("patrol-confirm")).toBeDisabled();
    await dlg.getByTestId("bp-head").fill("4");
    await dlg.getByTestId("bp-activity").fill("loading scaffold tubes");
    // 2026-10-06 10:00 is outside the ban period: the server refuses the patrol (HS9b).
    await dlg.getByTestId("patrol-confirm").click();
    await expect(dlg.getByTestId("form-error")).toBeVisible();
  });

  test("Ahmed cannot patrol; Noura cannot grant; Faisal grants a two-day exemption for RAWABI", async ({ page }) => {
    await openAs(page, USERS.ahmed, "/ban-patrols");
    await expect(page.getByTestId("patrols-table")).toBeVisible();
    await expect(page.getByTestId("new-patrol")).toHaveCount(0);
    await page.context().clearCookies();
    await openAs(page, USERS.noura, "/ban-exemptions");
    await expect(page.locator('[data-testid="exemption-row"][data-no="MBX-ANIA-EXP-2026-004"]')).toHaveAttribute("data-status", "expired");
    await expect(page.getByTestId("grant-exemption")).toHaveCount(0);

    await page.context().clearCookies();
    await openAs(page, USERS.faisal, "/ban-exemptions");
    await page.getByTestId("grant-exemption").click();
    const dlg = page.getByRole("dialog");
    await selectContaining(dlg.getByTestId("bx-eng"), "RAWABI");
    await pickMulti(page, "bx-zones", [/Z-LAY1/]);
    await dlg.getByTestId("bx-from").fill("2027-07-20");
    await dlg.getByTestId("bx-to").fill("2027-07-21");
    await dlg.getByTestId("bx-reason").selectOption("emergency_repair");
    await dlg.getByTestId("bx-en").fill("Water main repair; shade canopy; 15/45 regime; paramedic on standby.");
    await dlg.getByTestId("exemption-confirm").click();
    await expect(page.locator('[data-testid="exemption-row"][data-status="active"]').first()).toBeVisible();
  });
});
