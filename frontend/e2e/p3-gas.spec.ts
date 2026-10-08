import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";

/** Gas detectors: register, bump test, quarantine on a failed bump test and return to service (§3.x GD rules). */

const today = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Riyadh" });
const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Riyadh" });

async function bump(page: Page, result: "pass" | "fail") {
  await page.getByTestId("record-bump").click();
  const dlg = page.getByRole("dialog");
  await dlg.getByTestId("bump-result").selectOption(result);
  await dlg.locator("#bt-lot").fill("TEST-LOT-E2E");
  await dlg.locator("#bt-exp").fill(inDays(200));
  await dlg.getByTestId("detector-step-confirm").click();
  await expect(dlg).toHaveCount(0);
}

test("register a detector, bump test it, quarantine on a failed bump and return it to service", async ({ page }) => {
  await login(page, USERS.faisal);
  await page.goto("/en/gas-detectors");
  await page.getByTestId("new-detector").click();
  const dlg = page.getByRole("dialog");
  await selectContaining(dlg.locator("#dc-eng"), "RAWABI");
  await dlg.locator("#dc-model").fill("E2E MultiGas 4");
  await dlg.locator("#dc-serial").fill(`SN-${uid()}`);
  await dlg.locator("#dc-cal").fill(inDays(-10));
  await dlg.locator("#dc-cert").fill(`CAL-${uid()}`);
  await dlg.getByTestId("save-detector").click();
  await expect(page).toHaveURL(/\/gas-detectors\/[0-9a-f-]{36}/);
  await expect(page.getByTestId("detector-status")).toHaveAttribute("data-status", "in_service");

  await bump(page, "pass");
  await expect(page.getByTestId("bump-tests").locator("li")).toHaveCount(1);

  await bump(page, "fail");
  await expect(page.getByTestId("detector-status")).toHaveAttribute("data-status", "quarantined");
  await expect(page.getByTestId("detector-detail")).toContainText(/bump test/i);

  // A new calibration and a passing bump test return it to service.
  await page.getByTestId("record-calibration").click();
  const cal = page.getByRole("dialog");
  await cal.locator("#cal-on").fill(today());
  await cal.locator("#cal-cert").fill(`CAL-${uid()}`);
  await cal.getByTestId("detector-step-confirm").click();
  await expect(cal).toHaveCount(0);
  await bump(page, "pass");
  await expect(page.getByTestId("detector-status")).toHaveAttribute("data-status", "in_service");
  await expect(page.getByTestId("bump-tests").locator("li")).toHaveCount(3);
});
