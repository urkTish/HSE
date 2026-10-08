import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";

/** Every Phase 3 PTW register renders against the real backend in EN and AR without an error state. */
const PAGES = [
  "/permits",
  "/permits/new",
  "/ptw-board",
  "/permit-suspensions",
  "/gas-tests",
  "/gas-tests/new",
  "/gas-detectors",
  "/isolations",
  "/isolations/new",
  "/locks",
  "/simops-conflicts",
  "/jsa-templates",
  "/jsa-templates/new",
  "/ptw-audits",
  "/ptw-audits/new",
  "/ptw-appointments",
  "/ptw-setup",
  "/ptw-setup/settings",
  "/ptw-setup/types",
  "/ptw-setup/risk-matrix",
  "/ptw-setup/zones",
  "/ptw-setup/simops-rules",
  "/ptw-setup/adjacency",
];

const RAW_KEY = /\b(permits|permitDetail|permitSections|permitActions|permitCrew|fieldRecords|simops|jsa|gas|isolations|ptwBoard|ptwPrint|ptwAudits|ptwSetup|ptwAppointments|enums|common)\.[a-zA-Z_]+/;

for (const locale of ["en", "ar"] as const) {
  test(`Phase 3 PTW registers render (${locale})`, async ({ page }) => {
    test.setTimeout(180_000);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await login(page, USERS.faisal, locale);
    for (const p of PAGES) {
      await page.goto(`/${locale}${p}`);
      await expect(page.locator("h1").first(), p).toBeVisible();
      await page.waitForLoadState("networkidle");
      await expect(page.getByTestId("error-state"), p).toHaveCount(0);
      const text = await page.locator("main").innerText();
      expect(text, `${p} shows a raw message key`).not.toMatch(RAW_KEY);
    }
    expect(errors).toEqual([]);
  });
}

test("PTW navigation group is shown to the HSE Manager", async ({ page }) => {
  await login(page, USERS.faisal);
  await expect(page.getByTestId("nav-ptw")).toBeVisible();
  await expect(page.getByTestId("nav-permits")).toBeVisible();
  await expect(page.getByTestId("nav-ptw-setup")).toBeVisible();
});
