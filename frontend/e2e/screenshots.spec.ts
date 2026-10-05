import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";

// Demo screenshots for docs/screenshots/phase-0 (run with SCREENSHOTS=1).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-0");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");

test("phase-0 demo screenshots", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  await page.setViewportSize({ width: 1366, height: 860 });
  await page.goto("/en/login");
  await expect(page.locator("#email")).toBeVisible();
  await page.screenshot({ path: join(OUT, "login-en.png") });
  await page.goto("/ar/login");
  await expect(page.locator("#email")).toBeVisible();
  await page.screenshot({ path: join(OUT, "login-ar.png") });

  await login(page, USERS.faisal, "ar");
  await page.goto("/ar/projects");
  await expect(page.getByTestId("project-row").first()).toBeVisible();
  await page.screenshot({ path: join(OUT, "projects-list-ar.png") });

  const api = await apiAs(USERS.faisal);
  const ania = await projectId(api, "ANIA-EXP");
  const zones = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects/${ania}/zones?q=Z-APR-21`);
  await page.goto(`/en/projects/${ania}/zones/${zones.items[0]?.id ?? ""}`);
  await expect(page.getByTestId("airside-card")).toBeVisible();
  await page.screenshot({ path: join(OUT, "zone-detail-en.png"), fullPage: true });
});
