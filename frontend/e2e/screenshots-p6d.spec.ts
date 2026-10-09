import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, selectByPrefix, USERS } from "./helpers";
import { accessCard, pickMulti } from "./p2-helpers";
import { pinProject } from "./p6a-helpers";

// Phase 6d demo screenshots for docs/screenshots/phase-6d (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6d");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(900_000);

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

type Items<T> = { items: T[] };

for (const locale of ["en", "ar"] as const) {
  test(`phase 6d screens (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    const noura = await apiAs(USERS.noura);
    const pid = await projectId(noura, "ANIA-EXP");
    const stops = await getJson<Items<{ id: string; order_no: string }>>(noura, `/api/v1/projects/${pid}/stop-work-orders?page_size=50`);
    const stop = stops.items.find((o) => o.order_no === "SWO-ANIA-EXP-2026-007") ?? stops.items[0];
    const audits = await getJson<Items<{ id: string; audit_no: string; status: string }>>(noura, `/api/v1/projects/${pid}/field-audits?page_size=50`);
    const audit = audits.items.find((a) => a.audit_no === "AUD-ANIA-EXP-2026-012") ?? audits.items.find((a) => a.status === "issued");
    const talks = await getJson<Items<{ id: string; talk_no: string }>>(noura, `/api/v1/projects/${pid}/toolbox-talks?topic_code=TT-014&page_size=50`);
    const talk = talks.items.find((x) => x.talk_no === "TBT-ANIA-EXP-2026-04412") ?? talks.items[0];
    const tpls = await getJson<Items<{ id: string }>>(noura, "/api/v1/checklist-templates?template_code=GSI&status=published");
    const topics = await getJson<Items<{ id: string; topic_code: string }>>(noura, "/api/v1/toolbox-topics?status=published&page_size=100");
    const topic = topics.items.find((x) => x.topic_code === "TT-014");
    const campaigns = await getJson<Items<{ id: string }>>(noura, `/api/v1/projects/${pid}/briefing-campaigns?page_size=20`);
    const deps = await getJson<Items<{ id: string; worker_no: string; engagement: { short_code: string } | null; sites: { code: string }[] }>>(
      noura,
      `/api/v1/projects/${pid}/deployments?status=mobilised&page_size=200`,
    );
    const najd = deps.items.filter((d) => d.engagement?.short_code === "NAJD" && d.sites.some((s) => s.code === "S-LAND"));
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");

    await go("/field-overview");
    await expect(page.getByTestId("field-band")).toBeVisible();
    await shot(page, `01-field-overview-${locale}.png`, true);

    await go("/field-kpis?period=month&anchor=2026-09-15");
    await expect(page.getByTestId("fk-tiles")).toBeVisible({ timeout: 45_000 });
    await shot(page, `02-field-kpis-${locale}.png`, true);

    await go("/field-settings");
    await expect(page.getByTestId("fd-settings")).toBeVisible();
    await shot(page, `03-field-settings-${locale}.png`, true);

    await go("/checklist-templates");
    await expect(page.getByTestId("tpl-row").first()).toBeVisible();
    await shot(page, `04-checklist-templates-${locale}.png`);

    if (tpls.items[0]) {
      await go(`/checklist-templates/${tpls.items[0].id}`);
      await expect(page.getByTestId("tpl-item").first()).toBeVisible();
      await shot(page, `05-checklist-template-${locale}.png`, true);
    }

    await go("/toolbox-topics");
    await expect(page.getByTestId("topic-row").first()).toBeVisible();
    await shot(page, `06-toolbox-topics-${locale}.png`);

    if (topic) {
      await go(`/toolbox-topics/${topic.id}`);
      await expect(page.getByTestId("kp-en")).toBeVisible();
      await shot(page, `07-toolbox-topic-${locale}.png`, true);
    }

    await go("/field-findings");
    await expect(page.getByTestId("fd-finding").first()).toBeVisible();
    await shot(page, `08-field-findings-${locale}.png`);

    await go("/stop-work-orders");
    await expect(page.getByTestId("stop-row").first()).toBeVisible();
    await shot(page, `09-stop-work-orders-${locale}.png`);

    if (stop) {
      await go(`/stop-work-orders/${stop.id}`);
      await expect(page.getByTestId("stop-detail")).toBeVisible();
      await shot(page, `10-stop-work-order-${locale}.png`, true);
    }

    await go("/field-audits");
    await expect(page.getByTestId("audit-row").first()).toBeVisible();
    await shot(page, `11-field-audits-${locale}.png`);

    if (audit) {
      await go(`/field-audits/${audit.id}`);
      await expect(page.getByTestId("audit-detail")).toBeVisible();
      await shot(page, `12-field-audit-${locale}.png`, true);
    }

    await go("/audit-programme");
    await expect(page.getByTestId("programme-line").first()).toBeVisible();
    await shot(page, `13-audit-programme-${locale}.png`, true);

    await go("/toolbox-talks");
    await expect(page.getByTestId("talk-row").first()).toBeVisible();
    await shot(page, `14-toolbox-talks-${locale}.png`);

    if (talk) {
      await go(`/toolbox-talks/${talk.id}`);
      await expect(page.getByTestId("talk-detail")).toBeVisible();
      await shot(page, `15-toolbox-talk-${locale}.png`, true);
    }

    await go("/briefing-campaigns");
    await expect(page.getByTestId("campaigns-table").or(page.getByTestId("campaign-new"))).toBeVisible();
    await shot(page, `16-briefing-campaigns-${locale}.png`);

    if (campaigns.items[0]) {
      await go(`/briefing-campaigns/${campaigns.items[0].id}`);
      await expect(page.getByTestId("campaign-detail")).toBeVisible();
      await shot(page, `17-briefing-campaign-${locale}.png`, true);
    }

    await go("/inspection-plans/new");
    await page.locator("#inspection_type").selectOption("general_site");
    await expect(page.getByTestId("plan-template").locator("option", { hasText: "GSI" })).toHaveCount(1);
    await shot(page, `18-plan-template-${locale}.png`, true);

    // Phone (390 px): checklist execution and toolbox attendance.
    await page.setViewportSize({ width: 390, height: 844 });
    await go("/field-inspections/new");
    await expect(page.getByTestId("run-unplanned")).toBeVisible();
    await shot(page, `19-checklist-start-phone-${locale}.png`, true);
    await selectByPrefix(page.getByTestId("run-template-select"), "GSI");
    await selectByPrefix(page.getByTestId("run-site"), "S-LAND");
    await selectByPrefix(page.getByTestId("run-zone"), "Z-PIERB");
    await selectByPrefix(page.getByTestId("run-eng"), "NAJD");
    await page.getByTestId("run-start").click();
    await expect(page.getByTestId("run-item").first()).toBeVisible();
    for (const c of ["GSI-01", "GSI-02", "GSI-03", "GSI-04"]) await page.getByTestId(`ans-${c}-compliant`).click();
    await page.getByTestId("ans-GSI-05-non_compliant").click();
    await page.getByTestId("note-GSI-05").fill("Open slab edge at grid C-14, no barrier");
    await page.getByTestId("sw-activity").fill("Formwork at level 3 slab edge");
    await shot(page, `20-checklist-run-phone-${locale}.png`, true);

    await go("/toolbox-talks/new");
    await expect(page.getByTestId("offline-pack")).toHaveAttribute("data-cached", "yes", { timeout: 30_000 });
    await selectByPrefix(page.getByTestId("tf-site"), "S-LAND");
    await selectByPrefix(page.getByTestId("tf-host"), "NAJD");
    await pickMulti(page, "tf-topics", [/TT-014/]);
    if (najd[0]) {
      const card = await accessCard(await apiAs(USERS.faisal), najd[0].id);
      await page.getByTestId("att-payload").fill(card.qr_payload);
      await page.getByTestId("att-payload-go").click();
    }
    if (najd[1]) {
      await page.getByTestId("att-search").fill(najd[1].worker_no);
      await page.locator(`[data-testid="att-match"][data-worker="${najd[1].worker_no}"]`).click();
    }
    await expect(page.getByTestId("att-row").first()).toBeVisible();
    await shot(page, `21-toolbox-attendance-phone-${locale}.png`, true);

    await go("/field-overview");
    await expect(page.getByTestId("field-band")).toBeVisible();
    await shot(page, `22-field-overview-phone-${locale}.png`, true);
  });
}
