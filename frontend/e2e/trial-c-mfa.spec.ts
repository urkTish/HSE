import { createHmac } from "node:crypto";
import { expect, test } from "./fixtures/test";
import en from "../messages/en.json" with { type: "json" };
import ar from "../messages/ar.json" with { type: "json" };
import { apiAs, login, PASSWORD, sql, USERS, userId } from "./helpers";

/** RFC 6238 TOTP (SHA-1, 6 digits, 30 s) on the shared e2e clock (this process's Date is the API's). */
function totp(secret: string, stepOffset = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/\s/g, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const step = Math.floor(Date.now() / 1000 / 30) + stepOffset;
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(step));
  const mac = createHmac("sha1", key).update(msg).digest();
  const off = mac[mac.length - 1] & 0x0f;
  const value = (mac.readUInt32BE(off) & 0x7fffffff) % 1_000_000;
  return String(value).padStart(6, "0");
}

function clearMfa(email: string): void {
  const uid = `(SELECT id FROM users WHERE email = '${email}')`;
  sql(`DELETE FROM user_mfa_recovery_codes WHERE user_id = ${uid}`);
  sql(
    `UPDATE users SET mfa_enabled = false, mfa_secret_enc = NULL, mfa_pending_secret_enc = NULL, mfa_enabled_at = NULL, mfa_last_step = NULL, mfa_required_since = NULL, status = 'active', locked_until = NULL, failed_login_count = 0, failed_window_started_at = NULL WHERE email = '${email}'`,
  );
}

test.describe("Two-step verification (D-299)", () => {
  test.afterAll(() => {
    clearMfa(USERS.noura);
    clearMfa(USERS.faisal);
  });

  test("an officer turns it on from the profile, then signs in with a code and with a recovery code (AR)", async ({ page }) => {
    clearMfa(USERS.noura);
    await login(page, USERS.noura);
    await expect(page.getByTestId("mfa-banner")).toHaveCount(0); // optional for an HSE Officer
    await page.goto("/en/profile");
    await expect(page.getByTestId("mfa-status")).toHaveText(en.mfa.statusOff);
    await page.getByTestId("mfa-setup-link").click();
    await expect(page).toHaveURL(/\/en\/mfa-setup$/);
    await page.getByTestId("mfa-start").click();
    await expect(page.getByTestId("qr-image")).toBeVisible();
    const secret = (await page.getByTestId("mfa-secret").innerText()).replace(/\s/g, "");
    await page.getByTestId("mfa-setup-code-input").fill("123");
    await page.getByTestId("mfa-confirm").click();
    await expect(page.getByText(en.mfa.codeInvalid)).toBeVisible();
    await page.getByTestId("mfa-setup-code-input").fill(totp(secret));
    await page.getByTestId("mfa-confirm").click();
    const codes = page.getByTestId("mfa-recovery-code");
    await expect(codes).toHaveCount(10);
    const first = (await codes.first().innerText()).trim();
    await page.getByTestId("mfa-finish").click();
    await expect(page.getByTestId("topbar")).toBeVisible();

    // Sign in again in Arabic: the code step appears after the password.
    await page.getByTestId("user-menu").click();
    await page.getByTestId("logout").click();
    await page.goto("/ar/login");
    await page.locator("#email").fill(USERS.noura);
    await page.locator("#password").fill(PASSWORD);
    await page.locator("button[type=submit]").click();
    await expect(page.getByTestId("mfa-verify")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("mfa-verify")).toContainText(ar.mfa.verify.title);
    await page.getByTestId("mfa-code-input").fill("000000");
    await page.getByTestId("mfa-verify-submit").click();
    await expect(page.getByTestId("mfa-verify")).toContainText(ar.errors.code.MFA_CODE_INVALID);
    await page.getByTestId("mfa-toggle-recovery").click();
    await page.getByTestId("mfa-recovery-input").fill(first);
    await page.getByTestId("mfa-verify-submit").click();
    await expect(page.getByTestId("topbar")).toBeVisible();

    // And with the app code (the next 30 s step: the confirm code's step is spent).
    await page.getByTestId("user-menu").click();
    await page.getByTestId("logout").click();
    await page.goto("/en/login");
    await page.locator("#email").fill(USERS.noura);
    await page.locator("#password").fill(PASSWORD);
    await page.locator("button[type=submit]").click();
    await page.getByTestId("mfa-code-input").fill(totp(secret, 1));
    await page.getByTestId("mfa-verify-submit").click();
    await expect(page.getByTestId("topbar")).toBeVisible();
    await page.goto("/en/profile");
    await expect(page.getByTestId("mfa-status")).toHaveText(en.mfa.statusOn);
    await expect(page.getByTestId("mfa-codes-left")).toContainText("9");
  });

  test("the HSE Manager sees the set-up banner, is held at the set-up page after the grace period, and a manager can reset a lost phone", async ({ page }) => {
    clearMfa(USERS.faisal);
    await login(page, USERS.faisal);
    await expect(page.getByTestId("mfa-banner")).toBeVisible();
    await page.getByTestId("user-menu").click();
    await page.getByTestId("logout").click();

    // Grace period over (the e2e clock runs at 2026-10-06; the database clock is real time).
    sql(`UPDATE users SET mfa_required_since = now() - interval '60 days' WHERE email = '${USERS.faisal}'`);
    await page.goto("/en/login");
    await page.locator("#email").fill(USERS.faisal);
    await page.locator("#password").fill(PASSWORD);
    await page.locator("button[type=submit]").click();
    await expect(page).toHaveURL(/\/en\/mfa-setup$/);
    await expect(page.getByTestId("mfa-blocking")).toBeVisible();
    const res = await page.request.get("/api/v1/projects");
    expect(res.status()).toBe(403);
    expect((await res.json()).detail.code).toBe("MFA_ENROLMENT_REQUIRED");
    await page.goto("/en/projects");
    await expect(page).toHaveURL(/\/en\/mfa-setup$/);
    clearMfa(USERS.faisal);

    // Lost phone: the HSE Manager resets Noura's two-step verification.
    sql(`UPDATE users SET mfa_enabled = true WHERE email = '${USERS.noura}'`);
    const fa = await apiAs(USERS.faisal);
    const nid = await userId(fa, USERS.noura);
    await fa.dispose();
    await login(page, USERS.faisal);
    await page.goto(`/en/users/${nid}`);
    await page.getByTestId("mfa-reset").click();
    await page.getByTestId("mfa-reset-confirm").click();
    await expect(page.getByText(en.user.mfaReset.done)).toBeVisible();
    await expect(page.getByTestId("mfa-reset")).toHaveCount(0);
  });
});
