import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { pinProject } from "./p6a-helpers";

// Phase 6f demo screenshots for docs/screenshots/phase-6f (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6f");
// Design pass: SHOT_SUFFIX=before|after runs only the design set and writes docs/screenshots/phase-6f/design/<name>-<locale>-<suffix>.png.
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
  test(`phase 6f screens (${locale})`, async ({ page }) => {
    test.skip(Boolean(SFX), "design set only");
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

async function dshot(page: Page, name: string, locale: string, fullPage = true) {
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(DESIGN, `${name}-${locale}-${SFX}.png`), fullPage });
}

type Req = { id: string; incident_id: string; rule_code: string; pack_id: string | null; body: string };

/** The incident's follow-up panel alone, loaded, in a viewport tall enough that the sticky top bar does not cover it. */
async function panelShot(page: Page, name: string, locale: string, width: number) {
  await page.setViewportSize({ width, height: 3000 });
  const panel = page.getByTestId("fu-panel");
  await expect(panel.getByTestId("fu-req").first()).toBeVisible();
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await page.waitForTimeout(600);
  await panel.screenshot({ path: join(DESIGN, `${name}-${locale}-${SFX}.png`) });
  await page.setViewportSize({ width, height: width < 600 ? 844 : 900 });
}

for (const locale of ["en", "ar"] as const) {
  test(`phase 6f design set (${locale})`, async ({ page }) => {
    test.skip(!SFX, "design set only with SHOT_SUFFIX");
    mkdirSync(DESIGN, { recursive: true });
    const noura = await apiAs(USERS.noura);
    const pid = await projectId(noura, "ANIA-EXP");
    const reqs = await getJson<Items<Req>>(noura, `/api/v1/projects/${pid}/notification-requirements?page_size=100`);
    const gaca = reqs.items.find((r) => r.rule_code === "GACA-W");
    const incident = gaca?.incident_id ?? "";
    const flash = reqs.items.find((r) => r.rule_code === "CL-F")?.pack_id;
    // A draft GACA occurrence pack (Noura prepares it) that Ahmed, a Contractor HSE Rep, opens (PK-6: he approves GOSI packs only).
    let gacaPack = gaca?.pack_id ?? null;
    if (!gacaPack && gaca) {
      const r = await noura.post(`/api/v1/notification-requirements/${gaca.id}/packs`, { data: {} });
      gacaPack = ((await r.json()) as { id: string }).id;
    }
    const lessons = await getJson<Items<{ id: string; lesson_no: string }>>(noura, "/api/v1/lessons?page_size=50");
    const ll7 = lessons.items.find((l) => l.lesson_no === "LL-2026-007")?.id;
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/incidents/${incident}`);
    await panelShot(page, "01-incident-panel", locale, 1280);
    await go("/followup-overview");
    await expect(page.getByTestId("fu-band")).toBeVisible();
    await dshot(page, "02-overview", locale);
    await go("/notification-register");
    await expect(page.getByTestId("fu-req").first()).toBeVisible();
    await dshot(page, "03-register", locale);
    await go(`/notification-packs/${flash}`);
    await expect(page.getByTestId("pack-snapshot")).toBeVisible();
    await dshot(page, "04-client-pack", locale);
    await go("/followup-kpis?period=month");
    await expect(page.getByTestId("fk-tiles")).toBeVisible({ timeout: 45_000 });
    await dshot(page, "05-kpis", locale);
    await go("/lessons");
    await expect(page.getByTestId("ll-card").first()).toBeVisible();
    await dshot(page, "06-library", locale);
    await go(`/lessons/${ll7}`);
    await expect(page.getByTestId("lesson-distribution")).toBeVisible();
    await dshot(page, "07-lesson", locale);
    await go("/lesson-acknowledgements");
    await expect(page.getByTestId("dist-items")).toBeVisible();
    await dshot(page, "08-acks", locale);
    await go("/effectiveness-checks");
    await expect(page.getByTestId("checks-table")).toBeVisible();
    await dshot(page, "09-effectiveness", locale);
    await go("/followup-settings");
    await expect(page.getByTestId("fu-rules")).toBeVisible();
    await dshot(page, "10-settings", locale);

    // Phone: the incident panel and the register at 390 px.
    await page.setViewportSize({ width: 390, height: 844 });
    await go(`/incidents/${incident}`);
    await panelShot(page, "11-incident-panel-phone", locale, 390);
    await go("/notification-register");
    await expect(page.getByTestId("fu-req").first()).toBeVisible();
    await dshot(page, "12-register-phone", locale);

    // Ahmed (Contractor HSE Rep): the incident panel and a draft GACA pack, then his acknowledgements on the phone.
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.context().clearCookies();
    await login(page, USERS.ahmed, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/incidents/${incident}`);
    await panelShot(page, "13-incident-panel-ahmed", locale, 1280);
    await go(`/notification-packs/${gacaPack}`);
    await expect(page.getByTestId("pack-snapshot")).toBeVisible();
    await dshot(page, "14-gaca-pack-ahmed", locale);
    await page.setViewportSize({ width: 390, height: 844 });
    await go("/lesson-acknowledgements");
    await expect(page.getByTestId("dist-item").first()).toBeVisible();
    await dshot(page, "15-acks-phone-ahmed", locale);

    // Sarah (Viewer / Client): the incident panel, no packs or identities.
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.context().clearCookies();
    await login(page, USERS.sarah, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/incidents/${incident}`);
    await panelShot(page, "16-incident-panel-viewer", locale, 1280);
  });
}
