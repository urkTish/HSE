import { expect, test } from "@playwright/test";
import { login, USERS } from "./helpers";

/** Every Phase 2 register renders against the real backend in EN and AR without an error state. */
const PAGES = [
  "/workers",
  "/inductions",
  "/induction-courses",
  "/zone-profiles",
  "/pass-setup",
  "/pass-applications",
  "/airport-passes",
  "/adps",
  "/offences",
  "/vehicles",
  "/avps",
  "/notams",
  "/obstacle-clearances",
  "/waps",
  "/wap-board",
  "/ops-events",
  "/gates",
  "/gate-log",
  "/access-settings",
];

for (const locale of ["en", "ar"] as const) {
  test(`Phase 2 registers render (${locale})`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await login(page, USERS.faisal, locale);
    for (const p of PAGES) {
      await page.goto(`/${locale}${p}`);
      await expect(page.locator("h1").first(), p).toBeVisible();
      await page.waitForLoadState("networkidle");
      await expect(page.getByTestId("error-state"), p).toHaveCount(0);
      const text = await page.locator("main").innerText();
      expect(text, `${p} shows a raw message key`).not.toMatch(/\b(workers|waps|gates|passes|adps|vehicles|notams|obstacles|inductions|accessSettings|zoneProfiles|passSetup|enums|common|access|credentials)\.[a-zA-Z_]+/);
    }
    expect(errors).toEqual([]);
  });
}
