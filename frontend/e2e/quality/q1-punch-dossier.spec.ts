import { expect, newClockContext, test } from "../fixtures/test";
import { selectByPrefix, uid } from "../helpers";
import { openQ, QU } from "./q0-helpers";

// Quality Q1 punch list with plan pins and the handover dossier (spec 8-quality §B.5 – §B.8).

const ABDULLAH = "abdullah.dossary@example.com";
const MAZEN = "mazen.harbi@example.com";
// 8 × 8 px PNG (the server shrinks photos; the size does not matter here)
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGNMqehhwAaYsIoOWgkAHV8BeMIH/98AAAAASUVORK5CYII=", "base64");

test.describe("Quality Q1 punch list and dossier", () => {
  test("walkdown on the phone with a pin, fixed by the contractor, verified by the consultant", async ({ page, browser }) => {
    const tag = uid();
    await page.setViewportSize({ width: 390, height: 844 });
    await openQ(page, MAZEN, "/quality/punch/new");
    await selectByPrefix(page.getByTestId("q1-punch-site"), "S-LAND");
    await selectByPrefix(page.getByTestId("q1-punch-zone"), "Z-PIERB");
    await selectByPrefix(page.getByTestId("q1-punch-eng"), "RAWABI");
    await selectByPrefix(page.getByTestId("q1-punch-plan"), "Pier B Level 1");
    const plan = page.getByTestId("q1-plan-pick");
    await expect(plan).toBeVisible();
    // the top band (seeded pins sit lower), a fresh spot each run: clicking a pin would open that item instead
    const box = await plan.boundingBox();
    await plan.click({ position: { x: Math.round((box?.width ?? 300) * (0.15 + Math.random() * 0.7)), y: Math.round((box?.height ?? 200) * (0.04 + Math.random() * 0.06)) } });
    await expect(page.getByTestId("q1-pin-new")).toBeVisible();
    await page.getByTestId("q1-punch-location").fill(`Gate B2 lounge ${tag}`);
    await page.getByTestId("q1-punch-desc").fill(`Skirting loose behind the seating ${tag}`);
    await page.getByTestId("q1-punch-category").selectOption("A");
    await page.getByTestId("q1-punch-photos").setInputFiles({ name: "before.png", mimeType: "image/png", buffer: PNG });
    await page.getByTestId("q1-punch-save").click();
    const detail = page.getByTestId("q1-punch-detail");
    await expect(detail).toHaveAttribute("data-status", "open");
    await expect(page.getByRole("heading", { name: /PCH-ANIA-EXP-2026-/ })).toBeVisible();
    const path = page.url().replace(/^.*\/en/, "");

    const contractor = await (await newClockContext(browser)).newPage();
    await openQ(contractor, QU.joseph, path);
    await contractor.getByTestId("q1-punch-fix-note").fill("Skirting re-fixed with new plugs.");
    await contractor.getByTestId("q1-punch-after").setInputFiles({ name: "after.png", mimeType: "image/png", buffer: PNG });
    await contractor.getByTestId("q1-punch-ready").click();
    await expect(contractor.getByTestId("q1-punch-detail")).toHaveAttribute("data-status", "ready_for_review");

    const consultant = await (await newClockContext(browser)).newPage();
    await openQ(consultant, ABDULLAH, path);
    await consultant.getByTestId("q1-punch-verify").click();
    await consultant.getByTestId("q1-punch-close").click();
    await expect(consultant.getByTestId("q1-punch-detail")).toHaveAttribute("data-status", "closed");
  });

  test("register shows the seeded plan with coloured pins and the overdue filter", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/punch?overdue=true");
    await expect(page.getByTestId("q1-punch-row").filter({ hasText: "PCH-ANIA-EXP-2026-00318" })).toBeVisible();
    await page.goto("/en/quality/floor-plans");
    await page.getByTestId("q1-plan-card").filter({ hasText: "Pier B Level 1" }).click();
    await expect(page.getByTestId("q1-plan-detail")).toBeVisible();
    await expect(page.getByTestId("q1-pin").first()).toBeVisible();
    expect(await page.getByTestId("q1-pin").count()).toBeGreaterThanOrEqual(12);
  });

  test("dossier lists its blockers; compile makes the index and the ZIP; Arabic page", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/dossiers");
    await page.getByTestId("q1-dossier-row").filter({ hasText: "DOS-ANIA-EXP-2026-0001" }).getByRole("link").click();
    const detail = page.getByTestId("q1-dossier-detail");
    await expect(detail).toHaveAttribute("data-status", /draft|compiled/);
    const blockers = page.getByTestId("q1-dossier-blockers");
    await expect(blockers).toContainText("NCR-ANIA-EXP-2026-0044");
    await expect(blockers).toContainText("PCH-ANIA-EXP-2026-00318");
    await page.getByTestId("q1-dossier-compile").click();
    await expect(detail).toHaveAttribute("data-status", "compiled");
    await expect(page.getByTestId("q1-dossier-zip")).toBeVisible();
    await expect(page.getByTestId("q1-dossier-index-ar")).toBeVisible();
    await page.getByTestId("q1-dossier-submit").click();
    await expect(page.getByText(/cannot be submitted/)).toBeVisible();
    await page.goto(page.url().replace("/en/", "/ar/"));
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByText("ملفات التسليم").first()).toBeVisible();
  });
});
