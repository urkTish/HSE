import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { pinProject } from "./p6a-helpers";

// Phase 6g demo screenshots for docs/screenshots/phase-6g (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6g");
const TARIQ = "tariq.mutairi@example.com";
// Design pass: SHOT_SUFFIX=before|after runs only the design set and writes docs/screenshots/phase-6g/design/<name>-<locale>-<suffix>.png.
const SFX = process.env.SHOT_SUFFIX ?? "";
const DESIGN = join(OUT, "design");
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
    test.skip(Boolean(SFX), "design set only");
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

async function dshot(page: Page, name: string, locale: string, fullPage = true) {
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(DESIGN, `${name}-${locale}-${SFX}.png`), fullPage });
}

type Pack = { id: string; doc_no: string; revision: number; report_type: string; status: string };

for (const locale of ["en", "ar"] as const) {
  test(`phase 6g design set (${locale})`, async ({ page }) => {
    test.skip(!SFX, "design set only with SHOT_SUFFIX");
    mkdirSync(DESIGN, { recursive: true });
    const faisal = await apiAs(USERS.faisal);
    const pid = await projectId(faisal, "ANIA-EXP");
    const cards = await getJson<Items<{ id: string; engagement_code: string; scope: string }>>(faisal, `/api/v1/projects/${pid}/scorecards?month=2026-09&page_size=50`);
    const najd = cards.items.find((c) => c.engagement_code === "NAJD" && c.scope === "own")?.id;
    const watch = await getJson<Items<{ id: string; entry_no: string }>>(faisal, `/api/v1/projects/${pid}/watch-list?page_size=50`);
    const sahara = watch.items.find((w) => w.entry_no.endsWith("-002"))?.id;
    const packs = await getJson<Items<Pack>>(faisal, `/api/v1/projects/${pid}/report-packs?page_size=50`);
    const mcr = (m: string, rev: number) => packs.items.find((p) => p.report_type === "MCR" && p.doc_no.endsWith(m) && p.revision === rev)?.id;
    const engs = await getJson<Items<{ contractor: { id: string; short_code: string } }>>(faisal, `/api/v1/projects/${pid}/engagements?page_size=50`);
    const najdContractor = engs.items.find((e) => e.contractor.short_code === "NAJD")?.contractor.id;
    // One finished export so the job log has a row.
    await faisal.post("/api/v1/exports", { data: { dataset: "heat_patrols", format: "csv", project_id: pid, columns: [] } });
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.faisal, locale);
    await pinProject(page, "ANIA-EXP");
    await go("/scorecards?month=2026-09");
    await expect(page.getByTestId("sc-rank-row").first()).toBeVisible();
    await dshot(page, "01-register", locale);
    await go(`/scorecards/${najd}`);
    await expect(page.getByTestId("sc-pillar").first()).toBeVisible();
    await dshot(page, "02-card-najd", locale);
    await go("/scorecard-remarks");
    await expect(page.getByTestId("sc-remark").first()).toBeVisible();
    await dshot(page, "03-remarks", locale);
    await go(`/watch-list/${sahara}`);
    await expect(page.getByTestId("wl-no")).toBeVisible();
    await dshot(page, "04-watch-entry", locale);
    await go("/scorecard-kpis?period=month&anchor=2026-09-15");
    await expect(page.getByTestId("sk-tiles")).toBeVisible({ timeout: 45_000 });
    await dshot(page, "05-kpis", locale);
    await go("/scorecard-settings");
    await expect(page.getByTestId("sp-editor")).toBeVisible();
    await dshot(page, "06-settings", locale);
    await go("/report-packs");
    await expect(page.getByTestId("rp-row").first()).toBeVisible();
    await dshot(page, "07-packs", locale);
    await go(`/report-packs/${mcr("2026-07", 0)}`);
    await expect(page.getByTestId("rp-section").first()).toBeVisible();
    await dshot(page, "08-mcr-july-provisional", locale);
    await go(`/report-packs/${mcr("2026-09", 0)}`);
    await expect(page.getByTestId("rp-status")).toBeVisible();
    await dshot(page, "09-mcr-september-draft", locale);
    await go(`/report-packs/${mcr("2026-08", 1)}`);
    await expect(page.getByTestId("rp-section").first()).toBeVisible();
    await dshot(page, "10-mcr-august-issued", locale);
    await go("/distribution-lists?type=MCR");
    await expect(page.getByTestId("dl-editor")).toBeVisible();
    await dshot(page, "11-distribution", locale);
    await go("/exports?dataset=incidents");
    await expect(page.getByTestId("xp-form")).toBeVisible();
    await expect(page.getByTestId("xp-job").first()).toBeVisible();
    await dshot(page, "12-exports", locale);
    await go(`/contractors/${najdContractor}/performance`);
    await expect(page.getByTestId("cps-mean")).toBeVisible();
    await dshot(page, "13-performance", locale);
    await go("/ban-patrols");
    await expect(page.getByTestId("registry-export")).toBeVisible();
    await dshot(page, "14-register-export", locale, false);
    await go("");
    await expect(page.getByTestId("dashboard-print")).toBeVisible({ timeout: 45_000 });
    await dshot(page, "15-dashboard-print", locale, false);

    // Phone, HSE Manager: the register and a draft pack at 390 px.
    await page.setViewportSize({ width: 390, height: 844 });
    await go("/scorecards?month=2026-09");
    await expect(page.getByTestId("sc-rank-row").first()).toBeVisible();
    await dshot(page, "16-register-phone", locale);
    await go(`/report-packs/${mcr("2026-09", 0)}`);
    await expect(page.getByTestId("rp-status")).toBeVisible();
    await dshot(page, "17-draft-pack-phone", locale);
    await go("/ban-patrols");
    await expect(page.getByTestId("registry-export")).toBeVisible();
    await dshot(page, "18-register-export-phone", locale, false);

    // Tariq (Contractor HSE Rep, NAJD): his own card, register, remarks and watch list; never another contractor's name.
    await page.context().clearCookies();
    await login(page, TARIQ, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/scorecards/${najd}`);
    await expect(page.getByTestId("sc-score")).toBeVisible();
    await dshot(page, "19-card-phone-rep", locale);
    await go("/scorecards?month=2026-09");
    await expect(page.getByTestId("sc-card-list").or(page.getByTestId("sc-ranking")).first()).toBeVisible();
    await dshot(page, "20-register-phone-rep", locale);
    await go("/scorecard-remarks");
    await expect(page.getByTestId("sc-remark").first()).toBeVisible();
    await dshot(page, "21-remarks-phone-rep", locale);
    await go("/watch-list");
    await expect(page.getByTestId("wl-row").first()).toBeVisible();
    await dshot(page, "22-watch-phone-rep", locale);
    await page.setViewportSize({ width: 1280, height: 900 });
    await go("/scorecards?month=2026-09");
    await expect(page.getByTestId("sc-card-list").or(page.getByTestId("sc-ranking")).first()).toBeVisible();
    await dshot(page, "23-register-rep", locale);
  });
}
