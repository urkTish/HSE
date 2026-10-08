import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";

/** Every Phase 4 certification register renders against the real backend in EN and AR without an error state. */
const PAGES = [
  "/tpis",
  "/tpi-approvals",
  "/equipment",
  "/equipment-deployments",
  "/equipment-certificates",
  "/equipment-certificates/new",
  "/verification-log",
  "/scaffolds",
  "/scaffold-board",
  "/personnel-certificates",
  "/personnel-certificates/new",
  "/certification-bans",
  "/blacklist-register",
  "/defects",
  "/cert-settings",
  "/cert-catalogue",
  "/hook-policy",
  "/certificate-imports",
  "/cert-check",
];

const RAW_KEY =
  /\b(cert|tpis|eqDeployments|eqCerts|scaffolds|pcerts|bans|defects|certSettings|certCatalogue|hookPolicy|certImports|certCheck|enums|common)\.[a-zA-Z_]+/;

for (const locale of ["en", "ar"] as const) {
  test(`Phase 4 certification registers render (${locale})`, async ({
    page,
  }) => {
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

test("Certification navigation group is shown to the HSE Manager and hidden from the viewer", async ({
  page,
}) => {
  await login(page, USERS.faisal);
  await expect(page.getByTestId("nav-cert")).toBeVisible();
  for (const id of [
    "nav-equipment",
    "nav-equipment-certs",
    "nav-scaffolds",
    "nav-personnel-certs",
    "nav-defects",
    "nav-tpis",
    "nav-cert-setup",
  ]) {
    await expect(page.getByTestId(id), id).toBeVisible();
  }
  await page.getByTestId("user-menu").click();
  await page.getByTestId("logout").click();
  await login(page, USERS.sarah);
  await expect(page.getByTestId("nav-personnel-certs")).toHaveCount(0);
});
