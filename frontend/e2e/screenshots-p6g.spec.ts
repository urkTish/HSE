import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { pinProject } from "./p6a-helpers";

// Phase 6g demo screenshots for docs/screenshots/phase-6g (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6g");
const TARIQ = "tariq.mutairi@example.com";
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(900_000);

async function shot(page: Page, name: string, fullPage = true) {
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

type Items<T> = { items: T[] };

for (const locale of ["en", "ar"] as const) {
  test(`phase 6g screens (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    const faisal = await apiAs(USERS.faisal);
    const pid = await projectId(faisal, "ANIA-EXP");
    const cards = await getJson<Items<{ id: string; engagement_code: string }>>(faisal, `/api/v1/projects/${pid}/scorecards?month=2026-09&page_size=50`);
    const najd = cards.items.find((c) => c.engagement_code === "NAJD")?.id;
    const watch = await getJson<Items<{ id: string; entry_no: string }>>(faisal, `/api/v1/projects/${pid}/watch-list?page_size=50`);
    const sahara = watch.items.find((w) => w.entry_no.endsWith("-002"))?.id;
    const packs = await getJson<Items<{ id: string; doc_no: string; revision: number }>>(faisal, `/api/v1/projects/${pid}/report-packs?page_size=50`);
    const mcr = packs.items.find((p) => p.doc_no.endsWith("2026-08") && p.doc_no.startsWith("MCR") && p.revision === 1)?.id;
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.faisal, locale);
    await pinProject(page, "ANIA-EXP");
    await go("/scorecards?month=2026-09");
    await expect(page.getByTestId("sc-rank-row").first()).toBeVisible();
    await shot(page, `01-scorecard-register-${locale}.png`);
    await go(`/scorecards/${najd}`);
    await expect(page.getByTestId("sc-pillar").first()).toBeVisible();
    await shot(page, `02-scorecard-najd-${locale}.png`);
    await go("/scorecard-remarks");
    await expect(page.getByTestId("sc-remark").first()).toBeVisible();
    await shot(page, `03-remarks-${locale}.png`);
    await go(`/watch-list/${sahara}`);
    await expect(page.getByTestId("wl-no")).toBeVisible();
    await shot(page, `04-watch-entry-${locale}.png`);
    await go("/scorecard-kpis?period=month&anchor=2026-09-15");
    await expect(page.getByTestId("sk-tiles")).toBeVisible({ timeout: 45_000 });
    await shot(page, `05-scorecard-kpis-${locale}.png`);
    await go("/scorecard-settings");
    await expect(page.getByTestId("sp-editor")).toBeVisible();
    await shot(page, `06-scorecard-settings-${locale}.png`);
    await go("/report-packs");
    await expect(page.getByTestId("rp-row").first()).toBeVisible();
    await shot(page, `07-report-packs-${locale}.png`);
    await go(`/report-packs/${mcr}`);
    await expect(page.getByTestId("rp-section").first()).toBeVisible();
    await shot(page, `08-mcr-august-${locale}.png`);
    await go("/distribution-lists?type=MCR");
    await expect(page.getByTestId("dl-editor")).toBeVisible();
    await shot(page, `09-distribution-${locale}.png`);
    await go("/exports?dataset=incidents");
    await expect(page.getByTestId("xp-form")).toBeVisible();
    await shot(page, `10-exports-${locale}.png`);

    // Phone: the contractor rep's own card and the watch list at 390 px.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.context().clearCookies();
    await login(page, TARIQ, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/scorecards/${najd}`);
    await expect(page.getByTestId("sc-score")).toBeVisible();
    await shot(page, `11-scorecard-phone-rep-${locale}.png`, false);
    await go("/watch-list");
    await expect(page.getByTestId("wl-row").first()).toBeVisible();
    await shot(page, `12-watch-list-phone-rep-${locale}.png`, false);
  });
}
