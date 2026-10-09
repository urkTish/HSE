import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

/** ERP revisions, assembly points, contacts, zone requirements, muster readers and settings (6c §3.1–§3.3, §3.15, ER-3…ER-8). */
test.describe("Emergency plan and setup", () => {
  test("Noura drafts r4 from the plan in force and submits it; Faisal returns it with a reason", async ({ page }) => {
    await openAs(page, USERS.noura, "/emergency-plans");
    await expect(page.locator('[data-testid="erp-row"][data-no="ERP-ANIA-EXP-r3"]')).toHaveAttribute("data-status", "approved");
    await page.getByTestId("erp-new").click();
    await page.getByTestId("erp-create-confirm").click();
    await expect(page).toHaveURL(/\/emergency-plans\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("erp-status")).toHaveAttribute("data-status", "draft");
    await expect(page.locator('[data-testid="scenario-row"][data-code="SC-FIRE"]')).toBeVisible();
    await page.getByTestId("erp-submit").click();
    await page.getByTestId("erp-transition-confirm").click();
    await expect(page.getByTestId("erp-status")).toHaveAttribute("data-status", "submitted");
    await expect(page.getByTestId("erp-approve")).toHaveCount(0);
    const url = page.url().replace(/^.*\/en/, "");

    await page.context().clearCookies();
    await openAs(page, USERS.faisal, url);
    await page.getByTestId("erp-return").click();
    await page.getByTestId("em-reason").fill("Please update the airport interface reference before approval.");
    await page.getByTestId("em-reason-confirm").click();
    await expect(page.getByTestId("erp-status")).toHaveAttribute("data-status", "draft");
  });

  test("assembly points with the MP sticker, emergency numbers and zone requirements", async ({ page }) => {
    await openAs(page, USERS.noura, "/assembly-points");
    const ap = page.locator('[data-testid="ap-row"][data-code="AP-SLAND-01"]');
    await expect(ap).toBeVisible();
    await ap.getByTestId("ap-qr").click();
    await expect(page.getByTestId("ap-sticker")).toContainText("AP-SLAND-01");
    await page.keyboard.press("Escape");

    await page.goto("/en/emergency-contacts");
    await expect(page.locator('[data-testid="contact-row"][data-agency="civil_defense"]')).toContainText("998");
    await expect(page.locator('[data-testid="contact-row"][data-agency="airport_arff"]')).toBeVisible();

    await page.goto("/en/emergency-zone-profiles");
    await expect(page.locator('[data-testid="profile-row"][data-zone="Z-MSCP"]').getByTestId("profile-ext")).toContainText("4");
  });

  test("settings are read-only for Noura; Faisal registers and revokes a muster reader", async ({ page }) => {
    await openAs(page, USERS.noura, "/emergency-settings");
    await expect(page.getByTestId("settings-readonly")).toBeVisible();
    await expect(page.getByTestId("es-save")).toHaveCount(0);

    await page.context().clearCookies();
    await openAs(page, USERS.faisal, "/emergency-settings");
    await expect(page.getByTestId("settings-readonly")).toHaveCount(0);
    await expect(page.getByTestId("es-save")).toBeVisible();

    await page.goto("/en/muster-devices");
    await selectContaining(page.getByTestId("md-ap"), "AP-SAIR-01");
    await page.getByTestId("md-device").fill("MR-TEST-001");
    await page.getByTestId("md-label").fill("Reader at the contractor compound");
    await page.getByTestId("md-register").click();
    const row = page.getByTestId("md-row").first();
    await expect(row.getByTestId("md-token")).not.toBeEmpty();
    await row.getByTestId("md-revoke").click();
    await page.getByTestId("md-revoke-confirm").click();
    await expect(row).toHaveAttribute("data-revoked", "yes");
  });
});
