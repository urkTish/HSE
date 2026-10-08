import { expect, test } from "./fixtures/test";
import { uid, USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

const HEAD = "worker_no,id_type,id_number,passport_country,project_code,provider_code,examiner_no,assessment_type,examined_on,certificate_no,code,outcome,restrictions,restriction_review_date,unfit_review_date,printed_next_due";

/** Medical settings with hook enablement (§3.12, HK6-1) and medical imports (IM6). */
test.describe("Medical settings and imports", () => {
  test("hooks are on with the medical check card; an out-of-range value is refused, a valid one saved", async ({ page }) => {
    await openAs(page, USERS.faisal, "/medical-settings");
    await expect(page.getByTestId("medical-hooks-state")).toHaveAttribute("data-enabled", "true");
    await expect(page.getByTestId("enable-medical-hooks")).toHaveCount(0);
    await expect(page.getByTestId("hook-kind-medical_fitness")).toBeVisible();
    await page.getByTestId("ms-referral_assessment_hours").fill("200");
    await page.getByTestId("save-medical-settings").click();
    await expect(page.getByTestId("form-error")).toBeVisible();
    await page.getByTestId("ms-referral_assessment_hours").fill("48");
    await page.getByTestId("save-medical-settings").click();
    await expect(page.getByText("1 settings saved.")).toBeVisible();
  });

  test("the HSE Officer sees settings read-only", async ({ page }) => {
    await openAs(page, USERS.noura, "/medical-settings");
    await expect(page.getByTestId("ms-referral_assessment_hours")).toBeDisabled();
    await expect(page.getByTestId("save-medical-settings")).toHaveCount(0);
  });

  test("clinic register import: dry run shows OK and E01, commit creates one record", async ({ page }) => {
    const sfx = uid();
    const rows = [`WKR-000004,,,,ANIA-EXP,SHIFA-ANIA,EXR-0001,periodic,2026-10-01,SH-TEST-E2E-${sfx},GEN-FIT,fit,,,,`, `WKR-999999,,,,ANIA-EXP,SHIFA-ANIA,EXR-0001,periodic,2026-10-01,SH-TEST-E2E-${sfx}-2,GEN-FIT,fit,,,,`];
    await openAs(page, USERS6.huda, "/medical-imports");
    await page.getByTestId("mi-source").selectOption("clinic_register_file");
    const prov = page.getByTestId("mi-provider");
    await prov.selectOption((await prov.locator("option", { hasText: "SHIFA-ANIA" }).first().getAttribute("value")) ?? "");
    await page.getByTestId("mi-file").setInputFiles({ name: `register-${sfx}.csv`, mimeType: "text/csv", buffer: Buffer.from(`${HEAD}\r\n${rows.join("\r\n")}\r\n`, "utf8") });
    await page.getByTestId("mi-check").click();
    await expect(page).toHaveURL(/\/medical-imports\/[0-9a-f-]{36}$/);
    await expect(page.locator('[data-testid="mi-row"][data-row="1"]')).toHaveAttribute("data-status", /ok|warning/);
    await expect(page.locator('[data-testid="mi-row"][data-row="2"]').getByTestId("mi-issue").first()).toHaveAttribute("data-code", "E01");
    await page.getByTestId("mi-commit").click();
    await expect(page.getByTestId("mi-committed")).toContainText("1");
  });
});
