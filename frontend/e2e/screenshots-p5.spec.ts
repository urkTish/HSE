import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, login, uid, USERS } from "./helpers";
import { recordOf, sessionId, USERS5 } from "./p5-helpers";

// Phase 5 demo screenshots for docs/screenshots/phase-5 (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-5");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(300_000);

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

test("Phase 5 screenshots", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  const api = await apiAs(USERS.faisal);
  await page.setViewportSize({ width: 1440, height: 900 });

  await login(page, USERS.noura);
  await page.goto("/en/training-matrix?as_of=2026-09-30");
  await expect(page.locator('[data-testid="matrix-line"]').first()).toBeVisible();
  await shot(page, "01-training-matrix.png");

  await page.goto("/en/training-gaps");
  await expect(page.getByTestId("gaps-table")).toBeVisible();
  await shot(page, "02-training-gaps.png");

  await page.goto("/en/refresher-plan");
  await expect(page.getByTestId("plan-table")).toBeVisible();
  await shot(page, "05-refresher-plan.png");

  const rec = await recordOf(api, "ANIA-EXP", "WKR-000001", "WAH");
  await page.goto(`/en/training-records/${rec.id}`);
  await expect(page.getByTestId("tr-certificate")).toBeVisible();
  await shot(page, "04-record-tr-certificate.png");

  const sfx = uid();
  const csv = [
    "worker_no,id_type,id_number,passport_country,course_code,provider_code,certificate_no,completed_on,printed_expiry,theory_score_pct,practical_result,hours,project_sponsored,name_as_printed,id_on_card",
    `,iqama,2000001017,,FIRST-AID,HAYAT,HY-FA-DEMO-${sfx},2026-09-10,,85,pass,,N,Biju Thomas,same_as_lookup`,
    `WKR-999999,,,,FIRST-AID,HAYAT,HY-FA-DEMO-${sfx}-2,2026-09-10,,85,pass,,N,Unknown Worker,`,
    `WKR-000021,,,,FIRST-AID,HAYAT,HY-FA-TEST-24-1116,2024-11-16,,85,pass,,N,Rafiq Islam,`,
  ].join("\r\n");
  await page.goto("/en/training-imports");
  await page.getByTestId("ti-file").setInputFiles({ name: `first-aid-cards-${sfx}.csv`, mimeType: "text/csv", buffer: Buffer.from(`${csv}\r\n`, "utf8") });
  await page.getByTestId("ti-check").click();
  await expect(page.getByTestId("ti-rows")).toBeVisible();
  await shot(page, "07-import-dry-run.png");
  await page.getByTestId("ti-discard").click();

  await login(page, USERS.faisal);
  await page.goto("/en/hook-policy?kind=training_course");
  await expect(page.getByTestId("hook-kind-training_course")).toBeVisible();
  await expect(page.getByTestId("hook-readiness")).toBeVisible();
  await shot(page, "06-hook-policy-training.png");

  await page.goto("/en");
  const band = page.getByTestId("training-band");
  await expect(band).toBeVisible();
  await band.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await page.screenshot({ path: join(OUT, "08-dashboard-training-band.png") });

  const sid = await sessionId(api, "RBT-52", "TRS-RBT-52-2026-00022");
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, USERS5.lina, "ar");
  await page.goto(`/ar/training-sessions/${sid}`);
  await expect(page.getByTestId("attendance-register")).toBeVisible();
  await page.getByTestId("attendance-register").scrollIntoViewIfNeeded();
  await shot(page, "03-session-attendance-phone-ar.png");
});
