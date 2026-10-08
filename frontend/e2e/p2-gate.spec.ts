import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, login, uid, USERS } from "./helpers";
import {
  accessCard,
  createWorker,
  ensureGenCourse,
  projectIds,
  recordInduction,
  selectContaining,
} from "./p2-helpers";

// Committed demo screenshots are only rewritten on demand (SCREENSHOTS=1).
const SHOTS = process.env.SCREENSHOTS ? "../docs/screenshots/phase-2" : "test-results/shots";

test.describe
  .serial("Phase 2 — gates, devices and the gate check screen", () => {
  const gateCode = `GT${uid()}`;
  let token = "";
  let okRef = "";
  let okQr = "";
  let bannedRef = "";

  test.beforeAll(async () => {
    const api = await apiAs(USERS.faisal);
    const ids = await projectIds(api);
    const gen = await ensureGenCourse(api, ids.pid);
    const ok = await createWorker(api, ids, `Gate Ok ${uid()}`);
    await recordInduction(api, ids.pid, ok.id, gen);
    const okCard = await accessCard(api, ok.deploymentId);
    okRef = okCard.printed_ref;
    okQr = okCard.qr_payload;
    const bad = await createWorker(api, ids, `Gate Banned ${uid()}`);
    await recordInduction(api, ids.pid, bad.id, gen);
    bannedRef = (await accessCard(api, bad.deploymentId)).printed_ref;
    const ban = await api.post(`/api/v1/workers/${bad.id}/transitions`, {
      data: {
        to_status: "banned",
        reason: "Repeated unsafe acts on site (test)",
      },
    });
    expect(ban.ok(), await ban.text()).toBeTruthy();
  });

  test("GC-1: the HSE Manager creates a site gate and registers a device; the token is shown once", async ({
    page,
  }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/gates");
    await page.getByTestId("new-gate").click();
    await page.locator("#g-code").fill(gateCode);
    await page.locator("#g-type").selectOption("site_gate");
    await page.locator("#g-name-en").fill("E2E Main Gate");
    await page.locator("#g-name-ar").fill("البوابة الرئيسية للاختبار");
    await selectContaining(page.locator("#g-site"), "S-AIR");
    await page.getByTestId("save-gate").click();
    const row = page.locator(`[data-testid=gate-row][data-gate='${gateCode}']`);
    await expect(row).toBeVisible();
    await row.getByRole("link").click();

    await page.getByTestId("register-device").click();
    await page.locator("#dv-id").fill(`TAB-${uid()}`);
    await page.locator("#dv-label").fill("Guard tablet");
    await page.getByTestId("save-device").click();
    token = (await page.getByTestId("device-token").innerText()).trim();
    expect(token.length).toBeGreaterThanOrEqual(20);
    await page.getByTestId("token-done").click();
    await expect(page.getByTestId("device-row")).toHaveCount(1);
    await page.reload();
    await expect(page.locator("body")).not.toContainText(token);
  });

  async function deviceScreen(page: Page, locale: "en" | "ar") {
    await page.goto(`/${locale}/gate`);
    await page.getByTestId("device-token-input").fill(token);
    await page.getByTestId("device-login").click();
    await expect(page.getByTestId("gate-code")).toHaveText(gateCode);
    await expect(page.getByTestId("gate-ready")).toBeVisible();
  }

  for (const locale of ["ar", "en"] as const) {
    test(`GC-5/GC-7: device session on a phone (${locale}) — GRANTED and DENIED with reasons`, async ({
      browser,
    }) => {
      const ctx = await browser.newContext({
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
        locale: locale === "ar" ? "ar-SA" : "en-GB",
        timezoneId: "Asia/Riyadh",
      });
      const page = await ctx.newPage();
      await deviceScreen(page, locale);
      // Manual entry of the printed reference.
      await page.getByTestId("manual-ref").fill(okRef);
      await page.getByTestId("manual-check").click();
      const result = page.getByTestId("gate-result");
      await expect(result).toHaveAttribute("data-result", /^GRANTED/);
      await expect(page.getByTestId("person-card")).toBeVisible();
      await expect(page.getByTestId("next-scan")).toBeVisible();
      await page.screenshot({
        path: `${SHOTS}/gate-granted-mobile-${locale}.png`,
      });
      await page.getByTestId("next-scan").click();
      await expect(page.getByTestId("gate-ready")).toBeVisible();

      await page.getByTestId("manual-ref").fill(bannedRef);
      await page.getByTestId("manual-check").click();
      await expect(result).toHaveAttribute("data-result", "DENIED");
      // A banned worker is refused with WORKER_BANNED (v0.3.1).
      await expect(
        page.locator(
          "[data-testid=reasons] li[data-code=WORKER_BANNED][data-severity=deny]",
        ),
      ).toBeVisible();
      await expect(page.getByTestId("admitted-despite-denial")).toBeVisible();
      await page.screenshot({
        path: `${SHOTS}/gate-denied-mobile-${locale}.png`,
      });
      await ctx.close();
    });
  }

  test("GC-14: a guard records an admission despite denial; it shows in the gate log", async ({
    page,
    browser,
  }) => {
    await deviceScreen(page, "en");
    // Test hook stands in for the camera: feed the QR payload as if scanned.
    await page.evaluate(
      (p) =>
        (
          window as unknown as { __hseGateScan: (p: string) => Promise<void> }
        ).__hseGateScan(p),
      okQr,
    );
    await expect(page.getByTestId("gate-result")).toHaveAttribute(
      "data-result",
      /^GRANTED/,
    );
    await page.getByTestId("next-scan").click();

    await page.getByTestId("manual-ref").fill(bannedRef);
    await page.getByTestId("manual-check").click();
    await expect(page.getByTestId("gate-result")).toHaveAttribute(
      "data-result",
      "DENIED",
    );
    await page.getByTestId("admitted-despite-denial").click();
    await expect(page.getByTestId("admit-confirm")).toBeDisabled();
    await page
      .getByTestId("admit-reason")
      .fill("Escorted by site manager to collect tools");
    await page.getByTestId("admit-confirm").click();
    await expect(page.getByTestId("admitted-recorded")).toBeVisible();

    const ctx = await browser.newContext();
    const hse = await ctx.newPage();
    await login(hse, USERS.faisal);
    await hse.goto("/en/gate-log?admitted_despite_denial=true");
    const row = hse
      .locator("[data-testid=gate-log-row][data-admitted=true]")
      .first();
    await expect(row).toBeVisible();
    await expect(row).toContainText(gateCode);
    await expect(row.getByTestId("admitted-flag")).toContainText(
      "Escorted by site manager",
    );
    await hse.goto("/en/gate-log?result=GRANTED&result=GRANTED_WITH_WARNING");
    await expect(
      hse.locator("[data-testid=gate-log-row]").first(),
    ).toBeVisible();
    await ctx.close();
  });

  test("GC-1: revoking the device ends its session on the gate screen", async ({
    page,
    browser,
  }) => {
    await deviceScreen(page, "en");
    const ctx = await browser.newContext();
    const hse = await ctx.newPage();
    await login(hse, USERS.faisal);
    await hse.goto("/en/gates");
    await hse
      .locator(`[data-testid=gate-row][data-gate='${gateCode}'] a`)
      .click();
    await hse.getByTestId("revoke-device").click();
    await hse.getByTestId("revoke-confirm").click();
    await expect(hse.getByTestId("revoke-device")).toHaveCount(0);
    await ctx.close();

    await page.getByTestId("manual-ref").fill(okRef);
    await page.getByTestId("manual-check").click();
    await expect(page.getByTestId("device-token-input")).toBeVisible();
  });

  test("GC-15: with no connection the gate screen says so", async ({
    page,
    context,
  }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/gate");
    await expect(page.getByTestId("gate-screen")).toBeVisible();
    await context.setOffline(true);
    await expect(page.getByTestId("gate-offline").first()).toContainText(
      "No connection",
    );
    await context.setOffline(false);
  });

  test("GC: a user with gate.check can pick the gate on the gate screen", async ({
    page,
  }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/gate");
    await expect(page.getByTestId("gate-ready")).toBeVisible();
    const sel = page.getByTestId("gate-select");
    if (await sel.count()) await selectContaining(sel, gateCode);
    await expect(page.getByTestId("gate-code")).toHaveText(gateCode);
    await page.getByTestId("direction-out").click();
    await page.getByTestId("manual-ref").fill(okRef);
    await page.getByTestId("manual-check").click();
    await expect(page.getByTestId("gate-result")).toHaveAttribute(
      "data-result",
      "EXIT_RECORDED",
    );
  });
});
