import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";

/** JSA editor: 5×5 scores and bands (AC26), PPE-only rule (AC29), mandatory hazards at submit (AC28). */

async function newTemplate(page: Page, title: string) {
  await page.goto("/en/jsa-templates/new");
  await page.locator("#jt-title-en").fill(title);
  await page.getByRole("group", { name: /work types/i }).getByLabel("Working at height").check();
  await page.locator("#st-0-en").fill("Erect and inspect the edge protection");
}

async function setScore(page: Page, id: string, l: number, s: number) {
  await page.getByTestId(`${id}-l`).selectOption(String(l));
  await page.getByTestId(`${id}-s`).selectOption(String(s));
}

test("AC26 line scores, bands and the governing residual band follow the project matrix", async ({ page }) => {
  await login(page, USERS.faisal);
  await newTemplate(page, `E2E WAH template ${uid()}`);
  await page.getByTestId("add-hazard").click();
  await page.locator("#l-0-0-desc").fill("Fall from the slab edge");
  await setScore(page, "l-0-0-init", 4, 5);
  await setScore(page, "l-0-0-res", 2, 5);
  await page.getByTestId("control-text").first().fill("Guard rails and toe boards");
  await expect(page.getByTestId("l-0-0-init-score")).toContainText("20");
  await expect(page.getByTestId("l-0-0-res-score")).toContainText("10");

  await page.getByTestId("add-hazard").click();
  await page.getByTestId("line-hazard").nth(1).selectOption("falling_objects");
  await page.locator("#l-0-1-desc").fill("Dropped tools");
  await setScore(page, "l-0-1-init", 4, 3);
  await setScore(page, "l-0-1-res", 2, 2);
  await page.getByTestId("control-text").nth(1).fill("Tool lanyards and debris netting");
  await expect(page.getByTestId("l-0-1-init-score")).toContainText("12");
  await expect(page.getByTestId("l-0-1-res-score")).toContainText("4");

  await page.getByTestId("save-jsa").click();
  await expect(page).toHaveURL(/\/jsas\/[0-9a-f-]{36}/);
  await expect(page.getByTestId("jsa-status")).toHaveAttribute("data-status", "draft");
  await expect(page.getByTestId("governing-band")).toHaveAttribute("data-band", "high");
  await expect(page.locator("[data-testid=jsa-line][data-hazard=fall_from_height]")).toHaveAttribute("data-residual-band", "high");
  await expect(page.locator("[data-testid=jsa-line][data-hazard=falling_objects]")).toHaveAttribute("data-residual-band", "low");
  await expect(page.getByTestId("missing-hazards")).toHaveCount(0);
});

test("AC29 PPE-only controls cannot lower the band; same band is accepted", async ({ page }) => {
  await login(page, USERS.faisal);
  await newTemplate(page, `E2E PPE template ${uid()}`);
  await page.getByTestId("add-hazard").click();
  await page.locator("#l-0-0-desc").fill("Fall from the ladder");
  await setScore(page, "l-0-0-init", 3, 3);
  await setScore(page, "l-0-0-res", 1, 3);
  await page.getByTestId("control-level").first().selectOption("ppe");
  await page.getByTestId("control-text").first().fill("Harness");
  await expect(page.getByTestId("line-issues").locator("[data-issue=ppeOnly]")).toBeVisible();
  await page.getByTestId("save-jsa").click();
  await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "PPE_ONLY_CONTROLS");

  await setScore(page, "l-0-0-res", 2, 3);
  await expect(page.locator("[data-issue=ppeOnly]")).toHaveCount(0);
  // Still missing falling_objects for WAH: the draft saves, Submit is refused (AC28).
  await page.getByTestId("save-jsa").click();
  await expect(page).toHaveURL(/\/jsas\/[0-9a-f-]{36}/);
  await expect(page.getByTestId("missing-hazards")).toBeVisible();
  await page.getByTestId("jsa-submit").click();
  await page.getByTestId("jsa-step-confirm").click();
  await expect(page.getByRole("dialog").getByTestId("form-error")).toHaveAttribute("data-code", "JSA_MANDATORY_HAZARD_MISSING");
});
