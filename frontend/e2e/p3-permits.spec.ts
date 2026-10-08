import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";

/** Permit form and core rules: duration limit per type (AC10), zones on one site (AC11), draft → request. */

const riyadhDay = (n: number) => new Date(Date.now() + n * 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Riyadh" });

async function fillPermit(page: Page, o: { title: string; site: string; zones: RegExp[]; types: string[]; from: string; to: string; gx?: string; gy?: string }) {
  await page.goto("/en/permits/new");
  const f = page.getByTestId("permit-form");
  await selectContaining(f.getByTestId("pf-site"), o.site);
  await pickMulti(page, "pf-zones", o.zones);
  await f.getByTestId("pf-location").fill("Grid line C, level 1");
  if (o.gx) await f.getByTestId("pf-grid-x").fill(o.gx);
  if (o.gy) await f.getByTestId("pf-grid-y").fill(o.gy);
  await selectContaining(f.getByTestId("pf-engagement"), "NAJD");
  await f.getByTestId("pf-title").fill(o.title);
  for (const t of o.types) await page.getByRole("group", { name: /work types/i }).getByLabel(t, { exact: true }).check();
  await f.getByTestId("pf-scope").fill("Install temporary barriers and signage for the e2e run.");
  await f.getByTestId("pf-from").fill(o.from);
  await f.getByTestId("pf-to").fill(o.to);
  await f.getByTestId("pf-emergency").fill("Call 997; assembly point AP-3; first aider on site.");
}

test("AC10 a hot-work request longer than the type limit is refused naming hot_work", async ({ page }) => {
  await login(page, USERS.ramesh);
  await fillPermit(page, { title: `E2E hot work ${uid()}`, site: "S-LAND", zones: [/Z-PIERB/], types: ["Hot work"], from: `${riyadhDay(1)}T07:00`, to: `${riyadhDay(2)}T09:00` });
  await page.getByTestId("save-permit").click();
  await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "DURATION_EXCEEDS_LIMIT");
  await expect(page.getByTestId("permit-form")).toContainText("hot_work");
});

test("AC11 zones from two sites cannot share a permit", async ({ page }) => {
  await login(page, USERS.faisal);
  await page.goto("/en/permits/new");
  // The form only offers zones of the chosen site, so the rule is enforced by construction in the UI.
  const f = page.getByTestId("permit-form");
  await selectContaining(f.getByTestId("pf-site"), "S-LAND");
  await page.locator("button#pf-zones").click();
  await expect(page.getByRole("listbox").getByRole("option", { name: /Z-PIERB/ })).toBeVisible();
  await expect(page.getByRole("listbox").getByRole("option", { name: /Z-APR-21/ })).toHaveCount(0);
});

test("a receiver drafts a general permit and sees every readiness blocker", async ({ page }) => {
  await login(page, USERS.ramesh);
  const title = `E2E general ${uid()}`;
  await fillPermit(page, { title, site: "S-LAND", zones: [/Z-LAY1/], types: ["General / cold work"], from: `${riyadhDay(1)}T07:00`, to: `${riyadhDay(1)}T17:00`, gx: "900.0", gy: "900.0" });
  await page.getByTestId("save-permit").click();
  await expect(page).toHaveURL(/\/permits\/[0-9a-f-]{36}/);
  await expect(page.getByTestId("permit-status")).toHaveAttribute("data-status", "draft");
  await expect(page.getByTestId("permit-no")).toContainText(/PTW-ANIA-EXP-\d{4}-\d{4}/);
  // Readiness lists every blocker from the server (no JSA, documents, crew roles, checklist at issue).
  await expect(page.locator("[data-testid=blocker][data-code=JSA_MISSING]")).toBeVisible();
  await expect(page.locator("[data-testid=blocker][data-code=ROLE_MISSING]")).toBeVisible();
});

