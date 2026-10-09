import { expect, test } from "./fixtures/test";
import { selectByPrefix, USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Spill log linked to Phase 1 incidents and environmental complaints with complainant privacy (6e §3.13–§3.15, SPL-1…SPL-6, CPL-1…CPL-4, P6e-3). */
test.describe("Spills and complaints", () => {
  test("Fahad reports a 25 L diesel spill on his phone: reportable, an incident is created; Noura cleans up and closes it", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS6.fahad, "/spills/new");
    await selectByPrefix(page.getByTestId("sp-site"), "S-LAND");
    await selectByPrefix(page.getByTestId("sp-engagement"), "RAWABI");
    await page.getByTestId("sp-quantity").fill("25");
    await expect(page.getByTestId("sp-reportable-preview")).toBeVisible();
    await page.getByTestId("sp-contained-yes").click();
    await page.getByTestId("sp-actual").selectOption("2");
    await page.getByTestId("sp-potential").selectOption("3");
    await page.getByTestId("sp-activity").selectOption({ index: 1 });
    await page.getByTestId("sp-description").fill("Excavator hydraulic hose burst near the laydown area; diesel ran onto the paved apron.");
    await page.getByTestId("sp-immediate").fill("Absorbent pads and sand applied, area coned off, hose isolated.");
    await page.getByTestId("sp-save").click();
    await expect(page.getByTestId("spill-reportable")).toBeVisible();
    await expect(page.getByTestId("spill-incident")).toBeVisible();
    // Closing a spill is the HSE team's (210).
    await expect(page.getByTestId("spill-close")).toHaveCount(0);
    const path = new URL(page.url()).pathname.replace(/^\/en/, "");

    await page.setViewportSize({ width: 1280, height: 900 });
    await openAs(page, USERS.noura, path);
    await page.getByTestId("spill-clean").click();
    await page.getByTestId("clean-confirm").click();
    await expect(page.getByTestId("env-status").first()).toHaveAttribute("data-status", "cleaned_up");
    await page.getByTestId("spill-close").click();
    await selectByPrefix(page.getByTestId("cs-area"), "HWS-SLAND-01");
    await page.getByTestId("spill-close-confirm").click();
    await expect(page.getByTestId("env-status").first()).toHaveAttribute("data-status", "closed");
  });

  test("Noura records a phone complaint with the complainant's contact; the viewer sees only that the contact is held", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-complaints/new");
    await expect(page.getByTestId("cp-privacy")).toBeVisible();
    await page.getByTestId("cp-channel").selectOption("phone");
    await page.getByTestId("cp-category").selectOption({ index: 1 });
    await selectByPrefix(page.getByTestId("cp-site"), "S-LAND");
    await page.getByTestId("cp-name").fill("Resident, block 4");
    await page.getByTestId("cp-contact").fill("+966 55 000 1234");
    await page.getByTestId("cp-description").fill("Dust from the site reaches the houses on the north fence every afternoon.");
    await page.getByTestId("cp-save").click();
    await expect(page.getByTestId("complainant-contact")).toContainText("+966 55 000 1234");
    const path = new URL(page.url()).pathname.replace(/^\/en/, "");

    await openAs(page, USERS.sarah, path);
    await expect(page.getByTestId("contact-held")).toBeVisible();
    await expect(page.getByTestId("complainant-contact")).toHaveCount(0);
    await expect(page.getByText("+966 55 000 1234")).toHaveCount(0);
    await expect(page.getByTestId("complaint-respond")).toHaveCount(0);
  });

  test("Arabic: the spill log is right-to-left", async ({ page }) => {
    await openAs(page, USERS.noura, "/spills", "ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("سجل الانسكابات");
    await expect(page.getByTestId("spill-row").first()).toBeVisible();
  });
});
