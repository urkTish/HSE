import { expect, test } from "../fixtures/test";
import { login, selectByPrefix, uid } from "../helpers";
import { openQ, pickFirst, QU } from "./q0-helpers";

// Quality Q0 records (spec 8-quality Part A §A.5): observations, quality alerts, customer complaints.

test.describe("Quality Q0 records", () => {
  test("observation from the phone: raise and see it open (Q-OBS-01)", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openQ(page, QU.joseph, "/quality/observations?new=true");
    await pickFirst(page, "obs-site");
    await page.getByTestId("obs-category").selectOption("workmanship");
    await selectByPrefix(page.getByTestId("obs-engagement"), "RAWABI");
    await page.getByTestId("obs-description").fill(`Rebar cover blocks missing at grid B ${uid().slice(0, 6)}`);
    await page.getByTestId("obs-save").click();
    await expect(page.getByTestId("q-obs-detail")).toHaveAttribute("data-status", "open");
    await expect(page.getByRole("heading", { name: /QOB-ANIA-EXP-2026-/ })).toBeVisible();
  });

  test("quality alert: drafted by the quality engineer, issued by the QA/QC Manager (Q-QAL)", async ({ page }) => {
    await openQ(page, QU.rania, "/quality/alerts/new");
    const tag = uid().slice(0, 6);
    await page.getByTestId("al-title-en").fill(`Hold cement lot ${tag}`);
    await page.getByTestId("al-title-ar").fill(`إيقاف دفعة الإسمنت ${tag}`);
    await page.getByTestId("al-msg-en").fill("Do not use the lot until the retest result is in.");
    await page.getByTestId("al-msg-ar").fill("لا تستخدم الدفعة حتى تصدر نتيجة إعادة الاختبار.");
    await page.getByTestId("al-roles").click();
    await page.getByRole("group", { name: "Roles" }).getByText("QC Inspector").click();
    await page.keyboard.press("Escape");
    await page.getByTestId("al-save").click();
    const detail = page.getByTestId("q-alert-detail");
    await expect(detail).toHaveAttribute("data-status", "draft");
    // The drafter may not issue (segregation of duties); the QA/QC Manager does.
    const url = page.url();
    await page.context().clearCookies();
    await login(page, QU.hatem);
    await page.goto(url);
    await page.getByTestId("q-alert-issue").click();
    await expect(detail).toHaveAttribute("data-status", "issued");
    await expect(page.getByTestId("q-alert-acks")).toContainText("0/");
  });

  test("complaints on the logistics project: list and the investigation step (Q-CMP)", async ({ page }) => {
    await openQ(page, QU.reem, "/quality/complaints", { project: "RUH-CCH" });
    const row = page.locator('[data-testid="q-complaint-row"][data-no="CCM-RUH-CCH-2026-0004"]');
    await expect(row).toBeVisible();
    await row.getByRole("link").click();
    await expect(page.getByTestId("q-complaint-detail")).toHaveAttribute("data-status", "under_investigation");
    await expect(page.getByTestId("q-cmp-respond-form")).toBeVisible();
  });

  test("Arabic: alert register in right-to-left", async ({ page }) => {
    await openQ(page, QU.hatem, "/quality/alerts", { locale: "ar" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "تنبيهات الجودة" })).toBeVisible();
    await expect(page.locator('[data-testid="q-alert-row"]').first()).toBeVisible();
  });
});
