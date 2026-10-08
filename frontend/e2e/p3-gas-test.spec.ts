import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login } from "./helpers";
import { selectContaining, sign } from "./p2-helpers";

/** Gas test entry on PTW-0413 (seed): server-side live preview (AC31), quarantined detector not offered (AC33), save. */

const FARIS = "faris.anazi@example.com";

test("AC31/AC33 gas test entry: live preview from the server, quarantined detector hidden, passing test saved", async ({ page }) => {
  const api = await apiAs(FARIS);
  const projects = await getJson<{ items: { id: string; code: string }[] }>(api, "/api/v1/projects?q=ANIA-EXP");
  const pid = projects.items.find((p) => p.code === "ANIA-EXP")?.id ?? "";
  const permits = await getJson<{ items: { id: string; permit_no: string }[] }>(api, `/api/v1/projects/${pid}/permits?q=PTW-ANIA-EXP-2026-0413`);
  const permitId = permits.items.find((p) => p.permit_no === "PTW-ANIA-EXP-2026-0413")?.id ?? "";

  await login(page, FARIS);
  await page.goto(`/en/gas-tests/new?permit_id=${permitId}`);
  const det = page.getByTestId("gas-detector");
  await expect(det.locator("option", { hasText: "GD-ANIA-003" })).toBeAttached();
  await expect(det.locator("option", { hasText: "GD-ANIA-005" })).toHaveCount(0);
  await selectContaining(det, "GD-ANIA-003");
  await page.getByTestId("gas-type").selectOption("periodic");
  await selectContaining(page.getByTestId("gas-tester"), "Salem");

  await page.locator("#ge-temp").fill("31.5");
  const rows = page.getByTestId("gas-reading-row");
  const n = await rows.count();
  for (let i = 0; i < n; i++) {
    const r = rows.nth(i);
    await r.getByTestId("reading-o2_pct").fill("20.9");
    await r.getByTestId("reading-lel_pct").fill("0");
    await r.getByTestId("reading-h2s_ppm").fill("0");
    await r.getByTestId("reading-co_ppm").fill("0");
  }
  const preview = page.getByTestId("gas-preview");
  await expect(preview.getByTestId("gas-result")).toHaveAttribute("data-result", "pass", { timeout: 15_000 });

  await rows.first().getByTestId("reading-h2s_ppm").fill("1");
  await expect(preview.locator("[data-testid=preview-fails] [data-code=H2S_ABOVE_LIMIT]")).toBeVisible({ timeout: 15_000 });
  await rows.first().getByTestId("reading-h2s_ppm").fill("0");
  await expect(preview.getByTestId("gas-result")).toHaveAttribute("data-result", "pass", { timeout: 15_000 });

  await sign(page, "ge-sig");
  await page.getByTestId("save-gas-test").click();
  await expect(page).toHaveURL(/\/gas-tests\/[0-9a-f-]{36}/);
  await expect(page.getByTestId("gas-test-detail")).toBeVisible();
});
