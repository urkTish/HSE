import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Browser, type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, uid, USERS } from "./helpers";
import { deploymentOf } from "./p5-helpers";
import { pinProject, USERS6 } from "./p6a-helpers";

// Cross-module consistency pass: the most-used older screens in EN and AR, for docs/screenshots/consistency.
// Run with SCREENSHOTS=1 on a fresh seed; SHOT_SUFFIX=before|after names the files (default "after").
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "consistency");
const SFX = process.env.SHOT_SUFFIX ?? "after";
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(300_000);

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, `${name}-${SFX}.png`), fullPage });
}

async function idOf(path: string, key: string, value: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, "ANIA-EXP");
  const url = path.startsWith("/") ? `${path}?project_id=${pid}&q=${encodeURIComponent(value)}&page_size=50` : `/api/v1/projects/${pid}/${path}?q=${encodeURIComponent(value)}&page_size=50`;
  const list = await getJson<{ items: Record<string, string>[] }>(api, url);
  return list.items.find((x) => x[key] === value || String(x[key] ?? "").startsWith(value))?.id ?? "";
}

async function phone(browser: Browser, locale: "en" | "ar") {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: locale === "ar" ? "ar-SA" : "en-GB", timezoneId: "Asia/Riyadh" });
  return { ctx, page: await ctx.newPage() };
}

for (const locale of ["en", "ar"] as const) {
  test(`consistency pass screenshots (${locale})`, async ({ page, browser }) => {
    mkdirSync(OUT, { recursive: true });
    const permit = await idOf("permits", "permit_no", "PTW-ANIA-EXP-2026-0413");
    const mc03 = await idOf("/api/v1/equipment", "current_tag", "RW-MC-03");
    const nadeem = await deploymentOf("ANIA-EXP", "WKR-000022");
    const sunil = await deploymentOf("ANIA-EXP", "WKR-000034");

    // 1. Gate check on the guard's phone: a scan result.
    {
      const api = await apiAs(USERS.faisal);
      const pid = await projectId(api, "ANIA-EXP");
      const gates = await getJson<{ items: { id: string; gate_code: string }[] }>(api, `/api/v1/projects/${pid}/gates`);
      const g = gates.items.find((x) => x.gate_code === "G-ANIA-01");
      const res = await api.post(`/api/v1/gates/${g?.id}/devices`, { data: { device_id: `TAB-CONS-${uid()}`, label: "Consistency tablet" } });
      const token = ((await res.json()) as { device_token: string }).device_token;
      const { ctx, page: gp } = await phone(browser, locale);
      await gp.goto(`/${locale}/gate`);
      await gp.getByTestId("device-token-input").fill(token);
      await gp.getByTestId("device-login").click();
      await expect(gp.getByTestId("gate-ready")).toBeVisible();
      await gp.getByTestId("manual-ref").fill("ANIA-EXP-RW-MEWP-07");
      await gp.getByTestId("manual-check").click();
      await expect(gp.getByTestId("gate-result")).toBeVisible();
      await shot(gp, `01-gate-phone-${locale}`);
      await ctx.close();
    }

    // 2–4. Phone views as the HSE Manager: permit detail, scaffold board, worker page.
    {
      const { ctx, page: m } = await phone(browser, locale);
      await login(m, USERS.faisal, locale);
      await pinProject(m);
      await m.goto(`/${locale}/permits/${permit}`);
      await expect(m.getByTestId("permit-status")).toBeVisible();
      await shot(m, `02-permit-phone-${locale}`, true);
      await m.goto(`/${locale}/scaffold-board`);
      await expect(m.getByTestId("scaffold-board")).toBeVisible();
      await shot(m, `03-scaffold-board-phone-${locale}`, true);
      await m.goto(`/${locale}/workers/${nadeem.worker_id}`);
      await expect(m.getByTestId("worker-title")).toBeVisible();
      await shot(m, `04-worker-phone-${locale}`, true);
      await ctx.close();
    }

    // 5–6. Desktop: dashboard and equipment page.
    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page, USERS.faisal, locale);
    await pinProject(page);
    await page.goto(`/${locale}`);
    await expect(page.getByTestId("headline")).toBeVisible({ timeout: 30_000 });
    await shot(page, `05-dashboard-${locale}`, true);
    await page.goto(`/${locale}/equipment/${mc03}`);
    await expect(page.getByTestId("current-line")).toBeVisible();
    await shot(page, `06-equipment-${locale}`, true);

    // 7. Worker health (6a) as the occupational health user.
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: locale === "ar" ? "ar-SA" : "en-GB", timezoneId: "Asia/Riyadh" });
      const h = await ctx.newPage();
      await login(h, USERS6.huda, locale);
      await pinProject(h);
      await h.goto(`/${locale}/worker-health/${sunil.worker_id}?dep=${sunil.id}`);
      await expect(h.getByTestId("worker-fitness")).toBeVisible();
      await shot(h, `07-worker-health-${locale}`, true);
      await ctx.close();
    }
  });
}
