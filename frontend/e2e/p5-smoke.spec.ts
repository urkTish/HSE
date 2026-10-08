import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";

/** Every Phase 5 training register renders against the real backend in EN and AR without an error state. */
const PAGES = [
  "/training-courses",
  "/training-courses/WAH",
  "/training-providers",
  "/trainer-authorisations",
  "/training-matrix",
  "/training-gaps",
  "/training-exemptions",
  "/refresher-plan",
  "/training-sessions",
  "/training-sessions/new",
  "/training-records",
  "/training-records/new",
  "/training-verification-log",
  "/training-imports",
  "/training-settings",
];

const RAW_KEY = /\b(training|enums|common|hookPolicy|certCheck|dashboard)\.[a-zA-Z_]+\.[a-zA-Z_]+/;

for (const locale of ["en", "ar"] as const) {
  test(`Phase 5 training registers render (${locale})`, async ({ page }) => {
    test.setTimeout(240_000);
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

test("Training navigation group: full for the HSE Manager, limited for a contractor rep", async ({ page }) => {
  await login(page, USERS.faisal);
  await expect(page.getByTestId("nav-training")).toBeVisible();
  for (const id of ["nav-training-sessions", "nav-training-records", "nav-training-matrix", "nav-training-catalogue", "nav-training-imports", "nav-training-settings"]) {
    await expect(page.getByTestId(id), id).toBeVisible();
  }
  await page.getByTestId("nav-training-sessions").click();
  await expect(page).toHaveURL(/\/training-sessions/);
  await expect(page.getByTestId("sessions-table")).toBeVisible();

  await login(page, USERS.ahmed);
  await expect(page.getByTestId("nav-training-records")).toBeVisible();
  await expect(page.getByTestId("nav-training-catalogue")).toBeVisible();

  await login(page, USERS.sarah);
  await expect(page.getByTestId("nav-training-imports")).toHaveCount(0);
});
