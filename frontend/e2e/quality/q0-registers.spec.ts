import { expect, test } from "../fixtures/test";
import { uid } from "../helpers";
import { openQ, QU } from "./q0-helpers";

// Quality Q0 registers (spec 8-quality Part A §A.3): suppliers, customers, systems, criteria, M&TE.

test.describe("Quality Q0 registers", () => {
  test("M&TE register: create an item; a duplicate serial is refused (AC-Q0-49)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/mte");
    await expect(page.getByTestId("q-mte-row").first()).toBeVisible();
    const serial = `E2E-${uid().slice(0, 8)}`;
    await page.getByTestId("q-mte-new").click();
    await page.getByTestId("mte-type").selectOption("dft_gauge");
    await page.getByTestId("mte-description").fill("Coating thickness gauge");
    await page.getByTestId("mte-manufacturer").fill("Elcometer");
    await page.getByTestId("mte-serial").fill(serial);
    await page.getByTestId("mte-save").click();
    await expect(page.getByTestId("q-mte-detail")).toBeVisible();
    await expect(page.getByRole("heading", { name: /MTE-\d{4}/ })).toBeVisible();

    await page.goto("/en/quality/mte");
    await page.getByTestId("q-mte-new").click();
    await page.getByTestId("mte-type").selectOption("dft_gauge");
    await page.getByTestId("mte-description").fill("Second gauge, same serial");
    await page.getByTestId("mte-manufacturer").fill("Elcometer");
    await page.getByTestId("mte-serial").fill(serial);
    await page.getByTestId("mte-save").click();
    await expect(page.getByTestId("q-mte-form").getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/\/quality\/mte$/);
  });

  test("suppliers register shows status and opens the detail tabs", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/suppliers");
    const gulf = page.locator('[data-testid="q-supplier-row"][data-code="GULFPIPE"]');
    await expect(gulf).toHaveAttribute("data-status", "suspended");
    await page.locator('[data-testid="q-supplier-row"][data-code="LAB-RGM"]').getByRole("link").click();
    await expect(page.getByTestId("q-supplier-detail")).toHaveAttribute("data-status", "approved");
    await page.getByTestId("q-supplier-tab-accreditations").click();
    await expect(page.getByTestId("q-accreditations")).toBeVisible();
  });

  test("customers on the logistics project and systems on construction only", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/customers", { project: "RUH-CCH" });
    await expect(page.getByTestId("q-customer-row").first()).toBeVisible();
    await page.goto("/en/quality/systems");
    await expect(page.getByTestId("q-construction-only")).toBeVisible();
  });

  test("acceptance criteria: draft, publish, evaluate a value (Q-CRT)", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/criteria");
    await page.getByTestId("q-criterion-new").click();
    const code = `E2E-${uid().slice(0, 6).toUpperCase()}`;
    await page.getByTestId("cr-code").fill(code);
    await page.getByTestId("cr-title").fill("Slump 75–125 mm");
    await page.getByTestId("cr-title-ar").fill("الهبوط 75–125 مم");
    await page.getByTestId("cr-kind").selectOption("range");
    await page.getByTestId("cr-min").fill("75");
    await page.getByTestId("cr-max").fill("125");
    await page.getByTestId("cr-save").click();
    await expect(page.getByTestId("q-criterion-detail")).toHaveAttribute("data-status", "draft");
    await page.getByTestId("q-cr-publish").click();
    await expect(page.getByTestId("q-criterion-detail")).toHaveAttribute("data-status", "published");
    await page.getByTestId("cr-value").fill("140");
    await page.getByTestId("cr-evaluate").click();
    await expect(page.getByTestId("cr-verdict")).toHaveAttribute("data-verdict", "fail");
  });
});
