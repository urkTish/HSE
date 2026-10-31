import { expect, test } from "../fixtures/test";
import { uid } from "../helpers";
import { openQ, QU } from "./q0-helpers";

const letters = (s: string) => s.replace(/[0-9]/g, (d) => "ABCDEFGHIJ"[Number(d)] ?? "A");

// Quality checklists on the 6d engine (spec 8-quality Q-CHK-01, Q-CHK-04, Q-NAV-02): author 240, publish 239,
// codes start with Q and may hold digits and hyphens; no stop rule; the default per type is set in Quality settings.

test.describe("Quality Q0 checklists", () => {
  test("QA/QC Manager authors, publishes and sets a quality checklist as the default", async ({ page }) => {
    const code = `QE-${letters(uid()).toUpperCase().slice(0, 5)}`;
    await openQ(page, QU.hatem, "/checklist-templates?kind=quality");
    await page.getByTestId("tpl-new").click();
    await expect(page.getByTestId("nt-kind")).toHaveValue("quality");
    await page.getByTestId("nt-code").fill(code);
    await page.getByTestId("nt-type").selectOption("ir_inspection");
    await page.getByTestId("nt-profiles").selectOption("construction");
    await page.getByTestId("nt-en").fill(`Formwork before concrete ${code}`);
    await page.locator("#nt-ar").fill(`القوالب قبل الصب ${code}`);
    await page.getByTestId("tpl-create").click();
    await expect(page.getByTestId("tpl-detail")).toHaveAttribute("data-status", "draft");

    await page.getByTestId("tpl-add-item").click();
    await expect(page.getByTestId("ti-code")).toHaveValue(`${code}-01`);
    await page.getByTestId("ti-en").fill("Formwork lines and levels within tolerance");
    await page.getByTestId("ti-ar").fill("خطوط ومناسيب القوالب ضمن السماحية");
    await page.getByTestId("ti-critical").check();
    await expect(page.getByTestId("ti-stop").locator('option[value="stop_work"]')).toHaveCount(0);
    await page.getByTestId("item-save").click();
    await expect(page.locator(`[data-testid="tpl-item"][data-code="${code}-01"]`)).toBeVisible();
    await page.getByTestId("tpl-publish").click();
    await page.getByTestId("tpl-publish-confirm").click();
    await expect(page.getByTestId("tpl-detail")).toHaveAttribute("data-status", "published");

    await page.goto("/en/quality/settings");
    await page.getByTestId("q-settings-tab-checklists").click();
    const select = page.getByTestId("q-checklist-default-ir_inspection");
    await select.selectOption(code);
    await page.getByTestId("q-checklist-defaults-save").click();
    await page.reload();
    await page.getByTestId("q-settings-tab-checklists").click();
    await expect(page.getByTestId("q-checklist-default-ir_inspection")).toHaveValue(code);
  });

  test("the QC inspector reads quality checklists but cannot author them", async ({ page }) => {
    await openQ(page, QU.joseph, "/quality");
    await page.getByTestId("nav-quality").getByTestId("nav-q-checklists").click();
    await expect(page).toHaveURL(/\/checklist-templates/);
    await expect(page.getByRole("heading").first()).toBeVisible();
    await expect(page.getByTestId("tpl-new")).toHaveCount(0);
  });
});
