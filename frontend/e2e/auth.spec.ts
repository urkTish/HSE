import { expect, test } from "./fixtures/test";
import en from "../messages/en.json" with { type: "json" };
import { apiAs, login, PASSWORD, USERS, userId } from "./helpers";

test.describe("Authentication", () => {
  test("AC1: Faisal signs in (EN), reaches home and a login_success audit entry exists", async ({ page }) => {
    await login(page, USERS.faisal, "en");
    await expect(page).toHaveURL(/\/en$/);
    await expect(page.getByTestId("home")).toContainText("Welcome, Faisal Al-Harbi");
    await page.getByTestId("nav-audit").click();
    await page.locator("#audit-action").selectOption("login_success");
    const row = page.getByTestId("audit-row").filter({ hasText: "Faisal Al-Harbi" }).first();
    await expect(row).toBeVisible();
    await expect(row).toContainText(en.audit.action.login_success);
  });

  test("Login works in Arabic with RTL shell", async ({ page }) => {
    await login(page, USERS.faisal, "ar");
    await page.goto("/ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");
    await expect(page.getByTestId("home")).toContainText("مرحبًا");
    // Mirrored layout: the sidebar sits on the right in RTL.
    const box = await page.getByTestId("sidebar").boundingBox();
    const width = page.viewportSize()?.width ?? 0;
    expect(box && box.x > width / 2).toBeTruthy();
  });

  test("AC2: unknown email and wrong password give the identical message", async ({ page }) => {
    await page.goto("/en/login");
    await page.locator("#email").fill("nobody.here@example.com");
    await page.locator("#password").fill("Wrong-Password-123!");
    await page.locator("button[type=submit]").click();
    const unknown = await page.getByTestId("login-error").innerText();
    await page.locator("#email").fill(USERS.sarah);
    await page.locator("#password").fill("Wrong-Password-123!");
    await page.locator("button[type=submit]").click();
    await expect(page.getByTestId("login-error")).toHaveText(unknown);
    expect(unknown).toContain(en.errors.code.INVALID_CREDENTIALS);
  });

  test("AC27: Arabic login page sets dir/lang and shows no untranslated English text", async ({ page }) => {
    await page.goto("/ar/login");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");
    const text = await page.locator("body").innerText();
    // No raw message keys…
    expect(text).not.toMatch(/\b(auth|common|errors|validation)\.[a-zA-Z_.]+/);
    // …and none of the English login strings (except the deliberate "English" language switch).
    for (const s of [en.auth.login.title, en.auth.login.email, en.auth.login.password, en.auth.login.forgot, en.meta.appName]) {
      expect(text).not.toContain(s);
    }
    await page.locator("button[type=submit]").click();
    await expect(page.locator("#email-error")).toHaveText("هذا الحقل مطلوب.");
  });

  test("Language switch on the login page toggles EN ↔ AR", async ({ page }) => {
    await page.goto("/en/login");
    await page.getByTestId("language-switch").click();
    await expect(page).toHaveURL(/\/ar\/login/);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await page.getByTestId("language-switch").click();
    await expect(page).toHaveURL(/\/en\/login/);
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  });

  test("401 SESSION_EXPIRED returns to login with the expiry message", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: { code: "SESSION_EXPIRED", message: "Session expired" } }) }),
    );
    await page.goto("/en/projects");
    await expect(page).toHaveURL(/\/en\/login\?.*reason=expired/);
    await expect(page.getByTestId("session-expired")).toHaveText(en.auth.login.sessionExpired);
  });

  test("Sign out ends the session", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.getByTestId("user-menu").click();
    await page.getByTestId("logout").click();
    await expect(page).toHaveURL(/\/en\/login/);
    await page.goto("/en/projects");
    await expect(page).toHaveURL(/\/en\/login/);
  });

  test("AC3: 5 failures lock the account; HSE Manager unlocks it", async ({ page }) => {
    await page.goto("/en/login");
    for (let i = 0; i < 5; i++) {
      await page.locator("#email").fill(USERS.khalid);
      await page.locator("#password").fill(`Wrong-Password-${i}!`);
      await page.locator("button[type=submit]").click();
      await expect(page.getByTestId("login-error")).toBeVisible();
    }
    await page.locator("#email").fill(USERS.khalid);
    await page.locator("#password").fill(PASSWORD);
    await page.locator("button[type=submit]").click();
    await expect(page.getByTestId("login-error")).toContainText(en.auth.login.lockedTitle);
    await expect(page.getByTestId("login-error")).toContainText(en.errors.code.ACCOUNT_LOCKED);

    const api = await apiAs(USERS.faisal);
    const id = await userId(api, USERS.khalid);
    await login(page, USERS.faisal);
    await page.goto(`/en/users/${id}`);
    await expect(page.locator("[data-status=locked]")).toBeVisible();
    await page.getByTestId("transition-active").click();
    await page.getByTestId("transition-confirm").click();
    await expect(page.locator("[data-status=active]").first()).toBeVisible();

    await page.goto("/en/audit-log");
    await page.locator("#audit-action").selectOption("account_locked");
    await expect(page.getByTestId("audit-row").first()).toBeVisible();
  });
});
