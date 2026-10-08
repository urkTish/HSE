import { expect, test } from "./fixtures/test";
import en from "../messages/en.json" with { type: "json" };
import { apiAs, login, projectId, userId, USERS } from "./helpers";

test.describe("Role scoping visible in the UI", () => {
  test("AC6: Contractor HSE Rep Ahmed sees RAWABI and its subs only", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP");
    await login(page, USERS.ahmed);
    await page.goto(`/en/projects/${ania}/engagements`);
    await expect(page.getByTestId("engagement-row").first()).toBeVisible();
    for (const code of ["RAWABI", "NAJD", "GULFPAVE", "SAHARA"]) await expect(page.locator(`[data-code=${code}]`)).toBeVisible();
    for (const code of ["QIMMA", "DLIFT"]) await expect(page.locator(`[data-code=${code}]`)).toHaveCount(0);
  });

  test("AC7: Yousef (RBT-52) opening ANIA-EXP by ID gets not found", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP");
    await login(page, USERS.yousef);
    await page.goto(`/en/projects/${ania}`);
    await expect(page.getByTestId("not-found")).toBeVisible();
    await expect(page.getByTestId("project-switcher").locator("option")).toHaveText([/^RBT-52/]);
  });

  test("AC8: Permit Receiver Ramesh sees only NAJD in the contractor list", async ({ page }) => {
    await login(page, USERS.ramesh);
    await page.goto("/en/contractors");
    await expect(page.getByTestId("contractor-row")).toHaveCount(1);
    await expect(page.locator("[data-code=NAJD]")).toBeVisible();
    await expect(page.getByTestId("new-contractor")).toHaveCount(0);
  });

  test("AC9: Viewer Sarah gets a read-only UI (no create/edit/status actions)", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP");
    await login(page, USERS.sarah);
    await page.goto("/en/projects");
    await expect(page.getByTestId("project-row")).toHaveCount(2);
    await expect(page.getByTestId("new-project")).toHaveCount(0);
    await page.goto(`/en/projects/${ania}`);
    await expect(page.getByTestId("read-only-badge")).toBeVisible();
    await expect(page.getByTestId("edit-project")).toHaveCount(0);
    await expect(page.locator("[data-testid^=transition-]")).toHaveCount(0);
    await page.goto(`/en/projects/${ania}/sites`);
    await expect(page.getByTestId("site-row").first()).toBeVisible();
    await expect(page.getByTestId("new-site")).toHaveCount(0);
    await page.goto(`/en/projects/${ania}/settings`);
    await expect(page.getByText(en.settings.readOnlyNote)).toBeVisible();
    await expect(page.locator("#ltifr_base_hours")).toBeDisabled();
    await expect(page.getByTestId("nav-users")).toHaveCount(0);
    // Server enforcement behind the hidden buttons.
    const sarah = await apiAs(USERS.sarah);
    const res = await sarah.post(`/api/v1/projects/${ania}/sites`, {
      data: { code: "S-X", name_en: "X", name_ar: "س", site_side: "landside" },
    });
    expect(res.status()).toBe(403);
  });

  test("AC10: Site Engineer Omar (S-AIR only) sees only S-AIR zones", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP");
    await login(page, USERS.omar);
    await page.goto(`/en/projects/${ania}/zones`);
    const sites = page.getByTestId("zone-site");
    // At least the three seeded S-AIR zones (later specs may add S-AIR zones, e.g. p3-config AC1); never another site.
    await expect(sites.first()).toBeVisible();
    const texts = await sites.allInnerTexts();
    expect(texts.length).toBeGreaterThanOrEqual(3);
    expect(new Set(texts.map((x) => x.trim()))).toEqual(new Set(["S-AIR"]));
  });

  test("AC11: Faisal cannot change his own status or roles from the UI", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const me = await userId(api, USERS.faisal);
    await login(page, USERS.faisal);
    await page.goto(`/en/users/${me}`);
    await expect(page.getByTestId("self-note")).toHaveText(en.user.selfNote);
    await expect(page.locator("[data-testid^=transition-]")).toHaveCount(0);
    await expect(page.getByTestId("revoke-role")).toHaveCount(0);
    await expect(page.getByTestId("assign-role")).toHaveCount(0);
    // The server rule stands behind the UI.
    const res = await api.post(`/api/v1/users/${me}/transitions`, { data: { to_status: "deactivated", reason: "test" } });
    expect([403, 409]).toContain(res.status());
  });

  test("AC12: HSE Officer Noura is not offered hse_manager / hse_officer roles", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/users/invite");
    await expect(page.getByTestId("assignment-role").locator("option").nth(1)).toBeAttached();
    const options = await page.getByTestId("assignment-role").locator("option").allTextContents();
    expect(options).not.toContain(en.role.hse_manager);
    expect(options).not.toContain(en.role.hse_officer);
    expect(options).toContain(en.role.site_engineer);
  });

  test("AC31: Noura's audit log shows ANIA-EXP entries only, without IP", async ({ page }) => {
    // Produce at least one ANIA-EXP entry.
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP");
    await api.get(`/api/v1/exports/sites?format=csv&project_id=${ania}`);
    await login(page, USERS.noura);
    await page.goto("/en/audit-log");
    await expect(page.getByTestId("audit-row").first()).toBeVisible();
    const projects = await page.getByTestId("audit-project").allTextContents();
    for (const p of projects) expect(["ANIA-EXP", "—"]).toContain(p.trim());
    expect(projects).toContain("ANIA-EXP");
    await expect(page.getByTestId("ip-column")).toHaveCount(0);
    await expect(page.getByTestId("verify-chain")).toHaveCount(0);
    // Viewing is itself logged.
    await page.locator("#audit-action").selectOption("audit_log_viewed");
    await expect(page.getByTestId("audit-row").first()).toBeVisible();
  });
});
