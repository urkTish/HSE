import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import en from "../messages/en.json" with { type: "json" };
import { apiAs, login, projectId, uid, userId, USERS, selectByPrefix } from "./helpers";

const short = `E2E${uid()}`;
const cr = `7${String(Date.now()).slice(-9)}`;

async function fillContractor(page: Page, crNumber: string) {
  await page.locator("#legal_name_en").fill(`E2E Builders ${short}`);
  await page.locator("#legal_name_ar").fill("شركة البناء التجريبية");
  await page.locator("#short_code").fill(short);
  await page.locator("#cr_number").fill(crNumber);
  await page.locator("#contractor_category").selectOption("civil");
  await page.locator("#primary_contact_name").fill("E2E Contact");
  await page.locator("#primary_contact_mobile").fill("+966500009999");
  await page.locator("#primary_contact_email").fill("e2e.contact@example.com");
}

test.describe.serial("Contractors and engagements", () => {
  test("AC18: CR format and duplicate CR are rejected; a valid contractor is created", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/contractors/new");
    await fillContractor(page, "12345");
    await page.getByTestId("save").click();
    await expect(page.locator("#cr_number-error")).toHaveText(en.validation.crNumber);
    await page.locator("#cr_number").fill("1010000001");
    await page.getByTestId("save").click();
    await expect(page.getByTestId("form-error")).toBeVisible();
    await expect(page.getByTestId("form-error")).toHaveText(en.errors.code.DUPLICATE_VALUE);
    await page.locator("#cr_number").fill(cr);
    await page.getByTestId("save").click();
    await expect(page.getByTestId("contractor-title")).toHaveText(`E2E Builders ${short}`);
    await expect(page.locator("[data-status=draft]")).toBeVisible();
    await page.getByTestId("transition-pending_approval").click();
    await page.getByTestId("transition-confirm").click();
    await expect(page.locator("[data-status=pending_approval]")).toBeVisible();
  });

  test("AC21: engaging a contractor pending approval is rejected", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP");
    await login(page, USERS.faisal);
    await page.goto(`/en/projects/${ania}/engagements/new`);
    await selectByPrefix(page.locator("#contractor_id"), short);
    await page.locator("#tier").selectOption("1");
    await page.locator("#scope_of_work_en").fill("E2E works");
    await page.locator("#scope_of_work_ar").fill("أعمال تجريبية");
    await page.locator("#mobilisation_date").fill("2026-10-01");
    await page.getByLabel(/S-LAND/).check();
    await page.getByTestId("save").click();
    await expect(page.getByTestId("form-error")).toHaveText(en.errors.code.CONTRACTOR_NOT_APPROVED);
  });

  test("AC17: tier-3 parents are limited to tier 2; approved contractor engaged as tier 2", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP");
    await login(page, USERS.faisal);
    const contractors = await (await api.get(`/api/v1/contractors?q=${short}`)).json();
    await page.goto(`/en/contractors/${contractors.items[0].id}`);
    await page.getByTestId("transition-approved").click();
    await page.getByTestId("transition-confirm").click();
    await expect(page.locator("[data-status=approved]")).toBeVisible();

    await page.goto(`/en/projects/${ania}/engagements/new`);
    await page.locator("#tier").selectOption("3");
    const parents = (await page.locator("#parent_engagement_id option").allTextContents()).slice(1);
    expect(parents.length).toBeGreaterThan(0);
    for (const p of parents) expect(p).toContain("Tier 2");
    expect(parents.join()).not.toContain("RAWABI");

    await selectByPrefix(page.locator("#contractor_id"), short);
    await page.locator("#tier").selectOption("2");
    await selectByPrefix(page.locator("#parent_engagement_id"), "RAWABI");
    await page.locator("#scope_of_work_en").fill("E2E works");
    await page.locator("#scope_of_work_ar").fill("أعمال تجريبية");
    await page.locator("#mobilisation_date").fill("2026-10-01");
    await page.getByLabel(/S-LAND/).check();
    await page.getByTestId("save").click();
    await expect(page.getByTestId("engagement-title")).toContainText(short);
  });

  test("AC20: blacklisting requires a reason and is applied", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    await login(page, USERS.faisal);
    const contractors = await (await api.get(`/api/v1/contractors?q=${short}`)).json();
    await page.goto(`/en/contractors/${contractors.items[0].id}`);
    await page.getByTestId("transition-blacklisted").click();
    await expect(page.getByText(en.contractor.blacklistWarning)).toBeVisible();
    await page.getByTestId("transition-confirm").click();
    await expect(page.getByText(en.transitions.reasonRequired)).toBeVisible();
    await page.locator("#transition-reason").fill("E2E blacklist test");
    await page.getByTestId("transition-confirm").click();
    await expect(page.locator("[data-status=blacklisted]")).toBeVisible();
    await expect(page.getByText("E2E blacklist test")).toBeVisible();
    await expect(page.getByTestId("transition-suspended")).toHaveText(en.contractor.actions.liftBlacklist);
  });

  test("AC28: Arabic search ignores alef/teh-marbuta/yeh variants", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/contractors");
    for (const q of ["الروابى", "شركه الروابي"]) {
      await page.locator("#contractor-q").fill(q);
      await expect(page.getByTestId("contractor-row")).toHaveCount(1);
      await expect(page.locator("[data-code=RAWABI]")).toBeVisible();
    }
  });

  test("AC13: assigning Permit Receiver to a Permit Issuer shows SOD_CONFLICT", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const khalid = await userId(api, USERS.khalid);
    await login(page, USERS.faisal);
    await page.goto(`/en/users/${khalid}`);
    await page.getByTestId("assign-role").click();
    await page.getByTestId("assignment-role").selectOption("permit_receiver");
    await selectByPrefix(page.getByTestId("assignment-project"), "ANIA-EXP");
    await selectByPrefix(page.getByTestId("assignment-engagement"), "NAJD");
    await page.getByTestId("assign-confirm").click();
    await expect(page.getByTestId("form-error")).toHaveText(en.errors.code.SOD_CONFLICT);
  });

  test("AC33: Viewer Sarah's contractor export has no contact columns", async ({ page }) => {
    await login(page, USERS.sarah);
    await page.goto("/en/contractors");
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-csv").click()]);
    const file = readFileSync((await download.path()) ?? "", "utf8");
    const header = file.replace(/^﻿/, "").split(/\r?\n/)[0] ?? "";
    expect(header).toContain("short_code");
    expect(header).not.toMatch(/contact/);
    await login(page, USERS.faisal);
    await page.goto("/en/audit-log");
    await page.locator("#audit-action").selectOption("export");
    await expect(page.getByTestId("audit-row").filter({ hasText: "Sarah Mitchell" }).first()).toBeVisible();
  });
});
