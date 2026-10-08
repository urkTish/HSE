import { expect, test } from "./fixtures/test";
import en from "../messages/en.json" with { type: "json" };
import { apiAs, login, sql, uid, USERS, selectByPrefix } from "./helpers";

async function inviteViaUi(page: import("@playwright/test").Page, email: string, name: string) {
  await login(page, USERS.faisal);
  await page.goto("/en/users/invite");
  await page.locator("#email").fill(email);
  await page.locator("#full_name_en").fill(name);
  await page.locator("#employer_type").selectOption("client");
  await page.getByTestId("assignment-role").selectOption("viewer_client");
  await selectByPrefix(page.getByTestId("assignment-project"), "RBT-52");
  await page.getByTestId("save").click();
  await expect(page.getByTestId("user-title")).toHaveText(name);
  await expect(page.locator("[data-status=invited]")).toBeVisible();
}

function inviteLink(email: string): string {
  const body = sql(`select body from email_outbox where to_email='${email}' and template='invite' order by created_at desc limit 1`);
  const m = /\/(?:en|ar)\/invite\?token=[^\s]+/.exec(body);
  if (!m) throw new Error(`no invite link for ${email}`);
  return m[0];
}

test.describe("Invitations & privacy notice", () => {
  test("Invite → accept (set password + privacy ack) → home; AC5 re-ack is enforced", async ({ page }) => {
    const email = `e2e.viewer.${uid().toLowerCase()}@example.com`;
    await inviteViaUi(page, email, "E2E Viewer");
    await page.context().clearCookies();

    await page.goto(inviteLink(email).replace(/^\/ar\//, "/en/"));
    await expect(page.getByText("Welcome, E2E Viewer")).toBeVisible();
    await expect(page.getByTestId("privacy-text")).not.toBeEmpty();
    await page.locator("#password").fill("New-Strong-Pass-2026!");
    await page.locator("#confirm").fill("New-Strong-Pass-2026!");
    await page.locator("#ack").check();
    await page.getByRole("button", { name: en.auth.invite.submit }).click();
    await expect(page.getByTestId("home")).toBeVisible();

    // AC5: without a current acknowledgement every API call is blocked → the UI shows the notice.
    sql(`update users set privacy_notice_version=null, privacy_notice_ack_at=null where email='${email}'`);
    await page.context().clearCookies();
    await page.goto("/en/login");
    await page.locator("#email").fill(email);
    await page.locator("#password").fill("New-Strong-Pass-2026!");
    await page.locator("button[type=submit]").click();
    await expect(page).toHaveURL(/\/en\/privacy/);
    const api = await apiAs(email, "New-Strong-Pass-2026!");
    const res = await api.get("/api/v1/projects");
    expect(res.status()).toBe(403);
    expect((await res.json()).detail.code).toBe("PRIVACY_ACK_REQUIRED");
    await page.getByRole("button", { name: en.auth.privacy.submit }).click();
    await expect(page.getByText(en.auth.privacy.mustAck)).toBeVisible();
    await page.locator("#privacy-ack").check();
    await page.getByRole("button", { name: en.auth.privacy.submit }).click();
    await expect(page.getByTestId("home")).toBeVisible();
  });

  test("AC4: an invitation older than 72 h is rejected as expired", async ({ page }) => {
    const email = `e2e.expired.${uid().toLowerCase()}@example.com`;
    await inviteViaUi(page, email, "E2E Expired");
    // Relative to the shared e2e clock (e2e/clock.ts), not the database's wall clock.
    const at = new Date().toISOString();
    sql(
      `update user_tokens set created_at = timestamptz '${at}' - interval '73 hours', expires_at = timestamptz '${at}' - interval '1 hour' where user_id = (select id from users where email='${email}')`,
    );
    await page.context().clearCookies();
    await page.goto(inviteLink(email).replace(/^\/ar\//, "/en/"));
    await expect(page.getByTestId("invite-error")).toHaveText(en.errors.code.INVITE_EXPIRED);
  });
});
