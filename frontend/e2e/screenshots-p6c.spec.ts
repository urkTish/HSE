import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, sql, userId, USERS } from "./helpers";
import { accessCard } from "./p2-helpers";
import { pinProject } from "./p6a-helpers";

// Phase 6c demo screenshots for docs/screenshots/phase-6c (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6c");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(900_000);

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

/**
 * Eight S-AIR workers on site now: copies of their latest seeded entry-gate rows, moved to 30 min ago, so the
 * roll muster below has an expected list (the seed's S-AIR gate log ends on 30 Sept). Screenshot setup only.
 */
function workersOnSite(): string[] {
  const at = new Date(Date.now() - 30 * 60_000).toISOString();
  const out = sql(
    "CREATE TEMP TABLE t AS SELECT DISTINCT ON (gc.deployment_id) gc.* FROM gate_checks gc JOIN gates g ON g.id = gc.gate_id " +
      "JOIN sites s ON s.id = g.site_id JOIN worker_deployments d ON d.id = gc.deployment_id WHERE s.code = 'S-AIR' AND gc.final " +
      "AND gc.direction = 'in' AND gc.result = 'GRANTED_WITH_WARNING' AND d.status = 'mobilised' ORDER BY gc.deployment_id, gc.occurred_at DESC LIMIT 8; " +
      `UPDATE t SET id = gen_random_uuid(), occurred_at = '${at}', local_date = '${at.slice(0, 10)}', pairing_id = NULL; ` +
      "INSERT INTO gate_checks SELECT * FROM t RETURNING deployment_id;",
  );
  return out.split("\n").filter((l) => /^[0-9a-f-]{36}$/.test(l.trim()));
}

/** An open roll muster at S-AIR: eight expected, five scanned, three missing (planned by Noura, started by Omar). */
let openMuster = "";
async function ensureOpenMuster(): Promise<string> {
  if (openMuster) return openMuster;
  const onSite = workersOnSite();
  const noura = await apiAs(USERS.noura);
  const pid = await projectId(noura, "ANIA-EXP");
  const sites = await getJson<{ items: { id: string; code: string }[] }>(noura, `/api/v1/projects/${pid}/sites?page_size=50`);
  const res = await noura.post(`/api/v1/projects/${pid}/drills`, {
    data: {
      drill_type: "evacuation_full",
      scenario_code: "SC-FIRE",
      site_id: sites.items.find((s) => s.code === "S-AIR")?.id,
      zone_ids: [],
      planned_at: "2026-10-06T07:30:00Z",
      shift: "day",
      announced: true,
      suspend_permits: false,
      conductor_user_id: await userId(noura, USERS.omar),
      evaluator_user_ids: [await userId(noura, USERS.noura)],
      plan_note: "AOCC coordination ref AOCC-LOG-TEST-402.",
    },
  });
  const drill = (await res.json()) as { id: string };
  const omar = await apiAs(USERS.omar);
  const started = (await (await omar.post(`/api/v1/drills/${drill.id}/transitions`, { data: { action: "start" } })).json()) as { muster_id: string };
  for (const id of onSite.slice(0, 5)) {
    const card = await accessCard(noura, id);
    await omar.post(`/api/v1/musters/${started.muster_id}/scan`, { data: { payload: card.qr_payload } });
  }
  openMuster = started.muster_id;
  return openMuster;
}

