import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";

// Phase 3 demo screenshots for docs/screenshots/phase-3 (run with SCREENSHOTS=1).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-3");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(300_000);

const FARIS = "faris.anazi@example.com";
const MAJED = "majed.shammari@example.com";

async function find(email: string, project: string, path: string, key: string, value: string): Promise<string> {
  const api = await apiAs(email);
  const projects = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects?q=${project}`);
  const pid = projects.items.find((p) => p.code === project)?.id ?? "";
  const list = await getJson<{ items: Record<string, string>[] }>(api, `/api/v1/projects/${pid}/${path}?q=${encodeURIComponent(value)}&page_size=50`);
  return list.items.find((x) => x[key] === value)?.id ?? "";
}

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

test("phase-3 demo screenshots", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  const p0413 = await find(USERS.faisal, "ANIA-EXP", "permits", "permit_no", "PTW-ANIA-EXP-2026-0413");
  const iso = await find(USERS.faisal, "ANIA-EXP", "isolations", "iso_no", "ISO-ANIA-EXP-2026-0061");
  const sim = await find(MAJED, "RBT-52", "simops-conflicts", "conflict_no", "SIM-RBT-52-2026-0021");

  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, USERS.faisal);
  await page.goto(`/en/permits/${p0413}`);
  await expect(page.getByTestId("permit-detail")).toBeVisible();
  await shot(page, "permit-detail-desktop-en.png");

  await page.goto(`/en/isolations/${iso}`);
  await expect(page.getByTestId("deisolation-blockers")).toBeVisible();
  await shot(page, "loto-isolation.png");

  await page.goto("/en/ptw-board");
  await expect(page.getByTestId("board-permit").first()).toBeVisible();
  await shot(page, "ptw-board.png");

  await page.goto(`/en/permits/${p0413}/print`);
  await expect(page.getByTestId("permit-print")).toBeVisible();
  await page.getByTestId("permit-print").screenshot({ path: join(OUT, "permit-print.png") });

  await page.goto("/en");
  const band = page.getByTestId("ptw-band");
  await expect(band).toBeVisible({ timeout: 60_000 });
  await band.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500);
  await band.screenshot({ path: join(OUT, "dashboard-ptw-band.png") });

  await page.context().clearCookies();
  await login(page, FARIS);
  await page.goto(`/en/gas-tests/new?permit_id=${p0413}`);
  await selectContaining(page.getByTestId("gas-detector"), "GD-ANIA-003");
  await page.getByTestId("gas-type").selectOption("periodic");
  await selectContaining(page.getByTestId("gas-tester"), "Salem");
  await page.locator("#ge-temp").fill("31.5");
  const rows = page.getByTestId("gas-reading-row");
  const vals = [["20.9", "0", "0", "2"], ["20.8", "1", "1", "3"], ["20.6", "0", "0", "1"]];
  for (let i = 0; i < (await rows.count()); i++) {
    const v = vals[i] ?? vals[0]!;
    await rows.nth(i).getByTestId("reading-o2_pct").fill(v[0]!);
    await rows.nth(i).getByTestId("reading-lel_pct").fill(v[1]!);
    await rows.nth(i).getByTestId("reading-h2s_ppm").fill(v[2]!);
    await rows.nth(i).getByTestId("reading-co_ppm").fill(v[3]!);
  }
  await expect(page.locator("[data-testid=preview-fails] [data-code=H2S_ABOVE_LIMIT]")).toBeVisible({ timeout: 15_000 });
  await shot(page, "gas-test-entry.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/ar/permits/${p0413}`);
  await expect(page.getByTestId("permit-detail")).toBeVisible();
  await shot(page, "permit-mobile-ar.png");

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().clearCookies();
  await login(page, MAJED);
  await page.goto(`/en/simops-conflicts/${sim}`);
  await expect(page.getByTestId("conflict-status")).toBeVisible();
  await shot(page, "simops-conflict.png");
});
