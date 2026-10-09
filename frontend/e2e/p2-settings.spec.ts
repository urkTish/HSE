import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";

// Committed demo screenshots are only rewritten on demand (SCREENSHOTS=1).
const SHOTS = process.env.SCREENSHOTS ? "../docs/screenshots/phase-2" : "test-results/shots";

test.describe.serial("Phase 2 — access settings and dashboard", () => {
  test("§3.22: the HSE Manager changes an access setting; out-of-range values are refused in the form", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/access-settings");
    const field = page.locator("#as-escort_pairing_seconds");
    await field.fill("5");
    await page.getByTestId("save-access-settings").click();
    await expect(page.locator("[role=alert]", { hasText: /30.*600/ }).first()).toBeVisible();
    await field.fill("90");
    await page.getByTestId("save-access-settings").click();
    await expect(page.getByTestId("save-access-settings")).toBeDisabled();
    await page.reload();
    await expect(page.locator("#as-escort_pairing_seconds")).toHaveValue("90");
    await field.fill("120");
    await page.getByTestId("save-access-settings").click();
    await expect(page.getByTestId("save-access-settings")).toBeDisabled();
  });

  test("HK-4: switching a hook to block without a registered provider is refused with a clear message", async ({ page }) => {
    // On the full seed every hook kind has a live provider (Phase 4 per project, Phase 5 training,
    // Phase 6a medical_fitness, spec 6a §6a.7), so the backend refusal cannot be
    // reached from the seed; it is covered by backend test_P2AC22 (HOOK_PROVIDER_MISSING). Here the
    // PATCH answers as the backend does without a provider, and the screen must surface it unsaved.
    await page.route("**/access-settings", async (route) => {
      if (route.request().method() !== "PATCH") return route.fallback();
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            code: "HOOK_PROVIDER_MISSING",
            message: "No provider is registered for medical_fitness; it can only warn until its module is live (HK-4).",
            message_ar: "لا يوجد مزوّد مسجل لهذا المتطلب؛ يبقى تنبيهًا حتى تشغيل الوحدة.",
            errors: [{ loc: ["body", "hook_policy.medical_fitness"], msg: "Provider missing.", msg_ar: null, type: "HOOK_PROVIDER_MISSING" }],
          },
        }),
      });
    });
    await login(page, USERS.faisal);
    await page.goto("/en/access-settings");
    await page.getByTestId("hook-policy-medical_fitness").selectOption("block");
    await page.getByTestId("save-access-settings").click();
    await expect(page.getByTestId("form-error")).toBeVisible();
    await page.reload();
    await expect(page.getByTestId("hook-policy-medical_fitness")).toHaveValue("warn");
  });

  test("§3.22: a contractor rep cannot open access settings", async ({ page }) => {
    await login(page, USERS.ahmed);
    await expect(page.getByTestId("nav-access-settings")).toHaveCount(0);
  });

  test("§8.1: the dashboard shows the access band and charts C10–C12 for an airport project", async ({ page }) => {
    await login(page, USERS.faisal);
    // A URL with filters wins over saved preferences (an earlier test may have saved "all projects").
    await page.goto("/en?period=month");
    const band = page.getByTestId("access-band");
    await expect(band).toBeVisible();
    await expect(band.locator("[data-metric='K-48']")).toBeVisible();
    await expect(page.getByTestId("band-ops")).toBeVisible();
    await page.getByTestId("access-charts").scrollIntoViewIfNeeded();
    for (const id of ["C10", "C11", "C12"]) await expect(page.getByTestId(`chart-card-${id}`)).toBeVisible();
    await band.scrollIntoViewIfNeeded();
    await band.screenshot({ path: `${SHOTS}/dashboard-access-band-en.png` });
  });

  test("§8.1: Phase 2 action-panel items open the register with the same filter", async ({ page }) => {
    test.slow(); // every KPI request is slow on the full Phase 2 seed (reported to the backend)
    await login(page, USERS.faisal);
    await page.goto("/en?period=month");
    const item = page.locator("[data-testid=action-item][data-key=admitted_despite_denial]");
    await expect(item).toBeVisible({ timeout: 60_000 });
    await item.getByRole("link").click();
    await expect(page).toHaveURL(/\/gate-log\?.*admitted_despite_denial=true/, { timeout: 45_000 });
    await expect(page.locator("[data-testid=gate-log-row][data-admitted=true]").first()).toBeVisible();
    await expect(page.locator("[data-testid=gate-log-row][data-admitted=false]")).toHaveCount(0);
  });
});
