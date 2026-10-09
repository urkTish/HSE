import { expect, test } from "./fixtures/test";
import { sql, USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

/** Field overview (band, action panel), KPIs K-110…K-117, settings and the Phase 1 inspection additions (6d §8, §3.14, §11.2). */
test.describe("Field overview, KPIs and settings", () => {
  test("the overview shows the live band and the action panel", async ({ page }) => {
    await openAs(page, USERS.noura, "/field-overview");
    await expect(page.getByTestId("band-tile")).toHaveCount(5);
    await expect(page.locator('[data-testid="band-tile"][data-kind="stop_work_active"] [data-testid="band-value"]')).toHaveText(/^\d+$/);
    await expect(page.getByTestId("field-actions").or(page.getByText("Nothing needs action."))).toBeVisible();
    await expect(page.getByTestId("nav-field")).toBeVisible();
  });

  test("KPIs: September tiles and notes, in Arabic too; the viewer sees aggregates", async ({ page }) => {
    await openAs(page, USERS.sarah, "/field-kpis?period=month&anchor=2026-09-15");
    for (const k of ["K-110", "K-113", "K-114", "K-116"]) await expect(page.locator(`[data-testid="fk-tile"][data-metric="${k}"]`)).toBeVisible();
    await expect(page.locator('[data-testid="fk-tile"][data-metric="K-116"] [data-testid="fk-value"]')).toHaveText(/^\d+(\.\d)? %$/);
    await expect(page.getByTestId("fk-note").first()).toContainText("K-36 source");
    await expect(page.getByTestId("fk-row").first()).toBeVisible();

    await page.goto("/ar/field-kpis?period=month&anchor=2026-09-15");
    await expect(page.getByTestId("fk-note").first()).toContainText("مصدر K-36");
  });

  test("settings: a looser pass mark is refused for Faisal; Noura reads only", async ({ page }) => {
    await openAs(page, USERS.faisal, "/field-settings");
    await page.getByTestId("fs-inspection_pass_mark_pct").fill("80.0");
    await page.getByTestId("fs-save").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "SETTING_LOOSENING");
    await page.getByTestId("fs-inspection_pass_mark_pct").fill("90.0");
    await page.getByTestId("fs-save").click();
    await expect(page.getByTestId("form-error")).toHaveCount(0);
    await expect(page.getByTestId("fs-inspection_pass_mark_pct")).toHaveValue("90.0");

    await openAs(page, USERS.noura, "/field-settings");
    await expect(page.getByTestId("settings-readonly")).toBeVisible();
    await expect(page.getByTestId("fs-save")).toHaveCount(0);
  });

  test("Phase 1: the inspection shows its checklist, score and findings; plans pick a template", async ({ page }) => {
    const id = sql(
      "SELECT i.id FROM inspections i JOIN projects p ON p.id = i.project_id JOIN field_findings f ON f.response_id = i.response_id WHERE p.code = 'ANIA-EXP' ORDER BY i.ref LIMIT 1",
    );
    expect(id).toMatch(/^[0-9a-f-]{36}$/);
    await openAs(page, USERS.noura, `/inspections/${id}`);
    await expect(page.getByTestId("response-card")).toBeVisible();
    await expect(page.getByTestId("response-template")).toContainText("GSI");
    await expect(page.getByTestId("response-score")).toBeVisible();
    await expect(page.getByTestId("fd-finding").first()).toBeVisible();

    await page.goto("/en/inspection-plans/new");
    await page.locator("#inspection_type").selectOption("general_site");
    await expect(page.getByTestId("plan-template").locator("option", { hasText: "GSI" })).toHaveCount(1);
    await page.getByTestId("plan-rotation").selectOption("zones");
    await expect(page.locator("button#rotation_list")).toBeVisible();
  });
});
