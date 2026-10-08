import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./fixtures/test";
import { trirStream } from "./fixtures/ai-stream";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";

// Phase 1 demo screenshots for docs/screenshots/phase-1 (run with SCREENSHOTS=1).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-1");
const SEP = "period=month&anchor=2026-09-15";
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(240_000);

async function dashboardReady(page: import("@playwright/test").Page) {
  for (const id of ["chart-C1", "chart-C7", "chart-C9"]) await expect(page.getByTestId(id)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("pyramid-layer").first()).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("league-row").first()).toBeVisible({
    timeout: 60_000,
  });
  await page.waitForTimeout(1500);
}

test("phase-1 demo screenshots", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  const api = await apiAs(USERS.noura);
  const ania = await projectId(api, "ANIA-EXP");

  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, USERS.noura);
  await page.goto(`/en?${SEP}`);
  await dashboardReady(page);
  await page.screenshot({
    path: join(OUT, "01-dashboard-en-desktop.png"),
    fullPage: true,
  });

  await page.goto(`/ar?${SEP}`);
  await dashboardReady(page);
  await page.screenshot({
    path: join(OUT, "02-dashboard-ar-desktop.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId("lagging-tiles")).toBeVisible();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(OUT, "03-dashboard-ar-mobile.png") });

  // AI panel: no provider key in demo, so the recorded SSE fixture is replayed (as in p1-ai.spec.ts).
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route("**/api/v1/ai/status**", (r) =>
    r.fulfill({
      json: {
        project_id: ania,
        enabled: true,
        available: true,
        reason_code: null,
        can_ask: true,
        can_generate_report: true,
        questions_used_today: 3,
        questions_limit_per_day: 60,
        reports_used_this_month: 0,
        reports_limit_per_month: 10,
        default_model: "claude-sonnet",
        deep_model: "claude-opus",
        suggested_questions_en: ["What was our TRIR in September 2026?"],
        suggested_questions_ar: ["ما معدل الحالات المسجلة في سبتمبر 2026؟"],
      },
    }),
  );
  await page.route("**/api/v1/ai/ask", (r) =>
    r.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: trirStream(ania),
    }),
  );
  await page.goto(`/en?${SEP}`);
  await page.getByTestId("ai-open").click();
  await page.getByTestId("ai-question").fill("What was our TRIR in September 2026? Call me on +966500000123");
  await page.getByTestId("ai-send").click();
  await expect(page.getByTestId("ai-recommendation").first()).toBeVisible();
  await page.getByTestId("ai-citations").scrollIntoViewIfNeeded();
  await page.getByTestId("ai-turns").evaluate((el) => el.scrollBy(0, 260));
  await page.screenshot({ path: join(OUT, "04-ai-panel-answer.png") });
  await page.unrouteAll();

  const incidents = await getJson<{ items: { id: string; ref: string }[] }>(api, `/api/v1/projects/${ania}/incidents?q=2026-0147&page_size=5`);
  const inc = incidents.items[0] ?? (await getJson<{ items: { id: string }[] }>(api, `/api/v1/projects/${ania}/incidents?page_size=1`)).items[0];
  if (inc) {
    await page.goto(`/en/incidents/${inc.id}`);
    await expect(page.getByTestId("incident-title")).toBeVisible();
    await page.waitForTimeout(800);
    await page.screenshot({
      path: join(OUT, "05-incident-detail.png"),
      fullPage: true,
    });
  }

  await page.goto("/en/workforce/import");
  const csv = [
    "work_date,project_code,site_code,zone_code,contractor_code,shift,headcount,man_hours,no_work,remarks",
    "2026-10-01,ANIA-EXP,S-AIR,,RAWABI,day,40,400,N,",
    "2026-10-01,ANIA-EXP,S-LAND,,NAJD,day,10,200,N,",
    "2026-10-01,ANIA-EXP,S-LAND,,QIMMA,day,10,100,N,",
    "2026-10-01,ANIA-EXP,S-LAND,,SAHARA,all,5,0,Y,",
  ].join("\n");
  await page.getByTestId("import-file").setInputFiles({
    name: "returns-oct.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await page.getByTestId("import-check").click();
  await expect(page.getByTestId("import-report")).toBeVisible();
  await page.screenshot({
    path: join(OUT, "06-import-dry-run.png"),
    fullPage: true,
  });

  const cas = await getJson<{ items: { id: string }[] }>(api, `/api/v1/projects/${ania}/corrective-actions?page_size=1`);
  if (cas.items[0]) {
    await page.goto(`/en/actions/${cas.items[0].id}`);
    await expect(page.getByTestId("ca-ref")).toBeVisible();
    await page.waitForTimeout(800);
    await page.screenshot({
      path: join(OUT, "07-ca-detail.png"),
      fullPage: true,
    });
  }

  const reports = await getJson<{ items: { id: string }[] }>(api, `/api/v1/projects/${ania}/monthly-reports`);
  await page.goto(reports.items[0] ? `/en/reports/${reports.items[0].id}` : "/en/reports");
  await page.waitForTimeout(1500);
  await page.screenshot({
    path: join(OUT, "08-monthly-report.png"),
    fullPage: true,
  });
});
