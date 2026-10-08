import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";
import { PDF } from "./p4-helpers";
import { deploymentOf } from "./p5-helpers";
import { openAs, pinProject, USERS6 } from "./p6a-helpers";

/** Pick the first option whose text contains `text` (selects whose values are ids). */
async function pick(page: Page, testId: string, text: string | RegExp): Promise<void> {
  const sel = page.getByTestId(testId);
  await expect(sel.locator("option", { hasText: text }).first()).toBeAttached();
  const value = await sel.locator("option", { hasText: text }).first().getAttribute("value");
  await sel.selectOption(value ?? "");
}

/** Sign again when the API asks for a fresh password (signing a site clinic record). */
async function maybeReauth(page: Page): Promise<void> {
  const dlg = page.getByTestId("reauth-dialog");
  if (await dlg.isVisible().catch(() => false)) {
    await dlg.getByTestId("reauth-password").fill("Demo-Passw0rd!2026");
    await dlg.getByTestId("reauth-confirm").click();
  }
}

/** Fitness assessments (6a §4.3, FA/FH/FV; AC-level flows, one per screen group). */
test.describe("Fitness assessments", () => {
  test("referral → hold; nurse records, physician signs; the hold is released", async ({ page }) => {
    const worker = "WKR-000015";
    const dep = await deploymentOf("ANIA-EXP", worker);

    // The HSE Officer refers the worker and removes them from work: a hold is placed.
    await openAs(page, USERS.noura, `/worker-health/${dep.worker_id}`);
    await expect(page.getByTestId("worker-fitness")).toBeVisible();
    await page.getByTestId("wh-refer").click();
    await page.getByTestId("ref-reason").selectOption("observed_unwell");
    await page.getByTestId("ref-note").fill("Looked pale at the morning briefing.");
    await page.getByTestId("ref-remove").check();
    await page.getByTestId("raise-referral-confirm").click();
    await expect(page.getByTestId("referral-raised")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.reload();
    await expect(page.getByTestId("on-hold")).toBeVisible();

    // The site clinic nurse records the referral assessment; it waits for the physician.
    await page.context().clearCookies();
    await openAs(page, USERS6.grace, `/fitness-assessments/new?worker_no=${worker}&type=referral`);
    await expect(page.getByTestId("fa-worker-found")).toContainText(worker);
    await expect(page.getByTestId("fa-referral")).not.toHaveValue("");
    await pick(page, "fa-provider", "SHIFA-ANIA");
    await pick(page, "fa-examiner", "EXR-0001");
    await page.getByTestId("fa-line-0-outcome").selectOption("fit");
    await page.getByTestId("fa-notice").check();
    await page.getByTestId("fa-save").click();
    await expect(page).toHaveURL(/\/fitness-assessments\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("assessment-status")).toHaveAttribute("data-status", "awaiting_signoff");
    const url = page.url();

    // Dr. Huda signs (re-auth if asked); the record is accepted and the hold released.
    await page.context().clearCookies();
    await login(page, USERS6.huda);
    await pinProject(page, "ANIA-EXP");
    await page.goto(url);
    await page.getByTestId("fa-sign").click();
    await page.getByTestId("fa-confirm").click();
    await maybeReauth(page);
    await expect(page.getByTestId("assessment-status")).toHaveAttribute("data-status", "accepted");
    await page.goto(`/en/worker-health/${dep.worker_id}`);
    await expect(page.getByTestId("worker-fitness")).toBeVisible();
    await expect(page.getByTestId("on-hold")).toHaveCount(0);
  });

  test("external certificate: draft with scan, submitted, accepted, scan viewed with a reason, verified", async ({ page }) => {
    const worker = "WKR-000018";
    const cert = `SAL-TEST-26-E2E-${uid()}`;
    await openAs(page, USERS.noura, `/fitness-assessments/new?worker_no=${worker}&type=periodic`);
    await page.getByTestId("fa-src").selectOption("external_certificate");
    await expect(page.getByTestId("fa-worker-found")).toContainText(worker);
    await pick(page, "fa-provider", "SALAMA");
    await pick(page, "fa-examiner", "EXR-0003");
    await page.getByTestId("fa-examined").fill("2026-10-04");
    await page.getByTestId("fa-cert").fill(cert);
    await page.getByTestId("fa-line-0-outcome").selectOption("fit");
    await page.getByTestId("fa-notice").check();
    await page.getByTestId("fa-save").click();
    await expect(page).toHaveURL(/\/fitness-assessments\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("assessment-status")).toHaveAttribute("data-status", "draft");
    await page.getByTestId("fa-scan").setInputFiles(PDF("salama.pdf"));
    await expect(page.getByTestId("fa-scan-done")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("fa-submit").click();
    await page.getByTestId("fa-confirm").click();
    await expect(page.getByTestId("assessment-status")).toHaveAttribute("data-status", "submitted");
    // Tier 2: no scan link for the officer.
    await expect(page.getByTestId("fa-open-scan")).toHaveCount(0);
    const url = page.url();

    await page.context().clearCookies();
    await login(page, USERS6.huda);
    await pinProject(page, "ANIA-EXP");
    await page.goto(url);
    await page.getByTestId("fa-open-scan").click();
    await page.getByTestId("scan-reason").selectOption("verification");
    await page.getByTestId("scan-confirm").click();
    await expect(page.getByTestId("scan-link")).toBeVisible();
    await page.getByTestId("scan-confirm").click();
    await page.getByTestId("fa-accept").click();
    await page.getByTestId("fa-clinical").selectOption("no");
    await page.getByTestId("fa-confirm").click();
    await expect(page.getByTestId("assessment-status")).toHaveAttribute("data-status", "accepted");
    await page.getByTestId("fa-verify").click();
    await page.getByTestId("fv-method").selectOption("clinic_email");
    await page.getByTestId("fv-channel").fill("fitness@salama-test.example");
    await page.getByTestId("fv-outcome").selectOption("confirmed");
    await page.getByTestId("fv-ref").fill("Email reply 2026-10-06");
    await page.getByTestId("verify-confirm").click();
    await expect(page.getByTestId("med-verification")).toHaveAttribute("data-status", "verified");
    await expect(page.getByTestId("fa-verification")).toHaveCount(1);
  });
});
