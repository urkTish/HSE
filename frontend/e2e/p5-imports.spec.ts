import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";

const HEAD = "worker_no,id_type,id_number,passport_country,course_code,provider_code,certificate_no,completed_on,printed_expiry,theory_score_pct,practical_result,hours,project_sponsored,name_as_printed,id_on_card";

async function upload(page: Page, name: string, csv: string): Promise<void> {
  await page.goto("/en/training-imports");
  await page.getByTestId("ti-template").selectOption("training_records");
  await page.getByTestId("ti-file").setInputFiles({ name, mimeType: "text/csv", buffer: Buffer.from(csv, "utf8") });
  await page.getByTestId("ti-check").click();
}

/** Training record imports (5-training §5.12, IM5; AC114, AC119). */
test.describe("Training imports", () => {
  test("AC114: dry run gives OK, E01 and E04 with the ID masked; commit creates one Submitted record", async ({ page }) => {
    const sfx = uid();
    const rows = [
      `,iqama,2000001017,,FIRST-AID,HAYAT,HY-FA-E2E-${sfx},2026-09-10,,85,pass,,N,Biju Thomas,same_as_lookup`,
      `WKR-999999,,,,FIRST-AID,HAYAT,HY-FA-E2E-${sfx}-2,2026-09-10,,85,pass,,N,Nobody Known,`,
      `WKR-000021,,,,FIRST-AID,HAYAT,HY-FA-TEST-24-1116,2024-11-16,,85,pass,,N,Rafiq Islam,`,
    ];
    await login(page, USERS.noura);
    await upload(page, `first-aid-${sfx}.csv`, `${HEAD}\r\n${rows.join("\r\n")}\r\n`);
    await expect(page).toHaveURL(/\/training-imports\/[0-9a-f-]{36}$/);
    await page.locator("#ti-show-ok").check();
    const r = page.getByTestId("ti-row");
    await expect(r).toHaveCount(3);
    await expect(page.locator('[data-testid="ti-row"][data-row="1"]')).toHaveAttribute("data-status", /ok|warning/);
    await expect(page.locator('[data-testid="ti-row"][data-row="2"]')).toContainText("E01");
    await expect(page.locator('[data-testid="ti-row"][data-row="3"]')).toContainText("E04");
    await expect(page.getByTestId("ti-id-masked").first()).toHaveText("2*******17");
    await expect(page.locator("main")).not.toContainText("2000001017");

    await page.getByTestId("ti-commit").click();
    await expect(page.getByTestId("ti-committed")).toBeVisible();
    await expect(page.getByTestId("ti-count-records_created")).toContainText("1");
  });

  test("AC119: a file without the course_code column is rejected as a whole with E12", async ({ page }) => {
    const sfx = uid();
    const head = HEAD.replace("course_code,", "");
    const row = `WKR-000017,,,,HAYAT,HY-FA-E2E-${sfx},2026-09-10,,85,pass,,N,Biju Thomas,`;
    await login(page, USERS.noura);
    await upload(page, `no-course-${sfx}.csv`, `${head}\r\n${row}\r\n`);
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "IMPORT_FILE_INVALID");
    await expect(page.getByTestId("ti-file-error")).toHaveAttribute("data-code", "E12");
    await expect(page.getByTestId("ti-file-error")).toContainText("course_code");
    await expect(page).toHaveURL(/\/training-imports$/);
  });
});
