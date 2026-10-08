import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, login, uid, USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";
import { PNG } from "./p4-helpers";
import { recordOf } from "./p5-helpers";

async function draftExternal(page: Page, worker: string, opts: { id?: string; certNo?: string } = {}): Promise<void> {
  await page.goto("/en/training-records/new");
  await page.getByTestId("tr-holder-search").fill(worker);
  await selectContaining(page.getByTestId("tr-holder"), worker);
  await page.getByTestId("tr-name-as-printed").fill("Biju Thomas");
  if (opts.id) {
    await page.getByTestId("tr-id-shown").check();
    await page.getByTestId("tr-id-number").fill(opts.id);
  } else {
    await page.getByTestId("tr-id-shown").uncheck();
  }
  await page.getByTestId("tr-course").selectOption("FIRST-AID");
  await selectContaining(page.getByTestId("tr-provider"), "HAYAT");
  await page.getByTestId("tr-cert-no").fill(opts.certNo ?? `HY-FA-E2E-${uid()}`);
  await page.getByTestId("tr-completed").fill("2026-09-01");
  const theory = page.getByTestId("tr-theory");
  if (await theory.count()) await theory.fill("88");
}

/** External records, review, suspension, scans and verification log (5-training §5.12–§5.14; AC65, AC67, AC69, AC74, AC139, AC141). */
test.describe("Training records", () => {
  test("AC67: an ID typed from the card that does not match the worker is refused, the right one is matched", async ({ page }) => {
    await login(page, USERS.ahmed);
    await draftExternal(page, "WKR-000017", { id: "2000001071" });
    await page.getByTestId("save-record").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "CERT_ID_MISMATCH");
    await expect(page).toHaveURL(/\/training-records\/new/);

    await page.getByTestId("tr-id-number").fill("2000001017");
    await page.getByTestId("save-record").click();
    await expect(page).toHaveURL(/\/training-records\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("id-match")).toHaveAttribute("data-result", "matched");
    await expect(page.locator("main")).not.toContainText("2000001017");
  });

  test("AC65/AC69/AC139: Ahmed cannot submit without a scan; after uploading it he submits, cannot accept, and opens the scan with a reason", async ({ page }) => {
    await login(page, USERS.ahmed);
    await draftExternal(page, "WKR-000017");
    await page.getByTestId("save-record").click();
    await expect(page).toHaveURL(/\/training-records\/[0-9a-f-]{36}$/);

    await page.getByTestId("record-submit").click();
    await page.getByTestId("record-confirm").click();
    await expect(page.getByTestId("form-error")).toBeVisible();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", /SCAN_REQUIRED|VALIDATION_ERROR/);
    await page.keyboard.press("Escape");

    await page.getByTestId("tr-scan").setInputFiles(PNG("first-aid-card.png"));
    await expect(page.getByTestId("open-scan")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("record-submit").click();
    await page.getByTestId("record-confirm").click();
    await expect(page.getByTestId("record-accept")).toHaveCount(0);
    await expect(page.getByTestId("record-submit")).toHaveCount(0);

    await page.getByTestId("open-scan").click();
    await page.getByTestId("scan-reason").selectOption("verification");
    const signed = page.waitForResponse((r) => r.url().includes("/scan-url") && r.request().method() === "POST");
    await page.getByTestId("scan-confirm").click();
    const res = await signed;
    expect(res.status()).toBe(200);
    expect(((await res.json()) as { url: string }).url).toMatch(/^(https?:\/\/|\/)/);
  });

  test("AC74/AC141: suspension needs a 20-character reason; the HSE Rep then sees 'not accepted' without details", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const rec = await recordOf(api, "ANIA-EXP", "WKR-000009", "WAH");
    await login(page, USERS.noura);
    await page.goto(`/en/training-records/${rec.id}`);
    await page.getByTestId("record-suspend").click();
    await page.getByTestId("tr-reason").fill("Card looks");
    await expect(page.getByTestId("record-confirm")).toBeDisabled();
    await page.getByTestId("tr-reason").fill("Card details do not match the provider register entry");
    await page.getByTestId("record-confirm").click();
    await expect(page.getByTestId("record-reinstate")).toBeVisible();

    await login(page, USERS.ahmed);
    await page.goto(`/en/training-records/${rec.id}`);
    await expect(page.getByTestId("not-accepted")).toBeVisible();
    await expect(page.locator("main")).not.toContainText("provider register entry");
    await page.goto("/ar/training-records/" + rec.id);
    await expect(page.getByTestId("not-accepted")).toContainText("السجل التدريبي غير مقبول");
  });

  test("Verification log lists Waleed Saleh's not-found QUICKTRAIN check", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-verification-log?failed_only=1");
    await expect(page.getByTestId("verification-log")).toBeVisible();
    await expect(page.locator('[data-testid="verif-log-row"][data-outcome="not_found"]').first()).toContainText("WKR-000008");
  });
});
