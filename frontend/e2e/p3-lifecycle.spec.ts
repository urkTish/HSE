import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, PASSWORD, sql, USERS } from "./helpers";

/** Permit lifecycle on the Appendix A seed (shared e2e clock = 2026-10-06 10:00 Riyadh). */

const FARIS = "faris.anazi@example.com";

async function permitId(no: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const projects = await getJson<{ items: { id: string; code: string }[] }>(api, "/api/v1/projects?q=ANIA-EXP");
  const pid = projects.items.find((p) => p.code === "ANIA-EXP")?.id ?? "";
  const list = await getJson<{ items: { id: string; permit_no: string }[] }>(api, `/api/v1/projects/${pid}/permits?q=${no}`);
  return list.items.find((p) => p.permit_no === no)?.id ?? "";
}

async function act(page: Page, k: string) {
  await page.getByTestId(`act-${k}`).click();
  return page.getByRole("dialog");
}

test("AC59 shift end is refused while entrants are inside the space", async ({ page }) => {
  const id = await permitId("PTW-ANIA-EXP-2026-0413");
  await login(page, FARIS);
  await page.goto(`/en/permits/${id}`);
  const dlg = await act(page, "end_shift");
  await dlg.getByTestId("step-confirm").click();
  await expect(dlg.getByTestId("form-error")).toHaveAttribute("data-code", "ENTRANTS_INSIDE");
});

test("AC86/AC8 stop work by the contractor HSE rep; the issuer resumes after re-authentication", async ({ page }) => {
  const id = await permitId("PTW-ANIA-EXP-2026-0412");
  await login(page, USERS.ahmed);
  await page.goto(`/en/permits/${id}`);
  let dlg = await act(page, "suspend");
  await dlg.getByTestId("st-reason").selectOption("stop_work");
  await dlg.getByTestId("st-detail").fill("Sparks reaching the cable tray below; stopped until a fire blanket is fitted.");
  await dlg.getByTestId("step-confirm").click();
  await expect(dlg).toHaveCount(0);
  await expect(page.getByTestId("permit-status")).toHaveAttribute("data-status", "suspended");
  await expect(page.getByTestId("act-resume")).toHaveCount(0);

  await page.context().clearCookies();
  await login(page, USERS.khalid);
  // Khalid last authenticated 20 minutes ago: the signature asks for his password first (PT-15).
  sql(`UPDATE user_sessions SET last_authenticated_at = last_authenticated_at - interval '20 minutes' WHERE user_id = (SELECT id FROM users WHERE email = '${USERS.khalid}')`);
  await page.goto(`/en/permits/${id}`);
  dlg = await act(page, "resume");
  await dlg.getByTestId("st-site-visit").check();
  await dlg.getByTestId("st-cause").fill("Fire blanket fitted over the cable tray and checked by the fire watch.");
  const rows = dlg.getByTestId("crew-present-row");
  for (let i = 0; i < (await rows.count()); i++) await rows.nth(i).getByTestId("crew-present-check").check();
  await dlg.getByTestId("st-temp").fill("34.0");
  await dlg.getByTestId("cosign-here").check();
  await dlg.getByTestId("cosign-password").fill(PASSWORD);
  await dlg.getByTestId("step-confirm").click();
  const reauth = page.getByTestId("reauth-dialog");
  await expect(reauth).toBeVisible();
  await reauth.getByTestId("reauth-password").fill(PASSWORD);
  await reauth.getByTestId("reauth-confirm").click();
  await expect(page.getByTestId("permit-status")).toHaveAttribute("data-status", "active");
});
