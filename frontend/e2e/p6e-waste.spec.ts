import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, selectByPrefix, USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

type Area = { id: string; area_code: string };
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function areaId(code: string): Promise<string> {
  const api = await apiAs(USERS.noura);
  const pid = await projectId(api, "ANIA-EXP");
  const list = await getJson<{ items: Area[] }>(api, `/api/v1/projects/${pid}/waste-storage-areas?page_size=100`);
  const a = list.items.find((x) => x.area_code === code);
  expect(a, code).toBeTruthy();
  return a?.id ?? "";
}

/** Waste storage areas, consignments and the licence check at dispatch (6e §3.5–§3.6, WST-1…WST-9; 205–207). */
test.describe("Waste", () => {
  test("Fahad checks HWS-SLAND-01 on his phone: 12 days left on the chemical containers", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const id = await areaId("HWS-SLAND-01");
    await openAs(page, USERS6.fahad, `/waste-areas/${id}`);
    await expect(page.getByTestId("haz-deadlines")).toContainText("12 days left");
    await expect(page.getByTestId("area-check")).toBeVisible();
    await page.getByTestId("check-covered-yes").click();
    await page.getByTestId("check-lidded_secured-yes").click();
    await page.getByTestId("check-signage_bilingual-yes").click();
    await page.getByTestId("check-save").click();
    await expect(page.getByText("Check saved")).toBeVisible();
  });

  test("dispatch is refused without a licence covering the class; with HAZMOVE and OILREF it goes, then receipt and close", async ({ page }) => {
    const id = await areaId("HWS-SLAND-01");
    await openAs(page, USERS.noura, `/waste-consignments/new?area=${id}`);
    await page.getByTestId("cn-stream").selectOption("used_oil");
    await page.getByTestId("cn-area").selectOption(id);
    await selectByPrefix(page.getByTestId("cn-generator"), "RAWABI");
    await page.getByTestId("cn-quantity").fill("0.4");
    // GREENHAUL is licensed for inert and non-hazardous only.
    await selectByPrefix(page.getByTestId("cn-transporter"), "GREENHAUL");
    await selectByPrefix(page.getByTestId("cn-facility"), "OILREF");
    await page.getByTestId("cn-plate").fill("4821 RSA");
    await page.getByTestId("cn-manifest").fill("MWAN-2026-55120");
    await page.getByTestId("cn-save").click();
    await expect(page.getByRole("alert").filter({ hasText: /licence/i }).first()).toBeVisible();
    await expect(page.getByTestId("consignment-saved")).toHaveCount(0);

    await selectByPrefix(page.getByTestId("cn-transporter"), "HAZMOVE");
    await page.getByTestId("cn-save").click();
    await expect(page.getByTestId("env-status").first()).toHaveAttribute("data-status", "dispatched");
    const url = new URL(page.url()).pathname.replace(/^\/en/, "");

    await page.getByTestId("consignment-receipt").click();
    await page.getByTestId("rc-net").fill("0.41");
    await page.getByTestId("rc-ticket").fill("WB-77812");
    await page.getByTestId("rc-file").setInputFiles({ name: "ticket.png", mimeType: "image/png", buffer: PNG });
    await page.getByTestId("receipt-save").click();
    await expect(page.getByTestId("env-status").first()).toHaveAttribute("data-status", "received");
    await expect(page.getByTestId("received-net")).toContainText("0.41");
    await page.getByTestId("consignment-close").click();
    await page.getByTestId("close-confirm").click();
    await expect(page.getByTestId("env-status").first()).toHaveAttribute("data-status", "closed");

    // The viewer sees the record without the plate or the driver (P6e-2).
    await openAs(page, USERS.sarah, url);
    await expect(page.getByTestId("driver-hidden")).toBeVisible();
    await expect(page.getByText("4821 RSA")).toHaveCount(0);
    await expect(page.getByTestId("consignment-close")).toHaveCount(0);
  });

  test("Arabic: the consignment register and the waste streams are right-to-left", async ({ page }) => {
    await openAs(page, USERS.noura, "/waste-consignments", "ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("شحنات النفايات");
    await expect(page.getByTestId("consignment-row").first()).toBeVisible();
    await page.goto("/ar/waste-streams");
    await expect(page.getByTestId("stream-row").first()).toBeVisible();
  });
});
