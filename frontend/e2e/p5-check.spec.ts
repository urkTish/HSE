import { expect, test } from "./fixtures/test";
import { apiAs, login, USERS } from "./helpers";
import { accessCard } from "./p2-helpers";
import { deploymentOf, recordOf, scan, trQr, USERS5 } from "./p5-helpers";

/** Competence check with TR QR codes and the AC card (5-training §5.16; AC121, AC124). */
test.describe("Training competence check", () => {
  test("AC121: a site engineer scans a TR QR and sees course, worker, dates, status and provider — no ID or score", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const rec = await recordOf(api, "ANIA-EXP", "WKR-000001", "WAH");
    const qr = await trQr(rec.id);
    expect(qr).toMatch(/^HSE2:TR:/);
    // Omar's site scope does not cover Imran Hussain's deployment; Fahad's does.
    await login(page, USERS5.fahad);
    await scan(page, qr);
    const card = page.getByTestId("training-card");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-colour", "green");
    await expect(card).toContainText("WAH");
    await expect(card).toContainText("WKR-000001");
    await expect(card).toContainText("INT-HSE");
    await expect(card).not.toContainText(/%|\d{10}|\d\*{4,}\d/);
  });

  // Since the 6c seed (6c-emergency-drills §11.6 item 3, A.4 RT-ANIA-CSE-01) Biju holds CSE-RESCUE, which
  // satisfies CSE-ATTENDANT, so the line is now in force (5-training TR5(a) predates 6c).
  test("AC124: Fahad opens Biju Thomas's access card and sees the Training section with CSE-ATTENDANT in force", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const biju = await deploymentOf("ANIA-EXP", "WKR-000017");
    const card = await accessCard(api, biju.id);
    await login(page, USERS5.fahad);
    await scan(page, card.qr_payload);
    const section = page.getByTestId("person-training");
    await expect(section).toBeVisible();
    await expect(section.locator('[data-testid="person-training-item"][data-code="CSE-ATTENDANT"]')).toHaveAttribute("data-in-force", "1");
    await expect(section.getByTestId("person-training-item").first()).toBeVisible();
  });
});
