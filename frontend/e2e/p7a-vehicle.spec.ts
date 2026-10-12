import type { APIRequestContext, Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, uid, USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

// 7a vehicle accident details (spec 7a-vehicle-accident-details v1.1). Seed: Appendix A (D-239), found by title.
const SEP = "period=month&anchor=2026-09-15";
const T0201 = "Pickup struck a private car on Airport Road (km 12)";
const T0204 = "Tipper reversing near miss on the site haul road";
const T0212 = "Commuting crash in a worker's own car (single vehicle)";
const T0215 = "Crew bus struck by a private car on the camp road";
const T0231 = "Minor collision with a private car on a public road, no injury";

type Item = { id: string; ref: string; title: string; recorded_not_counted: boolean; plates?: string[]; report_no?: string | null };
type Report = { files: { id: string; superseded: boolean }[] };

function pdf(label: string): Buffer {
  return Buffer.from(`%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n% ${label}\ntrailer << /Root 1 0 R >>\n%%EOF\n`);
}

async function vehicleIncidents(api: APIRequestContext): Promise<Map<string, Item>> {
  const pid = await projectId(api, "ANIA-EXP");
  const page = await getJson<{ items: Item[] }>(api, `/api/v1/projects/${pid}/incidents?vehicle_involved=true&page_size=200`);
  return new Map(page.items.map((x) => [x.title, x]));
}

async function idOf(title: string): Promise<string> {
  const api = await apiAs(USERS.noura);
  const id = (await vehicleIncidents(api)).get(title)?.id;
  expect(id, title).toBeTruthy();
  return id as string;
}

async function rowCount(page: Page): Promise<number> {
  return page.getByTestId("incident-row").count();
}

test.describe("7a vehicle accident details", () => {
  test("AC17: the register finds commuting crashes with the 'Recorded, not counted' filter and badge; plate and report no. columns", async ({ page }) => {
    await openAs(page, USERS.noura, "/incidents?vehicle_involved=true");
    const rows = page.getByTestId("incident-row");
    await expect(rows.first()).toBeVisible();
    expect(await rowCount(page)).toBeGreaterThanOrEqual(6);
    await expect(rows.and(page.locator("[data-vehicle=false]"))).toHaveCount(0);
    // Own / contractor plates and the report number, left-to-right.
    const r0201 = rows.filter({ hasText: T0201 });
    await expect(r0201.getByTestId("row-report-no")).toHaveText("NJM-TEST-2026-00871");
    await expect(r0201.getByTestId("row-report-no")).toHaveAttribute("dir", "ltr");
    await expect(r0201.getByTestId("row-plates")).toBeVisible();

    await page.getByTestId("rnc-filter").click();
    await expect(page).toHaveURL(/recorded_not_counted=true/);
    await expect(rows).toHaveCount(2);
    for (const title of [T0212, T0215]) {
      const row = rows.filter({ hasText: title });
      await expect(row).toHaveAttribute("data-rnc", "true");
      await expect(row.getByTestId("rnc-badge")).toHaveText("Recorded, not counted — commuting (OSHA)");
    }
    // Road type and licence check filters reach the API.
    await page.goto("/en/incidents?vehicle_involved=true&road_type=site_road&licence_check=wrong_class");
    await expect(rows.filter({ hasText: T0204 })).toHaveCount(1);
    await expect(rows.filter({ hasText: T0201 })).toHaveCount(0);

    // Neither can be voided for being commuting: the incident page offers no special block, and shows the badge.
    await rows.first().getByRole("link").first().click();
    await expect(page.getByTestId("vehicle-section")).toBeVisible();
  });

  test("AC17 / AC28: K-136 tile chips, the K-136 drill-down badge and C41 from the KPI engine", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const d = await getJson<{ lagging: { metric: string; display: string; components: { key: string; display: string }[] }[] }>(api, `/api/v1/kpi/dashboard?project_id=${pid}&${SEP}`);
    const tile = d.lagging.find((x) => x.metric === "K-136");
    expect(tile).toBeTruthy();
    await openAs(page, USERS.noura, `?${SEP}`);
    const t = page.locator("[data-testid=kpi-tile][data-metric='K-136']");
    await expect(t.getByTestId("tile-value")).toHaveText(tile?.display ?? "");
    const rnc = tile?.components.find((c) => c.key === "recorded_not_counted");
    await expect(t.locator("[data-testid=k136-chip][data-key=recorded_not_counted]")).toContainText(rnc?.display ?? "x");
    for (const road of ["site_road", "airside", "public_road"]) await expect(t.locator(`[data-testid=k136-chip][data-key="road_type:${road}"]`)).toBeVisible();
    await expect(t.locator("[data-testid=k136-chip][data-key='K-137']")).toBeVisible();

    await t.getByTestId("drill-K-136").click();
    const dlg = page.getByTestId("drill-dialog");
    await expect(dlg.getByTestId("drill-source").first()).toBeVisible();
    await expect(dlg.getByTestId("rnc-badge")).toHaveCount(2);
    await page.keyboard.press("Escape");

    const c41 = page.getByTestId("chart-card-C41");
    await c41.scrollIntoViewIfNeeded();
    await expect(c41.getByTestId("chart-C41")).toBeVisible();
    await expect(c41).toContainText("Recorded, not counted (commuting)");
    await expect(c41).toContainText("K-137");
  });

  test("AC23 / AC14: the viewer sees ownership, contractor plates and the licence check, never driver identity or report files", async ({ page }) => {
    const id = await idOf(T0201);
    const noura = await apiAs(USERS.noura);
    const report = await getJson<Report>(noura, `/api/v1/incidents/${id}/accident-report`);
    const fileId = report.files[0]?.id;
    expect(fileId).toBeTruthy();

    await openAs(page, USERS.sarah, `/incidents/${id}`);
    const sec = page.getByTestId("vehicle-section");
    await expect(sec.getByTestId("veh-row")).toHaveCount(2);
    const own = sec.locator("[data-testid=veh-row][data-ownership=contractor]");
    await expect(own.getByTestId("plate")).toBeVisible();
    await expect(own.getByTestId("veh-licence-check")).toHaveAttribute("data-value", "valid");
    await expect(own.getByTestId("veh-driver-summary")).toContainText("GULFPAVE");
    await expect(sec.getByTestId("veh-driver-name")).toHaveCount(0);
    await expect(sec.getByTestId("veh-licence")).toHaveCount(0);
    await expect(sec.getByTestId("veh-insurer")).toHaveCount(0);
    await expect(sec.locator("[data-testid=veh-row][data-ownership=third_party]").getByTestId("plate")).toHaveCount(0);
    await expect(sec.getByTestId("veh-redacted")).toBeVisible();
    await expect(sec.getByTestId("veh-add")).toHaveCount(0);
    const card = page.getByTestId("accident-report-card");
    await expect(card.getByTestId("ar-number")).toHaveText("NJM-TEST-2026-00871");
    await expect(card.getByTestId("ar-files-hidden")).toBeVisible();
    await expect(card.getByTestId("ar-file")).toHaveCount(0);
    // The file URL itself is refused (403), not only hidden.
    const res = await page.request.post(`/api/v1/attachments/${fileId}/signed-url`);
    expect(res.status()).toBe(403);
  });

  test("AC23: the site engineer sees the vehicle and licence check category without driver identity", async ({ page }) => {
    // Omar's grant covers the airside site: the GSE tug incident (0209 in Appendix A).
    const id = await idOf("GSE tug damaged on the apron (airside vehicle incident)");
    await openAs(page, USERS.omar, `/incidents/${id}`);
    const sec = page.getByTestId("vehicle-section");
    const row = sec.locator("[data-testid=veh-row][data-ownership=contractor]");
    await expect(row).toHaveCount(1);
    await expect(row.getByTestId("veh-licence-check")).toHaveAttribute("data-value", "valid");
    await expect(row.getByTestId("veh-driver-summary")).toBeVisible();
    await expect(sec.getByTestId("veh-driver-name")).toHaveCount(0);
    await expect(sec.getByTestId("veh-licence")).toHaveCount(0);
    await expect(page.getByTestId("accident-report-card").getByTestId("ar-file")).toHaveCount(0);
  });

  test("AC24: Noura sees driver identity, licence data and the archived report files", async ({ page }) => {
    const id = await idOf(T0201);
    await openAs(page, USERS.noura, `/incidents/${id}`);
    const sec = page.getByTestId("vehicle-section");
    const own = sec.locator("[data-testid=veh-row][data-ownership=contractor]");
    await expect(own.getByTestId("veh-driver-name")).toContainText("Jomar Santos");
    await expect(own.getByTestId("veh-licence")).toBeVisible();
    await expect(sec.locator("[data-testid=veh-row][data-ownership=third_party]").getByTestId("plate")).toBeVisible();
    await expect(sec.getByTestId("veh-redacted")).toHaveCount(0);
    const card = page.getByTestId("accident-report-card");
    await expect(card.getByTestId("ar-file")).toHaveCount(1);
    await expect(card.getByTestId("ar-files-hidden")).toHaveCount(0);
  });

  test("AC2 / AC3: a near miss marked as a vehicle incident needs road type and a vehicle before it is reported", async ({ page }) => {
    const title = `Vehicle near miss ${uid()}`;
    await openAs(page, USERS.noura, "/incidents/new");
    const form = page.getByTestId("incident-form");
    await form.locator("#occurred_at").fill("2026-10-05T09:30");
    await form.locator("#site_id").selectOption({ index: 1 });
    await form.locator("#responsible_engagement_id").selectOption({ index: 1 });
    await form.getByLabel("Near miss").check();
    await form.locator("#activity").selectOption({ index: 1 });
    await form.locator("#title").fill(title);
    await form.locator("#description").fill("A pickup reversed towards a pedestrian on the site haul road and stopped short.");
    await form.locator("#immediate_actions").fill("Banksman assigned to the reversing area.");
    await form.locator("#actual_severity").selectOption("1");
    await form.locator("#potential_severity").selectOption("3");
    await page.getByTestId("vehicle-involved").check();
    await expect(page.getByTestId("road-type")).toBeVisible();
    // A vehicle incident is reported from its page (vehicles are added there first).
    await expect(page.getByTestId("save-report")).toHaveCount(0);
    await page.getByTestId("save").click();
    await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]{36}$/);
    const sec = page.getByTestId("vehicle-section");
    await expect(sec.getByTestId("veh-missing-report").locator("[data-missing=road_type]")).toBeVisible();
    await expect(sec.getByTestId("veh-missing-report").locator("[data-missing=vehicles]")).toBeVisible();

    await page.getByTestId("transition-reported").click();
    await page.getByTestId("transition-confirm").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "VEHICLE_SECTION_INCOMPLETE");
    await expect(page.getByTestId("form-error").locator("[data-missing=road_type]")).toContainText("Road type");
    await page.keyboard.press("Escape");

    await sec.getByTestId("veh-road-edit").click();
    await page.getByTestId("vr-road-type").selectOption("site_road");
    await page.getByTestId("vr-journey").selectOption("work_task");
    await page.getByTestId("vr-save").click();
    await expect(sec.getByTestId("veh-road-type")).toHaveAttribute("data-value", "site_road");

    await sec.getByTestId("veh-add").click();
    const dlg = page.getByTestId("veh-dialog");
    await dlg.getByTestId("vd-ownership").selectOption("contractor");
    await dlg.getByTestId("vd-role").selectOption("striking");
    await dlg.getByTestId("vd-engagement_id").selectOption({ index: 1 });
    await dlg.getByTestId("vd-category").selectOption("pickup");
    await dlg.getByTestId("vd-damage").selectOption("none");
    await dlg.getByTestId("vd-driver_kind").selectOption("external");
    await dlg.getByTestId("vd-external_driver_name").fill("Test Driver");
    await dlg.getByTestId("vd-seat_belt").selectOption("worn");
    await dlg.getByTestId("vd-save").click();
    const row = sec.getByTestId("veh-row");
    await expect(row).toHaveCount(1);
    await expect(row).toHaveAttribute("data-label", "V1");
    // AC9: an external driver without licence data is "not checked", not blocked.
    await expect(row.getByTestId("veh-licence-check")).toHaveAttribute("data-value", "not_checked");

    await page.getByTestId("transition-reported").click();
    await page.getByTestId("transition-confirm").click();
    await expect(page.getByTestId("transition-reported")).toHaveCount(0);
    await expect(sec.getByTestId("veh-missing-report")).toHaveCount(0);
  });

  test("AC13: a corrected report file supersedes the earlier one; after Closed nothing can be deleted", async ({ page }) => {
    const id = await idOf(T0204);
    await openAs(page, USERS.noura, `/incidents/${id}`);
    const card = page.getByTestId("accident-report-card");
    await expect(card).toHaveAttribute("data-locked", "true");
    await expect(card.getByTestId("ar-locked")).toBeVisible();
    await card.getByTestId("ar-file-input").setInputFiles({ name: "TEST-internal-report.pdf", mimeType: "application/pdf", buffer: pdf("first") });
    await expect(card.getByTestId("ar-file")).toHaveCount(1);
    await card.getByTestId("ar-replace").click();
    await card.getByTestId("ar-file-input").setInputFiles({ name: "TEST-internal-report-corrected.pdf", mimeType: "application/pdf", buffer: pdf("second") });
    await expect(card.getByTestId("ar-file")).toHaveCount(2);
    await expect(card.locator("[data-testid=ar-file][data-superseded=true]")).toHaveCount(1);
    await expect(card.locator("[data-testid=ar-file][data-superseded=false]")).toContainText("corrected");
    await expect(card.getByTestId("ar-delete")).toHaveCount(0);
    const report = await getJson<Report>(await apiAs(USERS.noura), `/api/v1/incidents/${id}/accident-report`);
    const res = await page.request.delete(`/api/v1/attachments/${report.files[0]?.id}`);
    expect(res.status()).toBe(409);
    expect(((await res.json()) as { detail: { code: string } }).detail.code).toBe("ACCIDENT_REPORT_LOCKED");
  });

  test("AC21 / 6f body Najm: entering the report number offers to record the Najm submission with that reference", async ({ page }) => {
    const id = await idOf(T0231);
    await openAs(page, USERS.noura, `/incidents/${id}`);
    await expect(page.getByTestId("fu-panel")).toContainText("Najm");
    const card = page.getByTestId("accident-report-card");
    await expect(card.getByTestId("ar-offer")).toHaveCount(0);
    await card.getByTestId("ar-edit").click();
    await page.getByTestId("ar-no-in").fill("NJM-TEST-2026-01234");
    await page.getByTestId("ar-save").click();
    await expect(card.getByTestId("ar-number")).toHaveText("NJM-TEST-2026-01234");
    await expect(card.getByTestId("ar-offer")).toHaveAttribute("data-body", "najm");
    await card.getByTestId("ar-offer-record").click();
    const ref = page.getByTestId("sub-ref").or(page.getByTestId("offer-ref"));
    await expect(ref).toHaveValue("NJM-TEST-2026-01234");
  });

  test("AC18: a commuting case on a work-task vehicle incident warns and still saves", async ({ page }) => {
    const id = await idOf(T0201);
    const api = await apiAs(USERS.noura);
    const inc = await getJson<{ cases: { id: string }[] }>(api, `/api/v1/incidents/${id}`);
    const caseId = inc.cases[0]?.id;
    expect(caseId).toBeTruthy();
    await openAs(page, USERS.noura, `/injury-cases/${caseId}/edit`);
    await expect(page.getByTestId("case-form")).toBeVisible();
    await expect(page.getByTestId("commuting-mismatch")).toHaveCount(0);
    await page.getByTestId("case-commuting").check();
    await expect(page.getByTestId("commuting-mismatch")).toBeVisible();
    await page.getByTestId("case-form").locator("button[type=submit]").click();
    await expect(page).toHaveURL(new RegExp(`/injury-cases/${caseId}$`));
    await expect(page.getByTestId("api-warnings").locator("[data-code=COMMUTING_PURPOSE_MISMATCH]").or(page.locator("[data-sonner-toast]").filter({ hasText: "journey purpose is not commuting" })).first()).toBeVisible();
    // Put the seed back.
    const res = await api.patch(`/api/v1/injury-cases/${caseId}`, { data: { commuting: false } });
    expect(res.ok()).toBeTruthy();
  });

  test("AC32: Arabic labels and badges, with plates and report numbers kept left-to-right", async ({ page }) => {
    const id = await idOf(T0215);
    await login(page, USERS.noura, "ar");
    await page.goto(`/ar/incidents/${id}`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const sec = page.getByTestId("vehicle-section");
    await expect(sec.getByTestId("rnc-badge")).toHaveText("مسجل، غير محتسب — تنقل (OSHA)");
    await expect(sec.getByTestId("veh-road-type")).toHaveText("طريق عام");
    await expect(sec.getByTestId("veh-journey")).toHaveText("تنقل بوسيلة الشركة");
    await expect(sec.getByText("المركبات", { exact: true })).toBeVisible();
    const num = page.getByTestId("accident-report-card").getByTestId("ar-number");
    await expect(num).toHaveText("TP-TEST-2026-3354");
    await expect(num).toHaveAttribute("dir", "ltr");
    const plate = sec.getByTestId("plate").first().locator("bdi[dir=ltr]");
    await expect(plate).toBeVisible();
    await page.goto("/ar/incidents?recorded_not_counted=true");
    await expect(page.getByTestId("incident-row").first().getByTestId("rnc-badge")).toHaveText("مسجل، غير محتسب — تنقل (OSHA)");
    await expect(page.getByText("مسجل، غير محتسب (تنقل)").first()).toBeVisible();
  });
});
