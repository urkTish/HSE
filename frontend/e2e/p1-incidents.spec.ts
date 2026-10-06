import { expect, test, type APIRequestContext } from "@playwright/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";

async function setup(api: APIRequestContext) {
  const ania = await projectId(api, "ANIA-EXP");
  const sites = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects/${ania}/sites?page_size=100`);
  const engs = await getJson<{
    items: { id: string; contractor: { short_code: string } }[];
  }>(api, `/api/v1/projects/${ania}/engagements?page_size=100`);
  return {
    ania,
    sLand: sites.items.find((s) => s.code === "S-LAND")?.id ?? "",
    sAir: sites.items.find((s) => s.code === "S-AIR")?.id ?? "",
    najd: engs.items.find((e) => e.contractor.short_code === "NAJD")?.id ?? "",
    rawabi: engs.items.find((e) => e.contractor.short_code === "RAWABI")?.id ?? "",
  };
}

async function injuryIncident(api: APIRequestContext, title: string, onAirside = false) {
  const s = await setup(api);
  const res = await api.post(`/api/v1/projects/${s.ania}/incidents`, {
    data: {
      site_id: onAirside ? s.sAir : s.sLand,
      responsible_engagement_id: onAirside ? s.rawabi : s.najd,
      occurred_at: "2026-10-03T06:40:00Z",
      shift: "day",
      incident_types: ["injury_illness"],
      primary_type: "injury_illness",
      title,
      description: "Worker cut hand on sheet edge while carrying materials.",
      immediate_actions: "First aid given at site clinic.",
      activity: "material_handling",
      work_related: true,
      actual_severity: 1,
      potential_severity: 2,
    },
  });
  expect(res.status(), await res.text()).toBe(201);
  return { ...s, incident: (await res.json()) as { id: string; ref: string } };
}

async function addCase(api: APIRequestContext, incidentId: string, najd: string, extra: Record<string, unknown> = {}) {
  const res = await api.post(`/api/v1/incidents/${incidentId}/injury-cases`, {
    data: {
      person_type: "contractor_worker",
      employer_engagement_id: najd,
      person_name: "Imran Hussain",
      id_type: "iqama",
      id_number: "2000000017",
      trade: "scaffolder",
      body_part: "hand",
      nature: "laceration",
      mechanism: "struck_against",
      agency: "materials",
      treatments: ["wound_cleaning", "wound_covering_steristrips"],
      treated_at: "site_clinic",
      ...extra,
    },
  });
  expect(res.status(), await res.text()).toBe(201);
  return (await res.json()) as { id: string; derived_category: string };
}

async function report(api: APIRequestContext, incidentId: string) {
  const res = await api.post(`/api/v1/incidents/${incidentId}/transitions`, {
    data: { to_status: "reported" },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}

test.describe("Incidents & PDPL", () => {
  test("AC19: near miss cannot be combined with another type (form blocks it)", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/incidents/new");
    const types = page.getByTestId("incident_types");
    await types.getByLabel("Near miss").check();
    await types.getByLabel("Property damage").check();
    await page.getByTestId("save").click();
    await expect(page.getByTestId("incident_types").getByRole("alert")).toContainText(/near miss cannot be combined/i);
    await expect(page).toHaveURL(/\/incidents\/new/);
  });

  test("AC33: a possible ID number in the description is flagged", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/incidents/new");
    await page.locator("#description").fill("Worker 2000000017 slipped near the gate");
    await expect(page.getByTestId("possible-id-hint")).toBeVisible();
  });

  test("AC20: an injury incident without a case cannot be reported", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const { incident } = await injuryIncident(api, "E2E hand cut no case");
    await login(page, USERS.noura);
    await page.goto(`/en/incidents/${incident.id}`);
    await page.getByTestId("transition-reported").click();
    const confirm = page.getByTestId("transition-confirm");
    if (await confirm.isVisible().catch(() => false)) await confirm.click();
    await expect(page.getByText("Add at least one injured person before reporting.").first()).toBeVisible();
  });

  test("AC13: treatments drive the derived category (FAC → MTC)", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const s = await injuryIncident(api, "E2E FAC to MTC");
    const kase = await addCase(api, s.incident.id, s.najd);
    expect(kase.derived_category).toBe("FAC");
    await login(page, USERS.noura);
    await page.goto(`/en/injury-cases/${kase.id}`);
    await expect(page.getByTestId("case-category")).toContainText("FAC");
    const res = await api.patch(`/api/v1/injury-cases/${kase.id}`, {
      data: {
        treatments: ["wound_cleaning", "wound_covering_steristrips", "sutures_staples_glue"],
      },
    });
    expect(res.ok(), await res.text()).toBeTruthy();
    await page.reload();
    await expect(page.getByTestId("case-category")).toContainText("MTC");
  });

  test("AC29/AC30: Omar sees a de-identified label; Noura sees the name and a masked ID", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    // Omar (site engineer) is scoped to S-AIR, so the incident is on S-AIR with an injured NAJD worker.
    const s = await injuryIncident(api, "E2E PDPL view", true);
    const kase = await addCase(api, s.incident.id, s.najd);
    await report(api, s.incident.id);

    await login(page, USERS.omar);
    await page.goto(`/en/incidents/${s.incident.id}`);
    await expect(page.getByTestId("case-label").first()).toContainText(/Person 1 · .*scaffolder.* · NAJD/i);
    await page.goto(`/en/injury-cases/${kase.id}`);
    await expect(page.getByTestId("redaction-note")).toBeVisible();
    await expect(page.locator("main")).not.toContainText("Imran Hussain");
    await expect(page.locator("main")).not.toContainText("2000000017");
    await expect(page.getByTestId("medical-card")).toHaveCount(0);

    await page.context().clearCookies();
    await login(page, USERS.noura);
    await page.goto(`/en/injury-cases/${kase.id}`);
    await expect(page.getByTestId("person-name")).toHaveText("Imran Hussain");
    await expect(page.getByTestId("id-number")).toContainText("2*******17");
  });

  test("AC31: a privacy case hides the name from the HSE Officer but not the HSE Manager", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const s = await injuryIncident(api, "E2E privacy case");
    const kase = await addCase(api, s.incident.id, s.najd, {
      privacy_case: true,
      privacy_reason: "employee_request",
    });
    await login(page, USERS.noura);
    await page.goto(`/en/injury-cases/${kase.id}`);
    await expect(page.getByTestId("person-name")).toContainText("Privacy case");
    await expect(page.locator("main")).not.toContainText("Imran Hussain");
    await page.context().clearCookies();
    await login(page, USERS.faisal);
    await page.goto(`/en/injury-cases/${kase.id}`);
    await expect(page.getByTestId("person-name")).toHaveText("Imran Hussain");
  });

  test("AC21: excluded cases list shows the reason", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const s = await setup(api);
    const res = await api.post(`/api/v1/projects/${s.ania}/incidents`, {
      data: {
        site_id: s.sLand,
        responsible_engagement_id: s.najd,
        occurred_at: "2026-10-02T18:00:00Z",
        shift: "night",
        incident_types: ["injury_illness"],
        primary_type: "injury_illness",
        title: "E2E off-duty camp injury",
        description: "Worker hurt during an off-duty game at the camp.",
        immediate_actions: "Taken to clinic.",
        activity: "other",
        actual_severity: 1,
        potential_severity: 1,
        work_related: false,
        not_work_related_reason: "off_duty_camp",
      },
    });
    expect(res.status(), await res.text()).toBe(201);
    const inc = (await res.json()) as { id: string };
    await addCase(api, inc.id, s.najd);
    await report(api, inc.id);
    await login(page, USERS.noura);
    await page.goto("/en/incidents/excluded");
    await expect(page.getByTestId("excluded-table")).toContainText(/off.duty|camp/i);
  });
});
