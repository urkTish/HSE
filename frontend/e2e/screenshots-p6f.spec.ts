import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { pinProject } from "./p6a-helpers";

// Phase 6f demo screenshots for docs/screenshots/phase-6f (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6f");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(900_000);

async function shot(page: Page, name: string, fullPage = true) {
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

type Items<T> = { items: T[] };

for (const locale of ["en", "ar"] as const) {
  test(`phase 6f screens (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    const noura = await apiAs(USERS.noura);
    const pid = await projectId(noura, "ANIA-EXP");
    const reqs = await getJson<Items<{ incident_id: string; rule_code: string; pack_id: string | null; body: string }>>(noura, `/api/v1/projects/${pid}/notification-requirements?page_size=100`);
    const incident = reqs.items.find((r) => r.rule_code === "GACA-W")?.incident_id;
    const pack = reqs.items.find((r) => r.pack_id && r.body === "client")?.pack_id;
    const lessons = await getJson<Items<{ id: string; lesson_no: string }>>(noura, "/api/v1/lessons?page_size=50");
    const ll7 = lessons.items.find((l) => l.lesson_no === "LL-2026-007")?.id;
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");

    await go(`/incidents/${incident}`);
    await expect(page.getByTestId("fu-panel")).toBeVisible();
    await page.getByTestId("fu-panel").scrollIntoViewIfNeeded();
    await shot(page, `01-incident-followup-${locale}.png`);
    await go("/followup-overview");
    await expect(page.getByTestId("fu-band")).toBeVisible();
    await shot(page, `02-followup-overview-${locale}.png`);
    await go("/notification-register");
    await expect(page.getByTestId("fu-req").first()).toBeVisible();
    await shot(page, `03-notification-register-${locale}.png`);
    await go(`/notification-packs/${pack}`);
    await expect(page.getByTestId("pack-snapshot")).toBeVisible();
    await shot(page, `04-client-pack-${locale}.png`);
    await go("/followup-kpis?period=month");
    await expect(page.getByTestId("fk-tiles")).toBeVisible({ timeout: 45_000 });
    await shot(page, `05-followup-kpis-${locale}.png`);
    await go("/lessons");
    await expect(page.getByTestId("ll-card").first()).toBeVisible();
    await shot(page, `06-lesson-library-${locale}.png`);
    await go(`/lessons/${ll7}`);
    await expect(page.getByTestId("lesson-distribution")).toBeVisible();
    await shot(page, `07-lesson-${locale}.png`);
    await go("/lesson-acknowledgements");
    await expect(page.getByTestId("dist-items")).toBeVisible();
    await shot(page, `08-acknowledgements-${locale}.png`);
    await go("/effectiveness-checks");
    await expect(page.getByTestId("checks-table")).toBeVisible();
    await shot(page, `09-effectiveness-${locale}.png`);
    await go("/followup-settings");
    await expect(page.getByTestId("fu-rules")).toBeVisible();
    await shot(page, `10-rules-settings-${locale}.png`);

    // Phone: the incident panel and the lesson acknowledgement at 390 px.
    await page.setViewportSize({ width: 390, height: 844 });
    await go(`/incidents/${incident}`);
    await expect(page.getByTestId("fu-panel")).toBeVisible();
    await page.getByTestId("fu-panel").scrollIntoViewIfNeeded();
    await shot(page, `11-incident-followup-phone-${locale}.png`, false);
    await page.context().clearCookies();
    await login(page, USERS.ahmed, locale);
    await pinProject(page, "ANIA-EXP");
    await go("/lesson-acknowledgements");
    await expect(page.getByTestId("dist-item").first()).toBeVisible();
    await page.getByTestId("ack-response-not_applicable").first().click();
    await shot(page, `12-acknowledgement-phone-${locale}.png`, false);
  });
}
