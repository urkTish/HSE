import type { APIRequestContext, Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, selectByPrefix, uid, userId, USERS } from "./helpers";
import { makePng } from "./p2-helpers";
import { openAs, pinProject } from "./p6a-helpers";

// Option 7b site vehicles & drivers (spec 7b-fleet-driver, Prototype). Seed: Appendix A; the e2e clock is
// 2026-10-06 10:00, so readiness is read at that date (VEH-0109's hold check is dated 10-12 and is not yet on hold;
// the defect-hold ACs create their own hold).
const TODAY = "2026-10-06";

type Vehicle = { id: string; vehicle_no: string; readiness: string; engagement: { short_code: string } };
type Auth = { worker: { worker_no: string } };
type Dep = { worker_id: string; worker_no: string; engagement: { short_code: string } | null };
type Tpl = { template: { items: { item_code: string }[] } };

/** A random 17-character VIN (no I, O or Q). */
function vin(): string {
  const set = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789";
  return "JTF" + Array.from({ length: 14 }, () => set[Math.floor(Math.random() * set.length)]).join("");
}

async function ania(api: APIRequestContext): Promise<string> {
  return projectId(api, "ANIA-EXP");
}

async function vehicles(api: APIRequestContext): Promise<Map<string, Vehicle>> {
  const pid = await ania(api);
  const page = await getJson<{ items: Vehicle[] }>(api, `/api/v1/projects/${pid}/site-vehicles?page_size=200`);
  return new Map(page.items.map((v) => [v.vehicle_no, v]));
}

async function vehicleId(no: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const v = (await vehicles(api)).get(no);
  expect(v, no).toBeTruthy();
  return (v as Vehicle).id;
}

const taken = new Set<string>();
/** A mobilised worker of a contractor with no driver authorisation at all (and no user account). */
async function freeWorker(contractor: string): Promise<Dep> {
  const api = await apiAs(USERS.faisal);
  const pid = await ania(api);
  const auths = await getJson<{ items: Auth[] }>(api, `/api/v1/projects/${pid}/driver-authorisations?page_size=200`);
  const held = new Set(auths.items.map((a) => a.worker.worker_no));
  const deps = await getJson<{ items: Dep[] }>(api, `/api/v1/projects/${pid}/deployments?status=mobilised&page_size=200`);
  const linked = new Set(["WKR-000011", "WKR-000024", "WKR-000025", "WKR-000026", "WKR-000027", "WKR-000028", "WKR-000029", "WKR-000030", "WKR-000031", "WKR-000032"]);
  const d = deps.items.find((x) => x.engagement?.short_code === contractor && !held.has(x.worker_no) && !linked.has(x.worker_no) && !taken.has(x.worker_no));
  expect(d, `free ${contractor} worker`).toBeTruthy();
  taken.add((d as Dep).worker_no);
  return d as Dep;
}

/** Pick a mobilised worker in a DeploymentPicker by worker number. */
async function pickWorker(page: Page, id: string, workerNo: string): Promise<void> {
  await page.getByTestId(`${id}-search`).fill(workerNo);
  await selectByPrefix(page.getByTestId(id), workerNo);
}

async function expectError(page: Page, code: string): Promise<void> {
  await expect(page.getByTestId("form-error").first()).toHaveAttribute("data-code", code);
}

