import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

/** Real emergency events: declare → all clear → review (6c §3.7, EV-1…EV-7). */
test.describe("Emergency events", () => {
  test("EMV-ANIA-EXP-2026-004 shows its response times and incident link; Sarah cannot declare", async ({ page }) => {
    await openAs(page, USERS.noura, "/emergency-events");
    const row = page.locator('[data-testid="event-row"][data-no="EMV-ANIA-EXP-2026-004"]');
    await expect(row).toHaveAttribute("data-status", "reviewed");
    await row.getByRole("link").click();
    await expect(page.getByTestId("time-first")).toContainText("3.0");
    await expect(page.getByTestId("time-total")).toContainText("28.0");
    await expect(page.getByTestId("event-incident")).toContainText("INC-ANIA-EXP-2026-");
    await expect(page.getByTestId("event-review")).toBeVisible();

    await page.context().clearCookies();
    await openAs(page, USERS.sarah, "/emergency-events");
    await expect(page.getByTestId("event-row").first()).toBeVisible();
    await expect(page.getByTestId("event-declare")).toHaveCount(0);
  });

  test("Omar declares a false alarm from the board and gives the all clear; Noura reviews it", async ({ page }) => {
    await openAs(page, USERS.omar, "/emergency-board");
    await page.getByTestId("board-declare").click();
    await expect(page).toHaveURL(/\/emergency-events\?declare=1/);
    await page.getByTestId("ed-type").selectOption("false_alarm");
    await page.getByTestId("ed-response").selectOption("local_response");
    await selectContaining(page.getByTestId("ed-site"), "S-AIR");
    await pickMulti(page, "ed-zones", [/Z-APR-21/]);
    await page.getByTestId("ed-location").fill("Call point at the batching plant gate");
    await page.getByTestId("declare-confirm").click();
    await expect(page).toHaveURL(/\/emergency-events\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("event-status")).toHaveAttribute("data-status", "active");
    const path = page.url().replace(/^.*\/en/, "");

    await page.getByTestId("event-all-clear").click();
    await page.getByTestId("all-clear-confirm").click();
    await expect(page.getByTestId("event-status")).toHaveAttribute("data-status", "all_clear");
    await expect(page.getByTestId("review-waiting")).toBeVisible();
    await expect(page.getByTestId("rv-submit")).toHaveCount(0);

    await page.context().clearCookies();
    await openAs(page, USERS.noura, path);
    await page.getByTestId("rv-worked").fill("Fire watch checked the area within two minutes.");
    await page.getByTestId("rv-issues").fill("The call point has no protective cover near the forklift route.");
    await page.getByTestId("rv-submit").click();
    await expect(page.getByTestId("event-status")).toHaveAttribute("data-status", "reviewed");
    await expect(page.getByTestId("event-review")).toBeVisible();
  });
});
