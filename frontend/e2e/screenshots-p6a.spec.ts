import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, uid, USERS } from "./helpers";
import { deploymentOf } from "./p5-helpers";
import { pinProject, USERS6 } from "./p6a-helpers";

// Phase 6a demo screenshots for docs/screenshots/phase-6a (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6a");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(600_000);

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

const IMPORT_HEAD = "worker_no,id_type,id_number,passport_country,project_code,provider_code,examiner_no,assessment_type,examined_on,certificate_no,code,outcome,restrictions,restriction_review_date,unfit_review_date,printed_next_due";

for (const locale of ["en", "ar"] as const) {
  test(`Phase 6a screenshots (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    const api = await apiAs(USERS.faisal);
    const pid = await projectId(api, "ANIA-EXP");
    const sunil = await deploymentOf("ANIA-EXP", "WKR-000034");
    const huda = await apiAs(USERS6.huda);
    const fa = await getJson<{ items: { id: string }[] }>(huda, `/api/v1/projects/${pid}/fitness-assessments?q=WKR-000009&page_size=5`);
    const providers = await getJson<{ items: { id: string; provider_code: string }[] }>(huda, "/api/v1/medical-providers?page_size=50");
    const salama = providers.items.find((p) => p.provider_code === "SALAMA");
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS6.huda, locale);
    await pinProject(page, "ANIA-EXP");

    await go(`/worker-health/${sunil.worker_id}?dep=${sunil.id}`);
    await expect(page.getByTestId("req-row").first()).toBeVisible();
    await shot(page, `01-worker-health-${locale}.png`, true);

    await go("/fitness-gaps");
    await expect(page.getByTestId("gap-row").first()).toBeVisible();
    await shot(page, `02-fitness-gaps-${locale}.png`);

    await go("/medical-plan?as_of=2026-09-30");
    await expect(page.getByTestId("plan-line").first()).toBeVisible();
    await shot(page, `03-medical-plan-${locale}.png`);

    await go("/fitness-assessments");
    await expect(page.getByTestId("assessment-row").first()).toBeVisible();
    await shot(page, `04-fitness-assessments-${locale}.png`);

    if (fa.items[0]) {
      await go(`/fitness-assessments/${fa.items[0].id}`);
      await expect(page.getByTestId("fa-lines-view")).toBeVisible();
      await shot(page, `05-assessment-detail-${locale}.png`, true);
    }

    await go("/fitness-assessments/new?worker_no=WKR-000034&type=referral");
    await expect(page.getByTestId("fa-worker-found")).toBeVisible();
    await shot(page, `06-new-assessment-${locale}.png`, true);

    await go("/fitness-holds");
    await expect(page.getByTestId("hold-row").first()).toBeVisible();
    await shot(page, `07-fitness-holds-${locale}.png`);

    await go("/fitness-referrals");
    await expect(page.getByTestId("referral-row").first()).toBeVisible();
    await shot(page, `08-fitness-referrals-${locale}.png`);

    await go("/fitness-codes");
    await expect(page.getByTestId("fitness-code-row").first()).toBeVisible();
    await shot(page, `09-fitness-codes-${locale}.png`);

    await go("/medical-providers");
    await expect(page.getByTestId("med-provider-row").first()).toBeVisible();
    await shot(page, `10-medical-providers-${locale}.png`);

    if (salama) {
      await go(`/medical-providers/${salama.id}`);
      await expect(page.getByText("EXR-0003")).toBeVisible();
      await shot(page, `11-medical-provider-detail-${locale}.png`, true);
    }

    await go("/medical-examiners");
    await expect(page.getByTestId("examiner-row").first()).toBeVisible();
    await shot(page, `12-medical-examiners-${locale}.png`);

    const sfx = uid();
    const rows = [`WKR-000004,,,,ANIA-EXP,SHIFA-ANIA,EXR-0001,periodic,2026-10-01,SH-TEST-DEMO-${sfx},GEN-FIT,fit,,,,`, `WKR-999999,,,,ANIA-EXP,SHIFA-ANIA,EXR-0001,periodic,2026-10-01,SH-TEST-DEMO-${sfx}-2,GEN-FIT,fit,,,,`];
    await go("/medical-imports");
    await page.getByTestId("mi-source").selectOption("clinic_register_file");
    const prov = page.getByTestId("mi-provider");
    await prov.selectOption((await prov.locator("option", { hasText: "SHIFA-ANIA" }).first().getAttribute("value")) ?? "");
    await page.getByTestId("mi-file").setInputFiles({ name: `shifa-register-${sfx}.csv`, mimeType: "text/csv", buffer: Buffer.from(`${IMPORT_HEAD}\r\n${rows.join("\r\n")}\r\n`, "utf8") });
    await page.getByTestId("mi-check").click();
    await expect(page.getByTestId("mi-rows")).toBeVisible();
    await shot(page, `13-medical-import-dry-run-${locale}.png`);
    await page.getByTestId("mi-discard").click();
    await expect(page).toHaveURL(/\/medical-imports$/);

    // Phone (390 px): the worker's fitness state and the holds list as cards, for field use.
    await page.setViewportSize({ width: 390, height: 844 });
    await go(`/worker-health/${sunil.worker_id}?dep=${sunil.id}`);
    await expect(page.getByTestId("req-row").first()).toBeVisible();
    await shot(page, `16-worker-health-phone-${locale}.png`, true);
    await go("/fitness-holds");
    await expect(page.getByTestId("hold-row").first()).toBeVisible();
    await shot(page, `17-fitness-holds-phone-${locale}.png`);
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.context().clearCookies();
    await login(page, USERS.faisal, locale);
    await pinProject(page, "ANIA-EXP");
    await go("/medical-settings");
    await expect(page.getByTestId("medical-settings")).toBeVisible();
    await shot(page, `14-medical-settings-${locale}.png`, true);

    await go("/occupational-health?as_of=2026-09-30");
    await expect(page.getByTestId("oh-tile")).toHaveCount(8, { timeout: 30_000 });
    await shot(page, `15-occupational-health-kpi-${locale}.png`, true);
  });
}