/** Record a passing pre-use check through the API (fixture for AC15). */
async function passingCheck(api: APIRequestContext, vehicle: string, workerId: string): Promise<void> {
  const pid = await ania(api);
  const form = await getJson<Tpl>(api, `/api/v1/projects/${pid}/pre-use-checks/form?vehicle_id=${vehicle}`);
  const res = await api.post(`/api/v1/projects/${pid}/pre-use-checks`, {
    data: { vehicle_id: vehicle, driver_worker_id: workerId, source: "app", answers: form.template.items.map((i) => ({ item_code: i.item_code, answer: "compliant" })) },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}

async function depOf(workerNo: string): Promise<Dep> {
  const api = await apiAs(USERS.faisal);
  const pid = await ania(api);
  const deps = await getJson<{ items: Dep[] }>(api, `/api/v1/projects/${pid}/deployments?status=mobilised&q=${workerNo}`);
  const d = deps.items.find((x) => x.worker_no === workerNo);
  expect(d, workerNo).toBeTruthy();
  return d as Dep;
}

test.describe("7b site vehicles & drivers (Prototype)", () => {
  test("AC1: sidebar entry with the Prototype badge; RBT-52 (7b off) answers SITE_VEHICLES_NOT_LIVE and the page says so", async ({ page }) => {
    await login(page, USERS.faisal);
    await pinProject(page, "ANIA-EXP");
    const nav = page.getByTestId("nav-site-vehicles");
    await expect(nav).toBeVisible();
    await expect(nav.getByTestId("prototype-badge")).toHaveText("Prototype");
    await nav.click();
    await expect(page).toHaveURL(/\/en\/site-vehicles$/);
    await expect(page.getByTestId("prototype-badge").first()).toBeVisible();
    await expect(page.getByTestId("sv-vehicle-row").first()).toBeVisible();

    const api = await apiAs(USERS.faisal);
    const rbt = await projectId(api, "RBT-52");
    const res = await api.get(`/api/v1/projects/${rbt}/site-vehicles`);
    expect(res.status()).toBe(422);
    expect((await res.json()).detail.code).toBe("SITE_VEHICLES_NOT_LIVE");
    await page.getByTestId("project-switcher").selectOption(rbt);
    await expect(page.getByTestId("sv-not-live")).toBeVisible();
    await page.goto("/en/site-vehicles");
    await expect(page.getByTestId("sv-not-live")).toBeVisible();
    await expect(page.getByTestId("sv-vehicle-row")).toHaveCount(0);
    // The HSE Manager still reaches the settings page to switch 7b on.
    await page.goto("/en/site-vehicles/settings");
    await expect(page.getByTestId("sv-settings-off")).toBeVisible();
  });

  test("AC3 / AC5: summary tiles, docs_expired and not_certified rows, VEH-0107 insurance expiring; no Phase 4 action", async ({ page }) => {
    await openAs(page, USERS.faisal, "/site-vehicles");
    const sum = page.getByTestId("sv-summary");
    await expect(sum.locator("[data-testid=sv-sum][data-key=site_vehicles]")).toHaveAttribute("data-value", "24");
    await expect(sum.locator("[data-testid=sv-sum][data-key=docs_expired]")).toHaveAttribute("data-value", "2");
    await expect(sum.locator("[data-testid=sv-sum][data-key=not_certified]")).toHaveAttribute("data-value", "1");
    await expect(page.locator("[data-testid=sv-vehicle-row][data-vehicle=VEH-0116]")).toHaveAttribute("data-readiness", "docs_expired");
    await expect(page.locator("[data-testid=sv-vehicle-row][data-vehicle=VEH-0119]")).toHaveAttribute("data-readiness", "not_certified");

    // Readiness filter from the summary tile.
    await sum.locator("[data-testid=sv-sum][data-key=docs_expired]").getByRole("button").click();
    await expect(page).toHaveURL(/readiness=docs_expired/);
    await expect(page.getByTestId("sv-vehicle-row")).toHaveCount(2);

    await page.goto(`/en/site-vehicles/${await vehicleId("VEH-0107")}`);
    await expect(page.locator("[data-testid=sv-doc][data-kind=insurance]")).toHaveAttribute("data-state", "expiring");

    await page.goto(`/en/site-vehicles/${await vehicleId("VEH-0119")}`);
    await expect(page.getByTestId("sv-vehicle-detail")).toHaveAttribute("data-readiness", "not_certified");
    await expect(page.getByTestId("sv-not-certified")).toBeVisible();
    await expect(page.getByTestId("sv-clear-hold")).toHaveCount(0);
  });

  test("AC2: a crew bus without an operating card is refused; with one it registers; withdraw sits in the Record actions band", async ({ page }) => {
    const u = uid();
    await openAs(page, USERS.faisal, "/site-vehicles/new");
    const f = page.getByTestId("sv-vehicle-form");
    await expect(f).toBeVisible();
    await selectByPrefix(page.getByTestId("sv-f-eng"), "GULFPAVE");
    await page.getByTestId("sv-f-class").selectOption("crew_bus");
    await page.getByTestId("sv-f-seats").fill("22");
    await page.getByTestId("sv-f-plate-type").selectOption("transport");
    await page.getByTestId("sv-f-pla").fill("ب ح د");
    await page.getByTestId("sv-f-ple").fill("BHD");
    await page.getByTestId("sv-f-pld").fill(String(1000 + Math.floor(Math.random() * 8999)));
    await page.getByTestId("sv-f-fleet").fill(`GP-CB-${u}`);
    await page.getByTestId("sv-f-vin").fill(vin());
    await page.getByTestId("sv-f-make").fill("Toyota Coaster");
    await page.getByTestId("sv-f-ist").fill("2027-06-30");
    await page.getByTestId("sv-f-mvpi").fill("2027-03-31");
    await page.getByTestId("sv-f-ins-no").fill(`POL-TEST-${u}`);
    await page.getByTestId("sv-f-ins").fill("2027-05-31");
    await page.getByTestId("sv-vehicle-save").click();
    await expectError(page, "OPERATING_CARD_REQUIRED");

    await page.getByTestId("sv-f-oc-no").fill(`OC-TEST-${u}`);
    await page.getByTestId("sv-f-oc").fill("2027-04-30");
    await page.getByTestId("sv-vehicle-save").click();
    const detail = page.getByTestId("sv-vehicle-detail");
    await expect(detail).toBeVisible();
    await expect(page).toHaveURL(/\/site-vehicles\/[0-9a-f-]{36}$/);

    // Irreversible: withdraw lives in the page-end Record actions band.
    const band = page.getByTestId("sv-record-actions");
    await band.getByTestId("sv-withdraw").click();
    await page.getByTestId("sv-withdraw-reason").fill("Off-hired back to the rental company");
    await page.getByTestId("sv-withdraw-confirm").click();
    await expect(detail).toHaveAttribute("data-readiness", "withdrawn");
  });

  test("AC4: Ahmed (RAWABI rep) sees RAWABI vehicles only and cannot verify documents", async ({ page }) => {
    await openAs(page, USERS.ahmed, "/site-vehicles");
    const rows = page.getByTestId("sv-vehicle-row");
    await expect(rows.first()).toBeVisible();
    await expect(rows).toHaveCount(10);
    await expect(page.locator("[data-testid=sv-vehicle-row][data-vehicle=VEH-0119]")).toHaveCount(0);
    await expect(page.locator("[data-testid=sv-vehicle-row][data-vehicle=VEH-0101]")).toHaveCount(0);
    await page.locator("[data-testid=sv-vehicle-row][data-vehicle=VEH-0115]").getByRole("link").first().click();
    await expect(page.getByTestId("sv-vehicle-detail")).toBeVisible();
    await expect(page.getByTestId("sv-verify")).toHaveCount(0);
    await expect(page.getByTestId("sv-record-check")).toBeVisible();
  });

  test("AC6: the K-138…K-140 dashboard tiles show the server's values", async ({ page }) => {
    await login(page, USERS.faisal);
    const resp = page.waitForResponse((r) => r.url().includes("/api/v1/kpi/site-vehicles") && r.ok());
    await pinProject(page, "ANIA-EXP");
    const body = (await (await resp).json()) as { metrics: { metric: string; display: string }[] };
    const tiles = page.getByTestId("sv-tiles");
    await expect(tiles).toBeVisible();
    await expect(tiles.getByTestId("prototype-badge")).toBeVisible();
    for (const m of ["K-138", "K-139", "K-140"]) {
      const v = body.metrics.find((x) => x.metric === m);
      expect(v, m).toBeTruthy();
      await expect(tiles.locator(`[data-testid=sv-tile][data-metric='${m}']`).getByTestId("sv-tile-value")).toHaveText(v?.display ?? "x");
    }
    await expect(tiles.locator("[data-testid=sv-tile][data-metric='K-138'] [data-testid=sv-chip]").first()).toBeVisible();
  });

  test("AC7 / AC8 / AC9: licence class and assessment age are checked; activation warns on the missing DEF-DRV hook; revoke in the band", async ({ page }) => {
    const w = await freeWorker("GULFPAVE");
    await openAs(page, USERS.faisal, "/site-vehicles/authorisations/new");
    await expect(page.getByTestId("sv-auth-form")).toBeVisible();
    const prefill = page.waitForResponse((r) => r.url().includes("/driver-authorisations/prefill"));
    await pickWorker(page, "da-worker", w.worker_no);
    await prefill;
    const groups = page.getByTestId("da-groups");
    await groups.locator("input[value=light]").check();
    await groups.locator("input[value=bus]").check();
    await page.getByTestId("da-issuer").selectOption("ksa");
    await page.getByTestId("da-class").selectOption("private");
    await page.getByTestId("da-expiry").fill("2029-01-31");
    await page.getByTestId("da-assess").fill("2026-09-20");
    await page.getByTestId("da-assessor").fill("Faisal Al-Harbi (HSE)");
    await page.getByTestId("da-issued").fill("2026-10-01");
    await page.getByTestId("da-save").click();
    await expectError(page, "LICENCE_CLASS_NOT_COVERING");

    await page.getByTestId("da-class").selectOption("public_transport");
    await page.getByTestId("da-assess").fill("2025-09-01");
    await page.getByTestId("da-save").click();
    await expectError(page, "ASSESSMENT_TOO_OLD");

    await page.getByTestId("da-assess").fill("2026-09-20");
    await page.getByTestId("da-save").click();
    const detail = page.getByTestId("sv-auth-detail");
    await expect(detail).toHaveAttribute("data-status", "draft");
    await page.getByTestId("da-activate").click();
    await page.getByTestId("da-move-confirm").click();
    await expect(detail).toHaveAttribute("data-status", "active");
    await expect(page.locator(".api-warning-HOOK_NOT_MET_WARN").first()).toBeVisible();
    await expect(page.locator("[data-testid=da-hook]").first()).toBeVisible();

    await page.getByTestId("da-record-actions").getByTestId("da-revoke").click();
    await page.getByTestId("da-move-reason").fill("Issued in error during the e2e run");
    await page.getByTestId("da-move-confirm").click();
    await expect(detail).toHaveAttribute("data-status", "revoked");
  });

  test("AC12: Omar (site engineer) sees authorisation status only", async ({ page }) => {
    await openAs(page, USERS.omar, "/site-vehicles/authorisations");
    const rows = page.getByTestId("sv-auth-row");
    await expect(rows.first()).toBeVisible();
    await expect(rows.first()).toHaveAttribute("data-redacted", "true");
    await expect(page.getByTestId("sv-new-auth")).toHaveCount(0);
    await rows.first().getByRole("link").first().click();
    await expect(page.getByTestId("sv-auth-detail")).toBeVisible();
    await expect(page.getByTestId("da-redacted")).toBeVisible();
    await expect(page.getByTestId("da-hooks")).toHaveCount(0);
  });

  test("AC13: a failed brakes check puts the vehicle on defect hold with a finding and CA; clearing needs a passing re-check", async ({ page }) => {
    const vid = await vehicleId("VEH-0124");
    await openAs(page, USERS.noura, `/site-vehicles/checks/new?vehicle=${vid}`);
    await expect(page.getByTestId("pu-template")).toContainText("VPU-L");
    await pickWorker(page, "pu-driver", "WKR-002382");
    await page.getByTestId("pu-all-ok").click();
    await page.getByTestId("pu-fail-VPL-01").click();
    await expect(page.getByTestId("pu-critical")).toBeVisible();
    await page.getByTestId("pu-note-VPL-01").fill("Brake pedal goes to the floor, soft");
    await page.getByTestId("pu-submit").click();
    const check = page.getByTestId("sv-check-detail");
    await expect(check).toHaveAttribute("data-passed", "false");
    await expect(check).toHaveAttribute("data-hold", "true");
    await expect(page.getByTestId("sv-finding").first()).toBeVisible();
    await expect(page.getByTestId("sv-finding-ca").first()).toBeVisible();

    await page.goto(`/en/site-vehicles/${vid}`);
    await expect(page.getByTestId("sv-vehicle-detail")).toHaveAttribute("data-readiness", "defect_hold");
    await expect(page.getByTestId("sv-hold")).toBeVisible();
    await expect(page.getByTestId("sv-hold-ca")).toBeVisible();
    await page.getByTestId("sv-record-actions").getByTestId("sv-clear-hold").click();
    await page.getByTestId("sv-repair-note").fill("Brake master cylinder replaced by the workshop");
    await page.getByTestId("sv-clear-confirm").click();
    await expectError(page, "VEHICLE_DEFECT_HOLD");
    await page.keyboard.press("Escape");

    await page.getByTestId("sv-record-check").click();
    await expect(page.getByTestId("pu-on-hold")).toBeVisible();
    await pickWorker(page, "pu-driver", "WKR-002382");
    await page.getByTestId("pu-all-ok").click();
    await page.getByTestId("pu-submit").click();
    await expect(page.getByTestId("sv-check-detail")).toHaveAttribute("data-passed", "true");

    await page.goto(`/en/site-vehicles/${vid}`);
    await page.getByTestId("sv-record-actions").getByTestId("sv-clear-hold").click();
    await page.getByTestId("sv-repair-note").fill("Brake master cylinder replaced by the workshop");
    await page.getByTestId("sv-clear-confirm").click();
    await expect(page.getByTestId("sv-vehicle-detail")).toHaveAttribute("data-readiness", "ready");
    await expect(page.getByTestId("sv-hold")).toHaveCount(0);
  });

  test("AC15: a second check on the same vehicle and date is refused with PRE_USE_CHECK_EXISTS", async ({ page }) => {
    const vid = await vehicleId("VEH-0103");
    const d = await depOf("WKR-003337");
    await passingCheck(await apiAs(USERS.noura), vid, d.worker_id);
    await openAs(page, USERS.noura, `/site-vehicles/checks/new?vehicle=${vid}&date=${TODAY}`);
    await expect(page.getByTestId("pu-existing")).toBeVisible();
    await pickWorker(page, "pu-driver", "WKR-003337");
    await page.getByTestId("pu-all-ok").click();
    await page.getByTestId("pu-submit").click();
    await expectError(page, "PRE_USE_CHECK_EXISTS");
  });

  test("AC16: a driver without an authorisation is saved under warn with DRIVER_NOT_AUTHORISED_WARN and listed as not authorised", async ({ page }) => {
    const w = await freeWorker("GULFPAVE");
    const vid = await vehicleId("VEH-0104");
    await openAs(page, USERS.noura, `/site-vehicles/checks/new?vehicle=${vid}`);
    await pickWorker(page, "pu-driver", w.worker_no);
    await page.getByTestId("pu-all-ok").click();
    await page.getByTestId("pu-submit").click();
    await expect(page.getByTestId("sv-check-detail")).toHaveAttribute("data-passed", "true");
    await expect(page.locator(".api-warning-DRIVER_NOT_AUTHORISED_WARN").first()).toBeVisible();
    await page.goto(`/en/site-vehicles/checks?vehicle_id=${vid}&driver_authorised=false`);
    const row = page.locator("[data-testid=sv-check-row]").filter({ hasText: "VEH-0104" }).first();
    await expect(row.getByTestId("sv-authorised")).toHaveAttribute("data-ok", "false");
  });

  test("AC17: Ahmed records a paper check with a photo; it is listed with the paper badge", async ({ page }) => {
    const vid = await vehicleId("VEH-0115");
    await openAs(page, USERS.ahmed, `/site-vehicles/checks/new?vehicle=${vid}`);
    await pickWorker(page, "pu-driver", "WKR-001012");
    await page.getByTestId("pu-source").selectOption("paper");
    await page.getByTestId("pu-all-ok").click();
    await page.getByTestId("pu-paper-photo-input").setInputFiles({ name: "paper-check.png", mimeType: "image/png", buffer: makePng(64) });
    await expect(page.getByTestId("pu-paper-photo").locator("img").first()).toBeVisible();
    await page.getByTestId("pu-submit").click();
    await expect(page.getByTestId("sv-check-detail")).toHaveAttribute("data-passed", "true");
    await page.goto("/en/site-vehicles/checks?source=paper");
    const row = page.locator("[data-testid=sv-check-row][data-source=paper]").filter({ hasText: "VEH-0115" }).first();
    await expect(row.getByTestId("sv-paper")).toBeVisible();
  });

  test("AC19: the journey form shows the 'recommended' hint for 160 km or a 04:30 departure, none for 40 km by day; it saves", async ({ page }) => {
    await openAs(page, USERS.noura, `/site-vehicles/journeys/new?vehicle=${await vehicleId("VEH-0101")}`);
    await expect(page.getByTestId("sv-journey-form")).toBeVisible();
    await page.getByTestId("jp-dest").fill("Dammam port gate 3");
    await page.getByTestId("jp-km").fill("160");
    await page.getByTestId("jp-depart").fill(`${TODAY}T13:00`);
    await page.getByTestId("jp-arrive-at").fill(`${TODAY}T15:00`);
    await expect(page.getByTestId("jp-hint")).toHaveAttribute("data-reasons", /distance/);
    await page.getByTestId("jp-km").fill("40");
    await expect(page.getByTestId("jp-no-hint")).toBeVisible();
    await page.getByTestId("jp-depart").fill("2026-10-07T04:30");
    await page.getByTestId("jp-arrive-at").fill("2026-10-07T05:30");
    await expect(page.getByTestId("jp-hint")).toHaveAttribute("data-reasons", /night/);
    await page.getByTestId("jp-depart").fill(`${TODAY}T13:00`);
    await page.getByTestId("jp-arrive-at").fill(`${TODAY}T14:00`);
    await expect(page.getByTestId("jp-no-hint")).toBeVisible();
    await selectByPrefix(page.getByTestId("jp-contact"), "Omar");
    await pickWorker(page, "jp-driver", "WKR-003337");
    await page.getByTestId("jp-save").click();
    const detail = page.getByTestId("sv-journey-detail");
    await expect(detail).toHaveAttribute("data-status", "planned");
    await expect(detail).toHaveAttribute("data-overdue", "false");

    // Cancel sits in the Record actions band.
    await page.getByTestId("jp-record-actions").getByTestId("jp-cancel").click();
    await page.getByTestId("jp-cancel-reason").fill("Trip postponed");
    await page.getByTestId("jp-cancel-confirm").click();
    await expect(detail).toHaveAttribute("data-status", "cancelled");
  });

  test("AC20: VEHICLE_NOT_READY, PASSENGERS_EXCEED_SEATS and JOURNEY_CONTACT_IS_DRIVER", async ({ page }) => {
    await openAs(page, USERS.noura, `/site-vehicles/journeys/new?vehicle=${await vehicleId("VEH-0119")}`);
    await page.getByTestId("jp-dest").fill("Riyadh yard");
    await page.getByTestId("jp-km").fill("30");
    await page.getByTestId("jp-depart").fill(`${TODAY}T13:00`);
    await page.getByTestId("jp-arrive-at").fill(`${TODAY}T14:00`);
    await selectByPrefix(page.getByTestId("jp-contact"), "Omar");
    await pickWorker(page, "jp-driver", "WKR-003337");
    await page.getByTestId("jp-save").click();
    await expectError(page, "VEHICLE_NOT_READY");

    await selectByPrefix(page.getByTestId("jp-vehicle"), "VEH-0120");
    await page.getByTestId("jp-pax").fill("5");
    await page.getByTestId("jp-save").click();
    await expectError(page, "PASSENGERS_EXCEED_SEATS");

    await page.getByTestId("jp-pax").fill("1");
    await selectByPrefix(page.getByTestId("jp-contact"), "Noura");
    await pickWorker(page, "jp-driver", "WKR-000011");
    await page.getByTestId("jp-save").click();
    await expectError(page, "JOURNEY_CONTACT_IS_DRIVER");
  });

  test("AC21: a planned journey past its arrival is flagged Overdue (no escalation); Mark arrived sets Arrived", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const pid = await ania(api);
    const d = await depOf("WKR-003337");
    const res = await api.post(`/api/v1/projects/${pid}/journey-plans`, {
      data: {
        vehicle_id: await vehicleId("VEH-0101"),
        driver_worker_id: d.worker_id,
        passengers: 1,
        origin: "ANIA-EXP site",
        destination: "Jubail supplier yard",
        distance_km: 60,
        planned_depart: `${TODAY}T06:00:00+03:00`,
        planned_arrive: `${TODAY}T07:30:00+03:00`,
        contact_user_id: await userId(api, USERS.omar),
      },
    });
    expect(res.ok(), await res.text()).toBeTruthy();
    const plan = (await res.json()) as { plan_no: string; id: string };

    await openAs(page, USERS.noura, "/site-vehicles/journeys?overdue=true");
    const row = page.locator(`[data-testid=sv-journey-row][data-no='${plan.plan_no}']`);
    await expect(row).toHaveAttribute("data-overdue", "true");
    await expect(row.getByTestId("sv-overdue")).toBeVisible();
    await row.getByRole("link").first().click();
    const detail = page.getByTestId("sv-journey-detail");
    await expect(detail).toHaveAttribute("data-overdue", "true");
    await expect(page.getByTestId("jp-overdue-note")).toBeVisible();
    await page.getByTestId("jp-arrive").click();
    await page.getByTestId("jp-arrive-confirm").click();
    await expect(detail).toHaveAttribute("data-status", "arrived");
    await expect(detail).toHaveAttribute("data-overdue", "false");
  });

  test("AC22: Sarah (viewer) sees the aggregates only — summary and tiles, no registers", async ({ page }) => {
    await openAs(page, USERS.sarah, "/site-vehicles");
    await expect(page.getByTestId("sv-summary")).toBeVisible();
    await expect(page.getByTestId("sv-aggregates-only")).toBeVisible();
    await expect(page.getByTestId("sv-vehicle-row")).toHaveCount(0);
    await expect(page.getByTestId("sub-sv-auths")).toHaveCount(0);
    await page.goto("/en");
    const tiles = page.getByTestId("sv-tiles");
    await expect(tiles).toBeVisible({ timeout: 30_000 });
    await expect(tiles.getByRole("link")).toHaveCount(0);
  });

  test("AC24: Arabic labels and the Prototype badge; plates and refs stay left-to-right", async ({ page }) => {
    await openAs(page, USERS.faisal, "/site-vehicles", "ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const badge = page.getByTestId("prototype-badge").first();
    await expect(badge).toBeVisible();
    await expect(badge).not.toContainText("Prototype");
    const row = page.locator("[data-testid=sv-vehicle-row][data-vehicle=VEH-0107]");
    const ref = row.getByRole("link", { name: "VEH-0107" });
    await expect(ref).toBeVisible();
    expect(await ref.evaluate((el) => getComputedStyle(el).direction)).toBe("ltr");
    await expect(row.getByTestId("sv-readiness")).not.toContainText("Ready");
    await page.goto("/ar/site-vehicles/journeys/new");
    await page.getByTestId("jp-km").fill("200");
    await page.getByTestId("jp-depart").fill(`${TODAY}T13:00`);
    await page.getByTestId("jp-arrive-at").fill(`${TODAY}T16:00`);
    await expect(page.getByTestId("jp-hint")).not.toContainText("recommended");
  });

  test("Settings: the HSE Manager edits the 7b settings (range-checked); the HSE Officer reads them", async ({ page }) => {
    await openAs(page, USERS.faisal, "/site-vehicles/settings");
    const km = page.getByTestId("svs-km");
    await expect(km).toHaveValue("150");
    await km.fill("20");
    await page.getByTestId("svs-save").click();
    await expectError(page, "SETTING_OUT_OF_RANGE");
    await km.fill("180");
    await page.getByTestId("svs-save").click();
    await expect(page.getByTestId("form-error")).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("svs-km")).toHaveValue("180");
    await page.getByTestId("svs-km").fill("150");
    await page.getByTestId("svs-save").click();
    await expect(page.getByTestId("form-error")).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("svs-km")).toHaveValue("150");

    await openAs(page, USERS.noura, "/site-vehicles/settings");
    await expect(page.getByTestId("sv-settings")).toBeVisible();
    await expect(page.getByTestId("svs-save")).toHaveCount(0);
    await expect(page.getByTestId("svs-km")).toBeDisabled();
  });

  test("Phase 2 vehicle register shows the site-use column and the detail links to the 7b record", async ({ page }) => {
    await openAs(page, USERS.faisal, "/vehicles?q=GP-CB-07");
    const cell = page.getByTestId("vehicle-site-use").first();
    await expect(cell).toBeVisible();
    await page.getByRole("link", { name: /VEH-0107/ }).first().click();
    await expect(page.getByTestId("vehicle-site-card")).toBeVisible();
    await page.getByTestId("vehicle-site-link").click();
    await expect(page.getByTestId("sv-vehicle-detail")).toBeVisible();
  });
});
