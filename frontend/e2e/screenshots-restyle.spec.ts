import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Browser, type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, uid, USERS } from "./helpers";
import { accessCard, createWorker, ensureGenCourse, projectIds, recordInduction } from "./p2-helpers";
import { pinProject } from "./p6a-helpers";

// Platform restyle (emerald brand, platinum neutrals): a representative before/after set for
// docs/screenshots/restyle/<name>-<locale>-<suffix>.png. Run with SCREENSHOTS=1 SHOT_SUFFIX=before|after on a fresh seed.
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "restyle");
const SFX = process.env.SHOT_SUFFIX ?? "after";
const SEP = "period=month&anchor=2026-09-15";
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(900_000);

type Items<T> = { items: T[] };
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

async function shot(page: Page, name: string, locale: string, fullPage = false) {
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  await page.waitForTimeout(900);
  await page.screenshot({ path: join(OUT, `${name}-${locale}-${SFX}.png`), fullPage });
}

async function phone(browser: Browser, locale: "en" | "ar") {
  const ctx = await browser.newContext({
    viewport: PHONE,
    isMobile: true,
    hasTouch: true,
    locale: locale === "ar" ? "ar-SA" : "en-GB",
    timezoneId: "Asia/Riyadh",
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
  });
  return { ctx, page: await ctx.newPage() };
}

for (const locale of ["en", "ar"] as const) {
  test(`restyle set (${locale})`, async ({ page, browser }) => {
    mkdirSync(OUT, { recursive: true });
    const faisal = await apiAs(USERS.faisal);
    const pid = await projectId(faisal, "ANIA-EXP");
    const permits = await getJson<Items<{ id: string; permit_no: string }>>(faisal, `/api/v1/projects/${pid}/permits?q=0413&page_size=50`);
    const p0413 = permits.items.find((p) => p.permit_no === "PTW-ANIA-EXP-2026-0413")?.id;
    const cards = await getJson<Items<{ id: string; engagement_code: string; scope: string }>>(faisal, `/api/v1/projects/${pid}/scorecards?month=2026-09&page_size=50`);
    const najd = cards.items.find((c) => c.engagement_code === "NAJD" && c.scope === "own")?.id ?? cards.items[0]?.id;
    const go = (path: string) => page.goto(`/${locale}${path}`);

    // Login: desktop and phone.
    await page.setViewportSize(DESKTOP);
    await go("/login");
    await expect(page.locator("form").first()).toBeVisible();
    await shot(page, "01-login-desktop", locale);
    await page.setViewportSize(PHONE);
    await shot(page, "02-login-phone", locale);

    // Dashboard: desktop (full page) and phone.
    await page.setViewportSize(DESKTOP);
    await login(page, USERS.noura, locale);
    await go(`?${SEP}`);
    for (const id of ["chart-C1", "chart-C7"]) await expect(page.getByTestId(id)).toBeVisible({ timeout: 60_000 });
    await page.waitForTimeout(1500);
    await shot(page, "03-dashboard-desktop", locale, true);
    await page.setViewportSize(PHONE);
    await expect(page.getByTestId("lagging-tiles")).toBeVisible();
    await shot(page, "04-dashboard-phone", locale);

    // A list/register, a form, the heat board (desktop).
    await page.setViewportSize(DESKTOP);
    await pinProject(page, "ANIA-EXP");
    await go("/incidents");
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await shot(page, "05-register-desktop", locale);
    await go("/incidents/new");
    await expect(page.locator("form").first()).toBeVisible();
    await shot(page, "06-form-desktop", locale, true);
    await go("/heat-board");
    await expect(page.getByTestId("zone-card").first()).toBeVisible();
    await shot(page, "07-heat-board-desktop", locale, true);

    // A permit (Faisal), desktop and phone; a scorecard card.
    await page.context().clearCookies();
    await login(page, USERS.faisal, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/permits/${p0413}`);
    await expect(page.getByTestId("permit-detail")).toBeVisible();
    await shot(page, "08-permit-desktop", locale);
    await page.setViewportSize(PHONE);
    await shot(page, "09-permit-phone", locale);
    await page.setViewportSize(DESKTOP);
    await go(`/scorecards/${najd}`);
    await expect(page.getByTestId("sc-pillar").first()).toBeVisible();
    await shot(page, "10-scorecard-desktop", locale);
    await page.setViewportSize(PHONE);
    await shot(page, "11-scorecard-phone", locale);

    // Dark theme: the dashboard and a register, desktop.
    await page.setViewportSize(DESKTOP);
    await page.emulateMedia({ colorScheme: "dark" });
    await go("/incidents");
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await shot(page, "12-register-dark-desktop", locale);
    await page.emulateMedia({ colorScheme: "light" });

    // Gate check on a phone: a device on a seeded gate, one worker with a valid induction → GRANTED.
    const ids = await projectIds(faisal);
    const gates = await getJson<Items<{ id: string; gate_code: string; status?: string }>>(faisal, `/api/v1/projects/${pid}/gates`);
    const gate = gates.items.find((g) => g.gate_code === "G-ANIA-01") ?? gates.items[0]!;
    const reg = await faisal.post(`/api/v1/gates/${gate.id}/devices`, { data: { device_id: `RS-${uid()}`.slice(0, 40), label: "Restyle phone" } });
    expect(reg.ok(), await reg.text()).toBeTruthy();
    const token = ((await reg.json()) as { device_token: string }).device_token;
    const gen = await ensureGenCourse(faisal, ids.pid);
    const ok = await createWorker(faisal, ids, `Restyle Gate ${uid()}`);
    await recordInduction(faisal, ids.pid, ok.id, gen);
    const okRef = (await accessCard(faisal, ok.deploymentId)).printed_ref;
    const { ctx, page: gp } = await phone(browser, locale);
    await gp.goto(`/${locale}/gate`);
    await gp.getByTestId("device-token-input").fill(token);
    await gp.getByTestId("device-login").click();
    await expect(gp.getByTestId("gate-ready")).toBeVisible();
    await shot(gp, "13-gate-ready-phone", locale);
    await gp.getByTestId("manual-ref").fill(okRef);
    await gp.getByTestId("manual-check").click();
    await expect(gp.getByTestId("gate-result")).toHaveAttribute("data-result", /.+/);
    await shot(gp, "14-gate-result-phone", locale);
    await ctx.close();
  });
}
