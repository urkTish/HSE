import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, PASSWORD, USERS } from "./helpers";

/** Phase 3 checks on the Appendix A PTW seed that do not depend on the seed clock. */

const P3 = {
  majed: "majed.shammari@example.com",
  ibrahim: "ibrahim.saleh@example.com",
  nasser: "nasser.shahrani@example.com",
  faris: "faris.anazi@example.com",
};

async function idOf(email: string, project: string, path: string, key: string, value: string): Promise<string> {
  const api = await apiAs(email);
  const projects = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects?q=${project}`);
  const pid = projects.items.find((p) => p.code === project)?.id ?? "";
  const list = await getJson<{ items: Record<string, string>[] }>(api, `/api/v1/projects/${pid}/${path}?q=${encodeURIComponent(value)}&page_size=50`);
  const row = list.items.find((x) => x[key] === value || String(x[key] ?? "").startsWith(value));
  if (!row) throw new Error(`${value} not found in ${path}`);
  return row.id ?? "";
}

test("AC19/AC96 the viewer sees crew counts and roles only, never names or worker numbers", async ({ page }) => {
  const id = await idOf(USERS.faisal, "ANIA-EXP", "permits", "permit_no", "PTW-ANIA-EXP-2026-0412");
  await login(page, USERS.sarah);
  await page.goto(`/en/permits/${id}?tab=crew`);
  await expect(page.getByTestId("panel-crew")).toBeVisible();
  await expect(page.getByTestId("crew-counts")).toBeVisible();
  const main = await page.locator("main").innerText();
  expect(main).not.toMatch(/WKR-\d+/);
  expect(main).not.toMatch(/Prakash|Ahmed Raza/);
  await page.goto("/en/ptw-board");
  await expect(page.getByTestId("board-permit").first()).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(/WKR-\d+|Prakash|Ahmed Raza/);
});

test("AC25 the permit print carries a PT print token and no ID number or nationality", async ({ page }) => {
  const id = await idOf(USERS.faisal, "ANIA-EXP", "permits", "permit_no", "PTW-ANIA-EXP-2026-0413");
  await login(page, USERS.faisal);
  await page.goto(`/en/permits/${id}/print`);
  const sheet = page.getByTestId("permit-print");
  await expect(sheet.getByTestId("print-permit-no")).toContainText("PTW-ANIA-EXP-2026-0413");
  await expect(sheet.getByTestId("print-ref")).toBeVisible();
  expect(await sheet.getByTestId("print-qr").getAttribute("data-payload")).toMatch(/^HSE2:PT:[A-Za-z0-9_-]{22}$/);
  await expect(sheet.getByTestId("audit-hash")).toBeVisible();
  expect(await sheet.innerText()).not.toMatch(/iqama|nationality|الجنسية|\b2\d{9}\b/i);
});

test("AC40 de-isolation of ISO-0061 is blocked by PTW-0405 and the personal locks", async ({ page }) => {
  const id = await idOf(USERS.faisal, "ANIA-EXP", "isolations", "iso_no", "ISO-ANIA-EXP-2026-0061");
  await login(page, P3.nasser);
  await page.goto(`/en/isolations/${id}`);
  const blockers = page.getByTestId("deisolation-blockers");
  await expect(blockers).toContainText("PTW-ANIA-EXP-2026-0405");
  await expect(blockers).toContainText("P-ANIA-1101");
  await page.getByTestId("iso-deisolation_requested").click();
  await page.getByRole("dialog").getByTestId("iso-step-confirm").click();
  await expect(page.getByRole("dialog").getByTestId("form-error")).toHaveAttribute("data-code", "DEISOLATION_BLOCKED");
});

test("AC46 SIMOPS coordination signed by both issuers and the area authority clears the 0290 blocker", async ({ page }) => {
  const sim = await idOf(P3.majed, "RBT-52", "simops-conflicts", "conflict_no", "SIM-RBT-52-2026-0021");
  const permit = await idOf(P3.majed, "RBT-52", "permits", "permit_no", "PTW-RBT-52-2026-0290");
  await login(page, P3.majed);
  await page.goto(`/en/permits/${permit}`);
  await expect(page.locator("[data-testid=blocker][data-code=SIMOPS_COORDINATION_REQUIRED]")).toBeVisible();

  await page.goto(`/en/simops-conflicts/${sim}`);
  await expect(page.getByTestId("conflict-status")).toHaveAttribute("data-status", "open");
  await page.getByTestId("create-coordination").click();
  const dlg = page.getByRole("dialog");
  await dlg.getByTestId("co-agreed-en").fill("Debris netting at the L38 edge; no work above the landing zone during the lift; banksman on L38.");
  await dlg.getByTestId("add-cosigner").click();
  await dlg.getByTestId("co-pw-0").fill(PASSWORD);
  await dlg.getByTestId("save-coordination").click();
  await expect(dlg).toHaveCount(0);
  await expect(page.getByTestId("coordination-signer").filter({ has: page.locator("[data-signed=false]") })).toHaveCount(0);
  await expect(page.getByTestId("conflict-status")).toHaveAttribute("data-status", "coordinated");

  await page.goto(`/en/permits/${permit}`);
  await expect(page.locator("[data-testid=blocker][data-code=SIMOPS_COORDINATION_REQUIRED]")).toHaveCount(0);
});

test("dashboard shows the PTW band for the HSE Manager", async ({ page }) => {
  await login(page, USERS.faisal);
  await page.goto("/en");
  const band = page.getByTestId("ptw-band");
  await expect(band).toBeVisible({ timeout: 30_000 });
  await expect(band.getByTestId("ptw-band-active")).toBeVisible();
});

test("permit detail on a phone in Arabic: RTL, no horizontal scroll, LTR permit numbers", async ({ page }) => {
  const id = await idOf(USERS.faisal, "ANIA-EXP", "permits", "permit_no", "PTW-ANIA-EXP-2026-0413");
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, P3.faris, "ar");
  await page.goto(`/ar/permits/${id}`);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByTestId("permit-no")).toContainText("PTW-ANIA-EXP-2026-0413");
  await expect(page.getByTestId("permit-actions")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  expect(await page.locator("main").innerText()).not.toMatch(/\b(permitDetail|permits|ptw|enums)\.[a-zA-Z_]+/);
});
