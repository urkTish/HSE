import { expect, newClockContext, test } from "../fixtures/test";
import { selectByPrefix, uid } from "../helpers";
import { openQ, QU } from "./q0-helpers";

// Quality Q1 (spec 8-quality Part B §B.3, §B.4, §B.8): ITP register and builder, approval by the responsible
// person, IR raised on the phone, scheduled and inspected, Arabic RTL, and the logistics profile hiding Part B.

const ABDULLAH = "abdullah.dossary@example.com";

test.describe("Quality Q1 ITPs and inspection requests", () => {
  test("seeded ITP register, detail, coverage and revision compare", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/itps");
    const row = page.getByTestId("q1-itp-row").filter({ hasText: "ITP-ANIA-EXP-STC-001" });
    await expect(row).toBeVisible();
    await row.getByRole("link").first().click();
    const detail = page.getByTestId("q1-itp-detail");
    await expect(detail).toHaveAttribute("data-status", "approved");
    await expect(page.getByRole("heading", { name: /ITP-ANIA-EXP-STC-001 Rev\.2/ })).toBeVisible();
    await expect(page.getByTestId("q1-point-row")).toHaveCount(9);
    await page.getByTestId("q1-itp-tab-coverage").click();
    await expect(page.getByTestId("q1-coverage")).toBeVisible();
    await page.getByTestId("q1-itp-tab-revisions").click();
    await expect(page.getByTestId("q1-itp-compare")).toContainText("Rev.1");
  });

  test("builder → submit → approval by the consultant → IR raised on the phone → inspected", async ({ page, browser }) => {
    const tag = uid();
    await openQ(page, QU.bilal, "/quality/itps/new");
    await page.getByTestId("q1-itp-title-en").fill(`Blockwork walls ${tag}`);
    await page.getByTestId("q1-itp-title-ar").fill(`جدران البلوك ${tag}`);
    await page.getByTestId("q1-itp-discipline").selectOption("ARC");
    await selectByPrefix(page.getByTestId("q1-itp-engagement"), "RAWABI");
    await page.getByTestId("q1-pt-10-H").click();
    await page.getByTestId("q1-pt-10-activity").fill("Setting out and first course");
    await page.getByTestId("q1-pt-10-char").fill("Line, level and dowels");
    await page.getByTestId("q1-pt-10-acceptance").fill("± 5 mm to grid");
    await page.getByTestId("q1-itp-submit").click();
    const detail = page.getByTestId("q1-itp-detail");
    await expect(detail).toHaveAttribute("data-status", "submitted");
    const itpUrl = page.url();

    // the consultant (position CONSULTANT_RE) approves with code A
    const consultant = await (await newClockContext(browser)).newPage();
    await openQ(consultant, ABDULLAH, itpUrl.replace(/^.*\/en/, ""));
    await consultant.getByTestId("q1-itp-decide").click();
    await consultant.getByTestId("q1-itp-decide-confirm").click();
    await expect(consultant.getByTestId("q1-itp-detail")).toHaveAttribute("data-status", "approved");

    // Joseph (RAWABI QC) raises the IR on his phone
    const phone = await (await newClockContext(browser)).newPage();
    await phone.setViewportSize({ width: 390, height: 844 });
    await openQ(phone, QU.joseph, "/quality/inspection-requests/new");
    const itpSelect = phone.getByTestId("q1-ir-itp");
    await expect(itpSelect.locator("option", { hasText: tag })).toBeAttached();
    await itpSelect.selectOption({ label: (await itpSelect.locator("option", { hasText: tag }).textContent()) ?? "" });
    await phone.getByTestId("q1-ir-point-10").check();
    await selectByPrefix(phone.getByTestId("q1-ir-site"), "S-LAND");
    await selectByPrefix(phone.getByTestId("q1-ir-zone"), "Z-PIERB");
    await phone.getByTestId("q1-ir-location").fill(`Level 2 wall W-${tag}`);
    await phone.getByTestId("q1-ir-selfcheck").check();
    await phone.getByTestId("q1-ir-submit").click();
    const ir = phone.getByTestId("q1-ir-detail");
    await expect(ir).toHaveAttribute("data-status", "submitted");
    await expect(phone.getByRole("heading", { name: /IR-ANIA-EXP-2026-/ })).toBeVisible();
    const irPath = phone.url().replace(/^.*\/en/, "");

    // the consultant schedules and inspects: approved, signed
    await consultant.goto(`/en${irPath}`);
    await consultant.getByTestId("q1-ir-schedule").click();
    await consultant.getByTestId("q1-ir-schedule-confirm").click();
    await expect(consultant.getByTestId("q1-ir-detail")).toHaveAttribute("data-status", "scheduled");
    await consultant.getByTestId("q1-ir-decide").click();
    await consultant.getByTestId("q1-result-approved").click();
    await consultant.getByTestId("q1-run-sign").click();
    await expect(consultant.getByTestId("q1-ir-detail")).toHaveAttribute("data-status", "approved");
    await consultant.getByTestId("q1-ir-tab-signoffs").click();
    await expect(consultant.getByTestId("q1-signoffs")).toContainText("Abdullah");
  });

  test("the consultant's day: seeded scheduled inspections and the Arabic IR page", async ({ page }) => {
    await openQ(page, ABDULLAH, "/quality/inspection-requests", { locale: "ar" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("q1-ir-today")).toBeVisible();
    await expect(page.getByTestId("q1-ir-card").first()).toBeVisible();
    await page.getByTestId("q1-ir-view-register").click();
    await page.locator("#q1-ir-q").fill("00412");
    const row = page.getByTestId("q1-ir-row").filter({ hasText: "IR-ANIA-EXP-2026-00412" });
    await expect(row).toBeVisible();
    await row.getByRole("link").first().click();
    await expect(page.getByTestId("q1-ir-detail")).toHaveAttribute("data-status", "approved");
    await expect(page.getByTestId("q1-ir-round")).toHaveCount(2);
    await expect(page.getByText("نقطة توقف").first()).toBeVisible();
    // the IR number stays left-to-right inside the RTL page
    await expect(page.getByRole("heading", { name: "IR-ANIA-EXP-2026-00412" }).locator(".ltr")).toBeVisible();
  });

  test("logistics project hides the construction items (RUH-CCH)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality", { project: "RUH-CCH" });
    await expect(page.getByTestId("nav-q-ncrs")).toBeVisible();
    await expect(page.getByTestId("nav-q-itps")).toHaveCount(0);
    await expect(page.getByTestId("nav-q-irs")).toHaveCount(0);
    await expect(page.getByTestId("nav-q-punch")).toHaveCount(0);
    await expect(page.getByTestId("nav-q-dossiers")).toHaveCount(0);
  });
});
