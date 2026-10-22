import { createPrivateKey, sign } from "node:crypto";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { login, sql, USERS } from "./helpers";

/**
 * Trial readiness, package B (D-289…D-298): the HSE Manager pastes a licence key on the Licence page and the
 * trial banner appears at once; an expired licence shows the read-only banner (EN / AR, RTL). Read-only and caps
 * on the API are covered by backend/tests/test_licence.py. The spec removes its key afterwards, so the specs that
 * follow run with no key (unlimited).
 */

function riyadhToday(offsetDays = 0): string {
  return new Date(Date.now() + 3 * 3600_000 + offsetDays * 86_400_000).toISOString().slice(0, 10);
}

function issue(over: Record<string, unknown> = {}): string {
  const payload = Buffer.from(
    JSON.stringify({
      v: 1,
      id: "LIC-E2E-1",
      customer: "E2E Airports",
      bundle: "trial",
      issued_on: riyadhToday(),
      valid_until: riyadhToday(9),
      max_projects: null,
      max_users: null,
      max_storage_gb: null,
      ai_questions_per_month: null,
      ...over,
    }),
  );
  const key = createPrivateKey(process.env.E2E_LICENCE_PRIVATE_KEY ?? "");
  return `HSE1.${payload.toString("base64url")}.${sign(null, payload, key).toString("base64url")}`;
}

/** Serve GET /licence as an expired trial (the API's real answer with the state changed). */
async function mockExpired(page: Page): Promise<void> {
  await page.route("**/api/v1/licence", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const res = await route.fetch();
    const real = (await res.json()) as Record<string, unknown>;
    await route.fulfill({
      response: res,
      json: {
        ...real,
        state: "expired",
        read_only: true,
        bundle: "trial",
        is_trial: true,
        customer: "E2E Airports",
        valid_until: riyadhToday(-3),
        days_left: -3,
        data_deletion_after: riyadhToday(27),
      },
    });
  });
}

test.describe.serial("licence", () => {
  test.afterAll(() => {
    sql("DELETE FROM licence_keys");
  });

  test("HSE Manager pastes a trial key; the banner counts the days (EN / AR)", async ({ page }) => {
    sql("DELETE FROM licence_keys");
    await login(page, USERS.faisal);
    await expect(page.getByTestId("licence-banner")).toHaveCount(0); // no key = unlimited, no banner
    await page.getByTestId("nav-licence").click();
    // the first API calls queue behind the dashboard's cold KPI burst (D-264)
    await expect(page.getByTestId("licence-page")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("licence-no-key")).toBeVisible();

    // a key that is not ours is refused with a clear message
    await page.getByTestId("licence-key-input").fill(issue().replace(/.{6}$/, "AAAAAA"));
    await page.getByTestId("licence-key-save").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "LICENCE_KEY_INVALID");

    // pasted with line breaks, as from an e-mail
    const key = issue();
    await page.getByTestId("licence-key-input").fill(`${key.slice(0, 40)}\n${key.slice(40)}`);
    await page.getByTestId("licence-key-save").click();
    await expect(page.getByTestId("licence-state")).toHaveText("Active");
    await expect(page.getByTestId("licence-customer")).toHaveText("E2E Airports");
    await expect(page.getByTestId("licence-bundle")).toHaveText("Free trial");
    await expect(page.getByTestId("licence-days-left")).toHaveText("9");
    await expect(page.getByTestId("licence-trial-terms")).toContainText("deleted 30 days after the trial ends");
    await expect(page.getByTestId("licence-banner-days")).toHaveText("Trial: 9 days left");

    // other pages carry the banner; Arabic reads right to left
    await page.goto("/ar/projects");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("licence-banner-days")).toContainText("الفترة التجريبية");
    await page.goto("/ar/licence");
    await expect(page.getByTestId("licence-state")).toHaveText("ساري");
    await expect(page.getByTestId("licence-trial-terms")).toContainText("نظام حماية البيانات الشخصية");
  });

  test("an expired licence shows the read-only banner to everyone (EN / AR)", async ({ page }) => {
    await mockExpired(page);
    await login(page, USERS.noura);
    const banner = page.getByTestId("licence-banner");
    await expect(banner).toHaveAttribute("data-state", "expired");
    await expect(banner).toContainText("Licence expired, read-only");
    await expect(banner).toContainText("Ask your HSE Manager to enter a new licence key.");
    await expect(page.getByTestId("licence-banner-link")).toHaveCount(0); // officers cannot renew
    await page.goto("/ar");
    await expect(banner).toContainText("انتهى الترخيص، للقراءة فقط");
    await expect(banner).toContainText("ستُحذف بيانات الفترة التجريبية");
  });

  test("the HSE Manager reaches the licence page from the read-only banner", async ({ page }) => {
    await mockExpired(page);
    await login(page, USERS.faisal);
    await page.getByTestId("licence-banner-link").click();
    await expect(page.getByTestId("licence-page")).toBeVisible();
    await expect(page.getByTestId("licence-state")).toHaveText("Expired, read-only");
    await expect(page.getByTestId("licence-key-input")).toBeVisible();
  });
});
