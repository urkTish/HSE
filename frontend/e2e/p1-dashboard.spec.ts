import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";

// Seed covers 2025-09 … 2026-09 (spec Appendix A); September 2026 reproduces W1/W3.
const SEP = "period=month&anchor=2026-09-15";

interface Tile {
  metric: string;
  display: string;
  label_ar: string;
  short_label_ar: string;
}
interface Dash {
  lagging: Tile[];
  leading: Tile[];
  context: {
    filters: {
      scope_narrowed: boolean;
      effective_engagement_ids: string[] | null;
    };
    bases: { mixed_projects: boolean };
  };
}

const SEED_NAMES = [
  "Imran Hussain",
  "Rajesh Nair",
  "Abdul Karim Mia",
  "Mahmoud Fathy",
  "Jomar Santos",
  "Suman Tamang",
  "Saad Al-Dosari",
  "Waleed Saleh",
  "Osman Idris",
  "عمران حسين",
];

test.describe("Dashboard", () => {
  test("AC63: every tile shows the backend display string as given (no client recomputation)", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    const d = await getJson<Dash>(api, `/api/v1/kpi/dashboard?project_id=${ania}&${SEP}`);
    await login(page, USERS.noura);
    await page.goto(`/en?${SEP}`);
    await expect(page.getByTestId("lagging-tiles")).toBeVisible();
    for (const tile of [...d.lagging, ...d.leading]) {
      await expect(page.locator(`[data-testid=kpi-tile][data-metric="${tile.metric}"]`).getByTestId("tile-value")).toHaveText(tile.display);
    }
    await expect(page.getByTestId("headline")).toBeVisible();
    await expect(page.getByTestId("period-label")).toHaveText("Sep 2026");
  });

  test("Filters live in the URL and survive a reload; drill-down opens the source records", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto(`/en?${SEP}`);
    await page.getByTestId("filter-period").selectOption("r12");
    await expect(page).toHaveURL(/period=r12/);
    await page.reload();
    await expect(page.getByTestId("filter-period")).toHaveValue("r12");
    await page.getByTestId("filter-period").selectOption("month");
    await page.goto(`/en?${SEP}`);
    await page.locator("[data-testid=kpi-tile][data-metric='K-06']").getByTestId("drill-K-06").click();
    const dlg = page.getByTestId("drill-dialog");
    await expect(dlg).toBeVisible();
    // The drill request queues behind the dashboard's first KPI requests (CPU-bound backend, heavier Phase 2 seed).
    await expect(dlg.getByTestId("drill-source").first()).toBeVisible({ timeout: 30_000 });
    await dlg.getByTestId("drill-source").first().locator("a").click();
    await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]{36}|\/injury-cases\/[0-9a-f-]{36}/);
  });

  test("Charts C1–C9, pyramid and league table render with a table view", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto(`/en?${SEP}`);
    for (const id of ["C1", "C2", "C3", "C5", "C7", "C8", "C9"]) await expect(page.getByTestId(`chart-${id}`)).toBeVisible();
    await page.getByTestId("chart-C1").getByTestId("chart-toggle-table").click();
    await expect(page.getByTestId("chart-C1").getByTestId("chart-table")).toBeVisible();
    await expect(page.getByTestId("pyramid-layer").first()).toBeVisible();
    await expect(page.getByTestId("league-row").first()).toBeVisible();
    await page.getByTestId("c7-dimension").selectOption("body_part");
    await expect(page).toHaveURL(/c7d=body_part/);
  });

  test("AC64: overdue CA count equals K-42 and opens the filtered CA list", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    const d = await getJson<Dash>(api, `/api/v1/kpi/dashboard?project_id=${ania}`);
    const k42 = d.leading.find((t) => t.metric === "K-42");
    expect(k42).toBeDefined();
    await login(page, USERS.noura);
    await page.goto("/en");
    const item = page.locator("[data-testid=action-item][data-key=overdue_cas]");
    await expect(item.getByTestId("action-count")).toHaveText(k42?.display ?? "");
    await item.locator("a").first().click();
    await expect(page).toHaveURL(/\/actions\?/);
    await expect(page.getByTestId("ca-table")).toBeVisible();
  });

  test("AC62: Arabic dashboard is mirrored with Arabic labels", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    const d = await getJson<Dash>(api, `/api/v1/kpi/dashboard?project_id=${ania}&${SEP}`);
    await login(page, USERS.noura, "ar");
    await page.goto(`/ar?${SEP}`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const first = d.lagging[0];
    await expect(page.locator(`[data-testid=kpi-tile][data-metric="${first?.metric}"]`)).toContainText(first?.short_label_ar || first?.label_ar || "");
    await expect(page.getByTestId("chart-C1")).toContainText(/[؀-ۿ]/);
  });

  test("AC61: Viewer Sarah gets no sensitive breakdowns and no person names", async ({ page }) => {
    await login(page, USERS.sarah);
    await page.goto(`/en?${SEP}`);
    await expect(page.getByTestId("lagging-tiles")).toBeVisible();
    const dims = await page
      .getByTestId("c7-dimension")
      .locator("option")
      .evaluateAll((o) => o.map((x) => (x as HTMLOptionElement).value));
    expect(dims).not.toContain("nationality");
    expect(dims).not.toContain("age_band");
    await expect(page.getByTestId("league-row").first()).toBeVisible();
    const text = await page.locator("main").innerText();
    for (const n of SEED_NAMES) expect(text).not.toContain(n);
  });

  test("AC59: Yousef sees RBT-52 only, figures scoped to QIMMA + subs", async ({ page }) => {
    const api = await apiAs(USERS.yousef);
    const rbt = await projectId(api, "RBT-52");
    const d = await getJson<Dash>(api, `/api/v1/kpi/dashboard?project_id=${rbt}&${SEP}`);
    await login(page, USERS.yousef);
    await page.goto(`/en?${SEP}`);
    await expect(page.getByTestId("project-switcher").locator("option")).toHaveText([/^RBT-52/]);
    const tile = d.lagging.find((t) => t.metric === "K-10");
    await expect(page.locator("[data-testid=kpi-tile][data-metric='K-10']").getByTestId("tile-value")).toHaveText(tile?.display ?? "");
    if (d.context.filters.scope_narrowed) await expect(page.getByTestId("banner-scope")).toBeVisible();
  });

  test("AC55: All projects shows the mixed-bases banner", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto(`/en?${SEP}`);
    await page.getByTestId("filter-all-projects").click();
    await expect(page).toHaveURL(/all=1/);
    await expect(page.locator("[data-testid=dashboard-banner][data-code=MIXED_BASES], [data-testid=banner-mixed]").first()).toBeVisible();
  });

  test("Mobile (390 px, Arabic): no horizontal page scroll", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, USERS.noura, "ar");
    await page.goto(`/ar?${SEP}`);
    await expect(page.getByTestId("lagging-tiles")).toBeVisible();
    await expect(page.getByTestId("chart-C1")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("AC60: Permit Receiver Ramesh sees NAJD-only values", async ({ page }) => {
    const api = await apiAs(USERS.ramesh);
    const ania = await projectId(api, "ANIA-EXP");
    const d = await getJson<Dash>(api, `/api/v1/kpi/dashboard?project_id=${ania}&${SEP}`);
    // Role scope (D-3): only NAJD's engagement is counted.
    expect(d.context.filters.effective_engagement_ids).toHaveLength(1);
    await login(page, USERS.ramesh);
    await page.goto(`/en?${SEP}`);
    await expect(page.getByTestId("banner-scope")).toBeVisible();
    for (const tile of d.lagging.slice(0, 6)) {
      await expect(page.locator(`[data-testid=kpi-tile][data-metric="${tile.metric}"]`).getByTestId("tile-value")).toHaveText(tile.display);
    }
  });
});
