import { expect, test, type Page } from "@playwright/test";
import en from "../messages/en.json" with { type: "json" };
import { apiAs, login, projectId, uid, USERS } from "./helpers";

const code = `E2E-${uid()}`;
let projectUrl = "";

async function createSite(page: Page, siteCode: string, side: string) {
  await page.goto(`${projectUrl}/sites/new`);
  await page.locator("#code").fill(siteCode);
  await page.locator("#site_side").selectOption(side);
  await page.locator("#name_en").fill(`Site ${siteCode}`);
  await page.locator("#name_ar").fill("موقع اختبار");
  await page.getByTestId("save").click();
  await expect(page.getByTestId("site-title")).toHaveText(`Site ${siteCode}`);
}

test.describe.serial("Projects, sites, zones and settings", () => {
  test("Create an airport project (validation, ICAO required)", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/projects");
    await page.getByTestId("new-project").click();
    await page.locator("#code").fill(code);
    await page.locator("#project_type").selectOption("airport");
    await page.locator("#name_en").fill(`E2E Airport ${code}`);
    await page.locator("#name_ar").fill("Not Arabic");
    await page.locator("#client_name_en").fill("E2E Client (fictional)");
    await page.locator("#client_name_ar").fill("عميل تجريبي");
    await page.locator("#city").fill("Jeddah");
    await page.locator("#start_date").fill("2026-01-01");
    await page.locator("#planned_end_date").fill("2025-01-01");
    await page.getByTestId("save").click();
    await expect(page.locator("#name_ar-error")).toHaveText(en.validation.arabicRequired);
    await expect(page.locator("#airport_icao-error")).toHaveText(en.validation.icaoRequired);
    await expect(page.locator("#planned_end_date-error")).toHaveText(en.validation.endBeforeStart);
    await page.locator("#name_ar").fill("مطار الاختبار");
    await page.locator("#airport_icao").fill("OEYY");
    await page.locator("#planned_end_date").fill("2027-12-31");
    await page.getByTestId("save").click();
    await expect(page.getByTestId("project-title")).toHaveText(`E2E Airport ${code}`);
    await expect(page.locator("[data-status=planning]")).toBeVisible();
    projectUrl = new URL(page.url()).pathname;
  });

  test("Create sites and an airside zone with its attributes", async ({ page }) => {
    await login(page, USERS.faisal);
    await createSite(page, "S-AIR", "airside");
    await page.getByTestId("new-zone").click();
    // Airside site → only airside zones are offered.
    await expect(page.locator("#zone_type option")).toHaveText([en.zone.type.airside]);
    await page.locator("#code").fill("Z-TWY-A");
    await page.locator("#name_en").fill("Taxiway A Strip");
    await page.locator("#name_ar").fill("شريط الممر A");
    await page.locator("#airside-area").selectOption("taxiway_strip");
    await expect(page.locator("#airside-in_movement_area")).toBeChecked();
    // AC15: taxiway_strip outside the movement area is rejected.
    await page.locator("#airside-in_movement_area").uncheck();
    await page.getByTestId("save").click();
    await expect(page.getByText(en.validation.movementArea)).toBeVisible();
    await page.locator("#airside-in_movement_area").check();
    await page.locator("#airside-runway_ref").fill("15L/33R");
    await page.locator("#airside-ols").fill("642.5");
    await page.locator("#airside-maxh").fill("6");
    await page.locator("#airside-escort_required").check();
    await page.locator("#airside-adp_required").check();
    await page.getByTestId("save").click();
    await expect(page.getByTestId("zone-title")).toHaveText("Taxiway A Strip");
    const card = page.getByTestId("airside-card");
    await expect(card).toContainText(en.zone.area.taxiway_strip);
    await expect(card).toContainText("15L/33R");
    await expect(card).toContainText("642.5");
    // Edit an airside attribute → audited and visible in the change history (rule 21).
    await page.getByTestId("edit-zone").click();
    await page.locator("#airside-maxh").fill("4");
    await page.getByTestId("save").click();
    await expect(page.getByTestId("airside-card")).toContainText("4");
    await expect(page.getByTestId("history-entry").first()).toContainText(en.audit.action.update);
  });

  test("AC14: a non-airport project offers only zone type 'other'", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const rbt = await projectId(api, "RBT-52");
    await login(page, USERS.faisal);
    await page.goto(`/en/projects/${rbt}/sites`);
    await page.getByTestId("site-row").first().getByRole("link").click();
    await page.getByTestId("new-zone").click();
    await expect(page.locator("#zone_type option")).toHaveText([en.zone.type.other]);
    await expect(page.getByText(en.zone.typeHintNonAirport)).toBeVisible();
    // The server rejects it too.
    const sites = await (await api.get(`/api/v1/projects/${rbt}/sites`)).json();
    const res = await api.post(`/api/v1/sites/${sites.items[0].id}/zones`, {
      data: { code: "Z-BAD", name_en: "Bad", name_ar: "سيئ", zone_type: "airside", airside: null },
    });
    expect(res.status()).toBe(422);
  });

  test("AC23/24: KPI base change updates the label, is audited; 500,000 is not offered", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto(`${projectUrl}/settings`);
    await expect(page.locator("#ltifr_base_hours option")).toHaveText(["200,000 h", "1,000,000 h"]);
    await expect(page.getByTestId("ltifr-label")).toContainText("1,000,000");
    await page.locator("#ltifr_base_hours").selectOption("200000");
    await page.getByTestId("save-settings").click();
    await expect(page.getByTestId("ltifr-label")).toContainText("per 200,000 h");
    await expect(page.getByTestId("history-entry").first()).toContainText(en.audit.action.settings_changed);
    await expect(page.getByTestId("history-entry").first()).toContainText("ltifr_base_hours");
    const api = await apiAs(USERS.faisal);
    const pid = projectUrl.split("/").pop() ?? "";
    const bad = await api.patch(`/api/v1/projects/${pid}/settings`, { data: { ltifr_base_hours: 500000 } });
    expect(bad.status()).toBe(422);
  });

  test("Project workflow: activate, close (reason required); AC22 closed project rejects zone edits", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto(projectUrl);
    await page.getByTestId("transition-active").click();
    await page.getByTestId("transition-confirm").click();
    await expect(page.locator("[data-status=active]")).toBeVisible();
    await page.getByTestId("transition-closed").click();
    await page.getByTestId("transition-confirm").click();
    await expect(page.getByText(en.transitions.reasonRequired)).toBeVisible();
    await page.locator("#transition-reason").fill("E2E test closure");
    await page.getByTestId("transition-confirm").click();
    await expect(page.getByTestId("closed-banner")).toBeVisible();
    await expect(page.getByTestId("edit-project")).toHaveCount(0);

    await page.goto(`${projectUrl}/zones`);
    await page.getByTestId("zone-row").first().getByRole("link").click();
    await page.waitForURL(/\/zones\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("zone-title")).toBeVisible();
    await expect(page.getByTestId("edit-zone")).toHaveCount(0);
    await page.goto(`${new URL(page.url()).pathname}/edit`);
    await page.locator("#name_en").fill("Edited while closed");
    await page.getByTestId("save").click();
    await expect(page.getByTestId("form-error")).toHaveText(en.errors.code.PROJECT_CLOSED);
  });

  test("Project switcher and EN/AR shell switch keep the page", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/projects");
    await page.getByTestId("language-switch").click();
    await expect(page).toHaveURL(/\/ar\/projects$/);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "المشاريع" })).toBeVisible();
    await page.getByTestId("language-switch").click();
    await expect(page).toHaveURL(/\/en\/projects$/);
    const api = await apiAs(USERS.faisal);
    const rbt = await projectId(api, "RBT-52");
    await page.getByTestId("project-switcher").selectOption(rbt);
    await expect(page.getByTestId("nav-sites")).toHaveAttribute("href", `/en/projects/${rbt}/sites`);
  });

  test("AC25: a UTC timestamp is displayed in Asia/Riyadh", async ({ page }) => {
    await login(page, USERS.faisal);
    const api = await apiAs(USERS.faisal);
    const rbt = await projectId(api, "RBT-52");
    await page.getByTestId("project-switcher").selectOption(rbt); // RBT-52: Hijri off
    await page.route("**/api/v1/audit-log?**", async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      body.items = body.items.slice(0, 1).map((e: Record<string, unknown>) => ({ ...e, occurred_at: "2026-10-04T22:30:00Z" }));
      await route.fulfill({ response: res, json: body });
    });
    await page.goto("/en/audit-log");
    await expect(page.getByTestId("audit-time").first()).toHaveText("05 Oct 2026 01:30");
  });

  test("AC26: with show_hijri the Umm al-Qura date from ICU is shown beside the Gregorian date", async ({ page }) => {
    await page.clock.setFixedTime(new Date("2026-10-05T09:00:00Z"));
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP"); // seeded with Hijri on
    await login(page, USERS.faisal);
    await page.goto(`/en/projects/${ania}/settings`);
    await expect(page.locator("#show_hijri")).toBeChecked();
    const expected = await page.evaluate(() =>
      new Intl.DateTimeFormat("en-GB-u-ca-islamic-umalqura-nu-latn", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(
        new Date("2026-10-05T12:00:00Z"),
      ),
    );
    await expect(page.getByTestId("date-preview")).toHaveText(`05 Oct 2026 · ${expected}`);
  });
});
