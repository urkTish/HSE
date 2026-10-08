import { expect, test } from "./fixtures/test";
import { apiAs, login, USERS } from "./helpers";
import { recordOf, scan, sessionId, trQr } from "./p5-helpers";

/** Runs last among the Phase 5 specs: voiding a closed session revokes its records (5-training SS-9; AC54, AC122). */
test.describe("Session void", () => {
  test("AC54/AC122: Faisal voids TRS-ANIA-EXP-2026-00031; Imran Hussain's WAH record is revoked and its QR shows REVOKED", async ({ page }) => {
    test.setTimeout(150_000);
    const api = await apiAs(USERS.faisal);
    const id = await sessionId(api, "ANIA-EXP", "TRS-ANIA-EXP-2026-00031");
    const rec = await recordOf(api, "ANIA-EXP", "WKR-000001", "WAH");
    const qr = await trQr(rec.id);

    await login(page, USERS.faisal);
    await page.goto(`/en/training-sessions/${id}`);
    await page.getByTestId("session-void").click();
    await page.getByTestId("ss-void-code").selectOption("trainer_not_competent");
    await page.getByTestId("ss-void-text").fill("Trainer competence evidence found to be invalid after audit");
    await page.getByTestId("session-void-confirm").click();
    await expect(page.getByTestId("session-voided")).toBeVisible();

    await expect
      .poll(async () => (await recordOf(api, "ANIA-EXP", "WKR-000001", "WAH")).status, { timeout: 70_000, intervals: [2_000] })
      .toBe("revoked");

    await scan(page, qr);
    await expect(page.getByTestId("cc-result")).toHaveAttribute("data-result", "revoked_token");
    await expect(page.getByTestId("cc-verdict")).toContainText("Revoked");

    await login(page, USERS.ahmed);
    await page.goto(`/ar/training-records/${rec.id}`);
    await expect(page.getByTestId("not-accepted")).toContainText("السجل التدريبي غير مقبول");
  });
});
