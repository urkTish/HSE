import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Lessons learned: library search, review and publication, acknowledgement on a phone, effectiveness check (6f §3.6–§3.9, LL, DS, EF; AC 28, 32, 33, 38). */
test.describe("Lessons learned", () => {
  test("the library finds LL-2026-007 with an Arabic search; the viewer cannot list drafts", async ({ page }) => {
    await openAs(page, USERS.sarah, "/lessons");
    await page.getByTestId("ll-search").fill("سقاله");
    await expect(page.locator('[data-testid="ll-card"][data-no="LL-2026-007"]')).toBeVisible();
    await expect(page.locator("#ll-status option[value=draft]")).toHaveCount(0);
    await expect(page.getByTestId("lesson-new")).toHaveCount(0);

    await openAs(page, USERS6.huda, "/lessons?q=scaffold%20platform%20edge");
    await expect(page.locator('[data-testid="ll-card"][data-no="LL-2026-007"]')).toBeVisible();
  });

  test("Faisal publishes Noura's LL-2026-008; the author cannot publish it", async ({ page }) => {
    await openAs(page, USERS.noura, "/lessons?status=in_review");
    await page.locator('[data-testid="ll-card"][data-no="LL-2026-008"] a').click();
    await expect(page.getByTestId("lesson-status")).toHaveAttribute("data-status", "in_review");
    await expect(page.getByTestId("lesson-publish")).toHaveCount(0);
    const path = new URL(page.url()).pathname.replace(/^\/en/, "");

    await openAs(page, USERS.faisal, path);
    await page.getByTestId("lesson-publish").click();
    await expect(page.getByTestId("lesson-status")).toHaveAttribute("data-status", "published");
    await expect(page.getByTestId("lesson-distribution").getByTestId("dist-item").first()).toBeVisible();
    await expect(page.getByTestId("lesson-check")).toHaveAttribute("data-status", "scheduled");
  });

  test("Ahmed acknowledges LL-2026-007 for SAHARA on his phone (DS-3)", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS.ahmed, "/lesson-acknowledgements");
    const item = page.locator('[data-testid="dist-item"][data-lesson="LL-2026-007"][data-engagement="SAHARA"]');
    await expect(item).toHaveAttribute("data-status", "pending");
    await expect(item.getByTestId("fu-countdown")).toHaveAttribute("data-overdue", "true");
    await expect(item.getByTestId("ack-submit")).toBeDisabled();
    await item.getByTestId("ack-response-will_brief").click();
    await item.getByTestId("ack-submit").click();
    await expect(page.locator('[data-testid="dist-item"][data-lesson="LL-2026-007"][data-engagement="SAHARA"]')).toHaveCount(0);
    await page.goto("/en/lesson-acknowledgements?status=acknowledged");
    await expect(page.locator('[data-testid="dist-item"][data-lesson="LL-2026-007"][data-engagement="SAHARA"]')).toHaveAttribute("data-status", "acknowledged");
  });

  test("Noura completes the LL-2026-004 effectiveness check as suggested (EF-4)", async ({ page }) => {
    await openAs(page, USERS.noura, "/effectiveness-checks");
    const row = page.locator('[data-testid="check-row"][data-no="LL-2026-004"]');
    await row.getByTestId("check-row-complete").click();
    await expect(page.getByTestId("check-result-effective")).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("check-result-partly_effective").click();
    await expect(page.getByTestId("check-confirm")).toBeDisabled();
    await page.getByTestId("check-result-effective").click();
    await page.getByTestId("check-confirm").click();
    await expect(row.getByTestId("check-status")).toHaveAttribute("data-status", "completed");
  });
});
