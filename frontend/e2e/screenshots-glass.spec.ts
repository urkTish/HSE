import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Browser, type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { pinProject } from "./p6a-helpers";

// Glass restyle proof of concept (D-277): the screens the HSE Manager reviews, EN and AR, light and dark,
// desktop and phone, to docs/screenshots/glass/<name>-<locale>.png. Run with SCREENSHOTS=1 on a fresh seed.
// The "before" set is docs/screenshots/restyle/*-after.png.
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "glass");
const SEP = "period=month&anchor=2026-09-15";
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(900_000);

type Items<T> = { items: T[] };
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

async function shot(page: Page, name: string, locale: string, fullPage = false) {
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  await page.waitForTimeout(900);
  await page.screenshot({ path: join(OUT, `${name}-${locale}.png`), fullPage });
}

/** A real phone context: coarse pointer, so the surface defaults to Solid unless `surface` is "glass". */
async function phone(browser: Browser, locale: "en" | "ar", surface?: "glass") {
  const ctx = await browser.newContext({
    viewport: PHONE,
    isMobile: true,
    hasTouch: true,
    locale: locale === "ar" ? "ar-SA" : "en-GB",
    timezoneId: "Asia/Riyadh",
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
  });
  if (surface) await ctx.addInitScript((s) => window.localStorage.setItem("hse.surface", s), surface);
  return { ctx, page: await ctx.newPage() };
}

for (const locale of ["en", "ar"] as const) {
  test(`glass set (${locale})`, async ({ page, browser }) => {
    mkdirSync(OUT, { recursive: true });
    const faisal = await apiAs(USERS.faisal);
    const pid = await projectId(faisal, "ANIA-EXP");
    const permits = await getJson<Items<{ id: string; permit_no: string }>>(faisal, `/api/v1/projects/${pid}/permits?q=0413&page_size=50`);
    const p0413 = permits.items.find((p) => p.permit_no === "PTW-ANIA-EXP-2026-0413")?.id;
    const go = (path: string) => page.goto(`/${locale}${path}`);

    // Login, desktop.
    await page.setViewportSize(DESKTOP);
    await go("/login");
    await expect(page.locator("form").first()).toBeVisible();
    await shot(page, "01-login-desktop", locale);

    // Dashboard, desktop, light: full page, then the theme menu open on its Surface section.
    await login(page, USERS.noura, locale);
    await go(`?${SEP}`);
    for (const id of ["chart-C1", "chart-C7"]) await expect(page.getByTestId(id)).toBeVisible({ timeout: 60_000 });
    await page.waitForTimeout(1500);
    await shot(page, "02-dashboard-desktop", locale, true);
    await page.getByTestId("theme-toggle").click();
    await expect(page.getByTestId("surface-glass")).toBeVisible();
    await shot(page, "03-theme-menu-desktop", locale);
    await page.keyboard.press("Escape");

    // Dashboard, desktop, dark.
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForTimeout(400);
    await shot(page, "04-dashboard-dark-desktop", locale, true);

    // A register and a record (dark), then light again.
    await pinProject(page, "ANIA-EXP");
    await go("/incidents");
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await shot(page, "05-register-dark-desktop", locale);
    await page.emulateMedia({ colorScheme: "light" });
    await go("/incidents");
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await shot(page, "06-register-desktop", locale);
    await go("/incidents/new");
    await expect(page.locator("form").first()).toBeVisible();
    await shot(page, "07-form-desktop", locale, true);

    // A permit (Faisal), desktop.
    await page.context().clearCookies();
    await login(page, USERS.faisal, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/permits/${p0413}`);
    await expect(page.getByTestId("permit-detail")).toBeVisible();
    await shot(page, "08-permit-desktop", locale);

    // Phone: the default (Solid on a touch screen) and the same screens with Glass switched on.
    for (const surface of [undefined, "glass"] as const) {
      const sfx = surface ? "glass" : "solid";
      const { ctx, page: mp } = await phone(browser, locale, surface);
      await mp.goto(`/${locale}/login`);
      await expect(mp.locator("form").first()).toBeVisible();
      await shot(mp, `09-login-phone-${sfx}`, locale);
      await login(mp, USERS.noura, locale);
      await mp.goto(`/${locale}?${SEP}`);
      await expect(mp.getByTestId("lagging-tiles")).toBeVisible({ timeout: 60_000 });
      await mp.waitForTimeout(1200);
      await shot(mp, `10-dashboard-phone-${sfx}`, locale);
      await mp.getByTestId("open-menu").click();
      await expect(mp.getByTestId("mobile-nav")).toBeVisible();
      await mp.waitForTimeout(400);
      await shot(mp, `11-drawer-phone-${sfx}`, locale);
      await ctx.close();
    }
  });
}
