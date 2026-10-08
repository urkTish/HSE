import { type Locator } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, selectByPrefix, uid, USERS } from "./helpers";

/** Pick the first non-empty option of a <select>. */
async function pickFirst(select: Locator) {
  await expect(select.locator("option").nth(1)).toBeAttached();
  const v = await select.evaluate((el) => Array.from((el as HTMLSelectElement).options).find((o) => o.value)?.value ?? "");
  await select.selectOption(v);
}

test.describe("Observations, inspections, meetings, settings, reports", () => {
  test("Observation: create an unsafe observation and close it", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/observations/new");
    await page.locator("#observed_at").fill("2026-10-05T09:00");
    await selectByPrefix(page.locator("#site_id"), "S-LAND");
    await selectByPrefix(page.locator("#observed_engagement_id"), "NAJD");
    await page.locator("#obs_type").selectOption("unsafe_condition");
    await pickFirst(page.locator("#category"));
    await page.locator("#risk_rating").selectOption("medium");
    const text = `E2E open edge near stair core ${uid()}`;
    await page.locator("#description").fill(text);
    await page.locator("#immediate_action").fill("Area barricaded and supervisor informed.");
    await page.getByTestId("save-observation").click();
    await expect(page.getByTestId("observation-title")).toBeVisible();
    await expect(page).toHaveURL(/\/observations\/[0-9a-f-]{36}$/);
    await page.getByTestId("close-observation").click();
    await page.locator("#close-comment").fill("Edge protection installed.");
    await page.getByTestId("close-confirm").click();
    await expect(page.getByTestId("close-observation")).toHaveCount(0);
  });

  test("AC35: an anonymous observer is hidden from the HSE Officer and shown to the HSE Manager", async ({ page }) => {
    const ahmed = await apiAs(USERS.ahmed);
    const ania = await projectId(ahmed, "ANIA-EXP");
    const sites = await getJson<{ items: { id: string; code: string }[] }>(ahmed, `/api/v1/projects/${ania}/sites?page_size=100`);
    const engs = await getJson<{
      items: { id: string; contractor: { short_code: string } }[];
    }>(ahmed, `/api/v1/projects/${ania}/engagements?page_size=100`);
    const res = await ahmed.post(`/api/v1/projects/${ania}/observations`, {
      data: {
        site_id: sites.items.find((s) => s.code === "S-AIR")?.id,
        observed_at: "2026-10-05T06:00:00Z",
        anonymous: true,
        observed_engagement_id: engs.items.find((e) => e.contractor.short_code === "RAWABI")?.id,
        obs_type: "safe_behaviour",
        category: "ppe",
        description: "Crew wearing full PPE at the apron edge.",
      },
    });
    expect(res.status(), await res.text()).toBe(201);
    const obs = (await res.json()) as { id: string };
    await login(page, USERS.noura);
    await page.goto(`/en/observations/${obs.id}`);
    await expect(page.getByTestId("observation-title")).toBeVisible();
    await expect(page.getByTestId("observer")).not.toContainText("Ahmed");
    await page.context().clearCookies();
    await login(page, USERS.faisal);
    await page.goto(`/en/observations/${obs.id}`);
    await expect(page.getByTestId("observer")).toContainText("Ahmed");
  });

  test("Inspection plan and an unplanned inspection with results", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/inspection-plans/new");
    const name = `E2E weekly scaffold ${uid()}`;
    await page.locator("#name_en").fill(name);
    await page.locator("#name_ar").fill("تفتيش السقالات الأسبوعي");
    await page.locator("#inspection_type").selectOption("scaffold");
    await selectByPrefix(page.locator("#site_id"), "S-AIR");
    await page.locator("#frequency").selectOption("weekly");
    await page.locator("#weekday").selectOption({ index: 1 });
    await page.locator("#start_date").fill("2026-10-10");
    await page.locator("#assignee_role").selectOption("hse_officer");
    await page.getByTestId("save-plan").click();
    await expect(page.getByTestId("plan-title")).toContainText(name);

    await page.goto("/en/inspections/new");
    await page.locator("#un-type").selectOption("housekeeping");
    await selectByPrefix(page.locator("#un-site"), "S-LAND");
    await page.locator("#ins-completed").fill("2026-10-05T10:00");
    await page.locator("#ins-checked").fill("20");
    await page.locator("#ins-compliant").fill("18");
    await page.getByTestId("save-inspection").click();
    await expect(page.getByTestId("inspection-title")).toBeVisible();
    await expect(page).toHaveURL(/\/inspections\/[0-9a-f-]{36}$/);
  });

  test("HSE meeting: plan one from the list", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/meetings");
    await page.getByTestId("new-meeting").click();
    const title = `E2E committee ${uid()}`;
    await page.locator("#mt-title").fill(title);
    await page.locator("#mt-planned").fill("2026-10-20");
    await page.locator("#mt-invited").fill("12");
    await page.getByTestId("save-meeting").click();
    await expect(
      page
        .getByTestId("meeting-title")
        .or(page.getByTestId("meeting-row").filter({ hasText: title }))
        .first(),
    ).toBeVisible();
  });

  test("HSE settings: a target is saved; the AI section shows the effective state", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/hse-settings");
    await expect(page.getByTestId("hse-settings")).toBeVisible();
    await expect(page.getByTestId("ai-effective")).toBeVisible();
    const target = page.getByTestId("targets-table").locator("input").first();
    await target.fill("0.75");
    await page.getByTestId("save-settings").click();
    await page.reload();
    await expect(page.getByTestId("targets-table").locator("input").first()).toHaveValue(/0\.75/);
  });

  test("Monthly reports: list loads; drafting is offered only when AI is enabled and available", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    await login(page, USERS.noura);
    await page.goto("/en/reports");
    await expect(page.getByRole("heading", { name: "Monthly HSE reports" })).toBeVisible();
    const st = await api.get(`/api/v1/ai/status?project_id=${ania}`);
    if (st.ok()) {
      const s = (await st.json()) as { enabled: boolean; available: boolean };
      if (!(s.enabled && s.available)) {
        await expect(page.getByTestId("generate-report")).toBeDisabled();
        await expect(page.getByTestId("report-ai-off")).toBeVisible();
      }
    }
  });
});