for (const locale of ["en", "ar"] as const) {
  test(`Phase 6c screenshots (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const erps = await getJson<{ items: { id: string; erp_no: string }[] }>(api, `/api/v1/projects/${pid}/erps`);
    const drills = await getJson<{ items: { id: string; drill_no: string; muster_id: string | null }[] }>(api, `/api/v1/projects/${pid}/drills?page_size=100`);
    const events = await getJson<{ items: { id: string; event_no: string }[] }>(api, `/api/v1/projects/${pid}/emergency-events?page_size=50`);
    const erp = erps.items.find((e) => e.erp_no === "ERP-ANIA-EXP-r3");
    const drill = drills.items.find((d) => d.drill_no === "DRL-ANIA-EXP-2026-031");
    const event = events.items.find((e) => e.event_no === "EMV-ANIA-EXP-2026-004");
    const muster = await ensureOpenMuster();
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");

    await go("/emergency-board");
    await expect(page.getByTestId("board-site").first()).toBeVisible();
    await shot(page, `01-emergency-board-${locale}.png`, true);

    await go("/emergency-actions");
    await expect(page.getByTestId("em-action").first()).toBeVisible();
    await shot(page, `02-emergency-actions-${locale}.png`, true);

    await go("/emergency-kpis?period=month&anchor=2026-09-15");
    await expect(page.getByTestId("em-tiles")).toBeVisible({ timeout: 45_000 });
    await shot(page, `03-emergency-kpis-${locale}.png`, true);

    await go("/emergency-plans");
    await expect(page.getByTestId("erp-row").first()).toBeVisible();
    await shot(page, `04-emergency-plans-${locale}.png`);

    if (erp) {
      await go(`/emergency-plans/${erp.id}`);
      await expect(page.getByTestId("scenario-row").first()).toBeVisible();
      await shot(page, `05-emergency-plan-${locale}.png`, true);
    }

    await go("/assembly-points");
    await expect(page.getByTestId("ap-row").first()).toBeVisible();
    await shot(page, `06-assembly-points-${locale}.png`);

    await go("/emergency-contacts");
    await expect(page.getByTestId("contact-row").first()).toBeVisible();
    await shot(page, `07-emergency-contacts-${locale}.png`, true);

    await go("/emergency-zone-profiles");
    await expect(page.getByTestId("profile-row").first()).toBeVisible();
    await shot(page, `08-zone-profiles-${locale}.png`);

    await go("/muster-devices");
    await expect(page.getByTestId("md-register")).toBeVisible();
    await shot(page, `09-muster-devices-${locale}.png`);

    await go("/emergency-info");
    await page.locator("button#ei-zones").click();
    await page.getByRole("listbox").getByRole("option", { name: /Z-PIERB/ }).first().getByRole("button").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("ei-numbers")).toBeVisible();
    await shot(page, `10-emergency-info-${locale}.png`, true);

    await go("/emergency-settings");
    await expect(page.getByTestId("settings-readonly")).toBeVisible();
    await shot(page, `11-emergency-settings-${locale}.png`, true);

    await go("/emergency-roster");
    await expect(page.getByTestId("roster-row").first()).toBeVisible();
    await shot(page, `12-emergency-roster-${locale}.png`);

    await go("/emergency-coverage?from=2026-09-14&to=2026-09-14");
    await expect(page.getByTestId("coverage-row").first()).toBeVisible();
    await shot(page, `13-emergency-coverage-${locale}.png`, true);

    await go("/rescue-teams");
    await expect(page.getByTestId("team-card").first()).toBeVisible();
    await shot(page, `14-rescue-teams-${locale}.png`, true);

    await go("/emergency-assets");
    await expect(page.getByTestId("asset-row").first()).toBeVisible();
    await shot(page, `15-emergency-assets-${locale}.png`);

    await go("/emergency-asset-checks");
    await expect(page.getByTestId("check-row").first()).toBeVisible();
    await shot(page, `16-asset-checks-${locale}.png`);

    await go("/emergency-assets?type=aed");
    await page.getByTestId("asset-check").first().click();
    await expect(page.getByTestId("ce-item").first()).toBeVisible();
    await shot(page, `17-asset-check-entry-${locale}.png`, true);

    await go("/drill-programme");
    await expect(page.getByTestId("line-row").first()).toBeVisible();
    await shot(page, `18-drill-programme-${locale}.png`, true);

    await go("/drills");
    await expect(page.getByTestId("drill-row").first()).toBeVisible();
    await shot(page, `19-drills-${locale}.png`);

    if (drill) {
      await go(`/drills/${drill.id}`);
      await expect(page.getByTestId("eval-view")).toBeVisible();
      await shot(page, `20-drill-evaluated-${locale}.png`, true);
      if (drill.muster_id) {
        await go(`/musters/${drill.muster_id}`);
        await expect(page.getByTestId("muster-counters")).toBeVisible();
        await shot(page, `21-muster-counts-${locale}.png`, true);
      }
    }

    await go(`/musters/${muster}`);
    await expect(page.getByTestId("muster-scan")).toBeVisible();
    await shot(page, `22-muster-roll-${locale}.png`, true);

    // The printable muster sheet (MU-9), shown as it prints (A4 media); each fetch is an audited export.
    await go(`/musters/${muster}/sheet`);
    await expect(page.getByTestId("sheet-row").first()).toBeVisible();
    await page.emulateMedia({ media: "print" });
    await page.setViewportSize({ width: 794, height: 1123 });
    await shot(page, `28-muster-sheet-${locale}.png`, true);
    await page.emulateMedia({ media: "screen" });
    await page.setViewportSize({ width: 1440, height: 900 });

    await go("/emergency-events");
    await expect(page.getByTestId("event-row").first()).toBeVisible();
    await shot(page, `23-emergency-events-${locale}.png`);

    if (event) {
      await go(`/emergency-events/${event.id}`);
      await expect(page.getByTestId("event-review")).toBeVisible();
      await shot(page, `24-emergency-event-${locale}.png`, true);
    }

    await go("/emergency-events?declare=1");
    await expect(page.getByTestId("declare-confirm")).toBeVisible();
    await shot(page, `25-declare-emergency-${locale}.png`);

    // Phone (390 px): the board and the muster.
    await page.setViewportSize({ width: 390, height: 844 });
    await go("/emergency-board");
    await expect(page.getByTestId("board-site").first()).toBeVisible();
    await shot(page, `26-emergency-board-phone-${locale}.png`, true);
    await go(`/musters/${muster}`);
    await expect(page.getByTestId("muster-scan")).toBeVisible();
    await shot(page, `27-muster-phone-${locale}.png`, true);
  });
}
