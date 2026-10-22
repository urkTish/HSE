import { expect, test } from "./fixtures/test";
import en from "../messages/en.json" with { type: "json" };
import ar from "../messages/ar.json" with { type: "json" };

/**
 * First-time setup (D-306). The e2e database is seeded, so the real API keeps the setup locked; the "open"
 * state is simulated by answering GET /setup in the browser, and the real POST then proves the lock (409).
 * The successful setup on an empty install is covered by the backend tests (test_first_setup.py).
 */
test.describe("First-time setup (D-306)", () => {
  test("a seeded install shows the setup as locked and the login page stays", async ({ page }) => {
    await page.goto("/en/setup");
    await expect(page.getByTestId("setup-locked")).toContainText(en.firstSetup.locked);
    await page.getByRole("link", { name: en.firstSetup.toLogin }).click();
    await expect(page).toHaveURL(/\/en\/login/);
    await expect(page.locator("#email")).toBeVisible();
  });

  test("an empty install sends the login page to the setup form (AR, RTL); the server refuses a second setup", async ({ page }) => {
    await page.route("**/api/v1/setup", (route) =>
      route.request().method() === "GET"
        ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ needed: true, token_required: false }) })
        : route.continue(),
    );
    await page.goto("/ar/login");
    await expect(page).toHaveURL(/\/ar\/setup$/);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const form = page.getByTestId("first-setup");
    await expect(form).toContainText(ar.firstSetup.title);
    await page.getByTestId("setup-submit").click();
    await expect(page.locator("#setup-organisation_name_en-error")).toHaveText(ar.validation.required);
    await page.locator("#setup-organisation_name_en").fill("Gulf Airports Construction Co.");
    await page.locator("#setup-organisation_name_ar").fill("Gulf");
    await page.locator("#setup-code").fill("T3-EXP");
    await page.locator("#setup-name_en").fill("Terminal 3 expansion");
    await page.locator("#setup-name_ar").fill("توسعة المبنى 3");
    await page.locator("#setup-client_name_en").fill("Airport Authority");
    await page.locator("#setup-client_name_ar").fill("هيئة المطار");
    await page.locator("#setup-city").fill("Riyadh");
    await page.locator("#setup-start_date").fill("2026-10-01");
    await page.locator("#setup-full_name_en").fill("First Admin");
    await page.locator("#setup-email").fill("first.admin@example.com");
    await page.locator("#setup-password").fill("Trial-Setup#2026x");
    await page.locator("#setup-confirm").fill("Trial-Setup#2026x");
    await page.locator("#setup-ack").check();
    await page.getByTestId("setup-submit").click();
    await expect(page.locator("#setup-organisation_name_ar-error")).toHaveText(ar.validation.arabicRequired);
    await page.locator("#setup-organisation_name_ar").fill("شركة إنشاءات مطارات الخليج");
    await page.getByTestId("setup-submit").click();
    await expect(page.getByTestId("form-error")).toContainText(ar.errors.code.SETUP_ALREADY_DONE);
  });
});
