import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";

const riyadhDay = (n: number) => new Date(Date.now() + n * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Riyadh" });

async function draft(page: Page, title: string) {
  await page.goto("/en/permits/new");
  const f = page.getByTestId("permit-form");
  await selectContaining(f.getByTestId("pf-site"), "S-LAND");
  await pickMulti(page, "pf-zones", [/Z-LAY1/]);
  await f.getByTestId("pf-location").fill("Grid line C, level 1");
  await selectContaining(f.getByTestId("pf-engagement"), "NAJD");
  await f.getByTestId("pf-title").fill(title);
  await page.getByRole("group", { name: /work types/i }).getByLabel("General / cold work", { exact: true }).check();
  await f.getByTestId("pf-scope").fill("Install temporary barriers and signage for the e2e run.");
  await f.getByTestId("pf-from").fill(`${riyadhDay(1)}T07:00`);
  await f.getByTestId("pf-to").fill(`${riyadhDay(1)}T17:00`);
  await f.getByTestId("pf-emergency").fill("Call 997; assembly point AP-3; first aider on site.");
}

/** Phase 3 permit changes for heat (6b §11.4): heat workload and clothing on the request, shown on the detail. */
test("a receiver sets heat workload and clothing on an outdoor permit; indoor hides them", async ({ page }) => {
  await login(page, USERS.ramesh);
  await draft(page, `E2E heat ${uid()}`);
  const f = page.getByTestId("permit-form");
  await f.locator("#pf-exposure").selectOption("indoor");
  await expect(f.getByTestId("pf-heat-workload")).toHaveCount(0);
  await f.locator("#pf-exposure").selectOption("outdoor_direct_sun");
  await f.getByTestId("pf-heat-workload").selectOption("heavy");
  await f.getByTestId("pf-heat-clothing").selectOption("double_layer_woven");
  await page.getByTestId("save-permit").click();
  await expect(page).toHaveURL(/\/permits\/[0-9a-f-]{36}/);
  await expect(page.getByTestId("permit-heat-workload")).toContainText(/heavy/i);
  await expect(page.getByTestId("permit-heat-workload")).toHaveAttribute("data-clothing", "double_layer_woven");
});
