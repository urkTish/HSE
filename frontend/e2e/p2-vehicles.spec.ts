import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";

const VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789";
function vin(): string {
  return Array.from({ length: 17 }, () => VIN_CHARS[Math.floor(Math.random() * VIN_CHARS.length)]).join("");
}

test.describe.serial("Phase 2 — vehicles, AVPs and the sticker", () => {
  const digits = String(Math.floor(1000 + Math.random() * 8999));
  const fleet = `FL-${uid()}`;

  async function fillVehicle(page: Page, fleetNo: string) {
    await page.goto("/en/vehicles/new");
    await selectContaining(page.locator("#vf-eng"), "GULFPAVE");
    await page.locator("#vf-owner").selectOption("company");
    await page.locator("#vf-cat").selectOption("pickup");
    await page.locator("#vf-fleet").fill(fleetNo);
    await page.locator("#vf-make").fill("Toyota Hilux");
    await page.locator("#vf-year").fill("2022");
    await page.locator("#vf-colour").fill("White");
    await page.locator("#vf-vin").fill(vin());
    await page.locator("#vf-plate-type").selectOption("private");
    await page.locator("#vf-plate-ar").fill("ح ط ر");
    await page.locator("#vf-plate-en").fill("HTR");
    await page.locator("#vf-plate-digits").fill(digits);
    await page.locator("#vf-travel").fill("2");
    await page.locator("#vf-working").fill("2");
    await page.locator("#vf-istimara").fill("2027-08-01");
    await page.locator("#vf-mvpi").fill("2027-05-01");
    await page.locator("#vf-ins-no").fill(`POL-${uid()}`);
    await page.locator("#vf-ins-exp").fill("2027-07-01");
    await page.getByTestId("save-vehicle").click();
  }

  test("VP: register a plated vehicle; the plate shows Arabic letters with LTR digits", async ({ page }) => {
    await login(page, USERS.faisal);
    await fillVehicle(page, fleet);
    await expect(page).toHaveURL(/\/vehicles\/[0-9a-f-]{36}$/);
    const plate = page.getByTestId("plate").first();
    await expect(plate).toContainText("ح ط ر");
    await expect(plate).toContainText(digits);
  });

  test("AC40: a second vehicle with the same plate is rejected", async ({ page }) => {
    await login(page, USERS.faisal);
    await fillVehicle(page, `${fleet}-2`);
    await expect(page.getByTestId("form-error")).toBeVisible();
    await expect(page).toHaveURL(/\/vehicles\/new$/);
  });

  test("AC39 / VP: AVP inspection does not offer n.a. for the amber beacon; a clean checklist lets the AVP be issued with a sticker", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto(`/en/vehicles?q=${fleet}`);
    await page.getByTestId("vehicle-row").first().getByRole("link").first().click();
    await page.getByTestId("apply-avp").click();
    await pickMulti(page, "avp-areas", ["Apron"]);
    await page.getByTestId("apply-avp-confirm").click();
    await expect(page).toHaveURL(/\/avps\/[0-9a-f-]{36}$/);

    await page.getByTestId("record-inspection").click();
    await page.locator("#in-date").fill("2026-10-05");
    await page.locator("#in-inspector").fill("Airside Ops inspector");
    await page.locator("#in-result").selectOption("passed");
    const editor = page.getByTestId("checklist-editor");
    for (const sel of await editor.locator("select").all()) await sel.selectOption("pass");
    // AC39: n.a. is not offered for the amber beacon (the API refuses it with AVP_PRECONDITION).
    await expect(page.getByTestId("check-amber_beacon").locator("option[value='n.a.']")).toHaveCount(0);
    await expect(page.getByTestId("check-chequered_flag_or_marking").locator("option[value='n.a.']")).toHaveCount(1);
    await page.getByTestId("save-inspection").click();
    await expect(page.getByTestId("checklist-problems")).toHaveCount(0);
    await page.getByTestId("issue-avp").click();
    await page.locator("#ia-avp-no").fill(`AVP-${uid()}`);
    await page.locator("#ia-sticker").fill(`STK-${uid()}`);
    await page.locator("#ia-avp-until").fill("2027-06-30");
    await page.getByTestId("issue-avp-confirm").click();
    await expect(page.getByTestId("sticker-card")).toBeVisible();
    await expect(page.getByTestId("sticker-ref")).not.toBeEmpty();
    await page.getByTestId("print-sticker").click();
    await expect(page.getByTestId("sticker-print")).toBeVisible();
  });
});
