import { expect, test } from "./fixtures/test";
import { USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

const TARIQ = "tariq.mutairi@example.com";
const row = (doc: string, rev: number) => `[data-testid="rp-row"][data-doc="${doc}"][data-revision="${rev}"]`;

/** Report packs: register, revisions, contents, review → issue with the provisional watermark, distribution scope (6g §3.7–§3.9 RP, DL; AC 36–45). */
test.describe("Report packs", () => {
  test("August MCR: Rev 1 issued with files and deliveries, Rev 0 superseded (RP-5)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/report-packs");
    await expect(page.locator(row("MCR-ANIA-EXP-2026-08", 0))).toHaveAttribute("data-status", "superseded");
    await page.locator(row("MCR-ANIA-EXP-2026-08", 1)).getByRole("link").click();
    await expect(page.getByTestId("rp-doc-no")).toHaveText("MCR-ANIA-EXP-2026-08");
    await expect(page.getByTestId("rp-status")).toHaveAttribute("data-status", "issued");
    await expect(page.getByTestId("rp-file").first()).toBeVisible();
    await expect(page.getByTestId("rp-delivery").first()).toBeVisible();
    await expect(page.getByTestId("rp-section").first()).toBeVisible();

    await page.goto("/en/report-packs");
    await page.locator(row("MCR-ANIA-EXP-2026-08", 0)).getByRole("link").click();
    await expect(page.getByTestId("rp-superseded")).toBeVisible();
    await expect(page.getByTestId("rp-actions")).toHaveCount(0);
  });

  test("September MCR: Noura submits and reviews; Faisal needs the provisional watermark to issue (RP-3, RP-4)", async ({ page }) => {
    await openAs(page, USERS.noura, "/report-packs");
    await page.locator(row("MCR-ANIA-EXP-2026-09", 0)).getByRole("link").click();
    await expect(page.getByTestId("rp-status")).toHaveAttribute("data-status", "draft");
    await expect(page.getByTestId("rp-not-live")).toBeVisible();
    await expect(page.getByTestId("rp-issue")).toHaveCount(0);
    await page.getByTestId("rp-submit").click();
    await expect(page.getByTestId("rp-status")).toHaveAttribute("data-status", "in_review");
    await page.getByTestId("rp-review").click();
    await expect(page.getByTestId("rp-review")).toHaveCount(0);
    const url = page.url().replace(/^https?:\/\/[^/]+\/en/, "");

    await openAs(page, USERS.faisal, url);
    await page.getByTestId("rp-issue").click();
    await page.getByTestId("rp-issue-confirm").click();
    await expect(page.getByText("The month's scorecards are not Final.")).toBeVisible();
    await page.getByTestId("rp-provisional").check();
    await page.getByTestId("rp-provisional-reason").fill("Client meeting on the 12th needs the pack before the window closes (TEST).");
    await page.getByTestId("rp-issue-confirm").click();
    await expect(page.getByTestId("rp-status")).toHaveAttribute("data-status", "issued");
    await expect(page.getByTestId("rp-watermark").first()).toBeVisible();
    await expect(page.getByTestId("rp-delivery").first()).toBeVisible();
  });

  test("Ahmed cannot be put on the MCR distribution list (DL-2)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/distribution-lists?type=MCR");
    await expect(page.locator('[data-testid="dl-member"][data-kind="external"]')).toHaveCount(1);
    const option = page.getByTestId("dl-user").locator("option", { hasText: "Ahmed" }).first();
    await page.getByTestId("dl-user").selectOption((await option.getAttribute("value")) ?? "");
    await page.getByTestId("dl-add-user").click();
    await page.getByTestId("dl-ack").check();
    await page.getByTestId("dl-save").click();
    await expect(page.getByText("This recipient may not receive this report type.")).toBeVisible();
  });

  test("Tariq sees only his NAJD and SAHARA scorecard packs; Ramesh has no reports menu (RP-6)", async ({ page }) => {
    await openAs(page, TARIQ, "/report-packs");
    await expect(page.getByTestId("rp-row")).toHaveCount(4);
    await expect(page.locator('[data-testid="rp-row"][data-doc^="MCR-"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="rp-row"][data-doc^="SCP-ANIA-EXP-RAWABI"]')).toHaveCount(0);
    await expect(page.getByTestId("rp-new")).toHaveCount(0);
    await openAs(page, USERS.ramesh, "/");
    await expect(page.getByTestId("nav-xp-exports")).toBeVisible();
    await expect(page.getByTestId("nav-rp-packs")).toHaveCount(0);
  });
});
