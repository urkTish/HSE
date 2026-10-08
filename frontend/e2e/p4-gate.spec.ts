import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, uid, USERS } from "./helpers";

interface Gate {
  id: string;
  gate_code: string;
  gate_type: string;
}

async function deviceToken(gateCode: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, "ANIA-EXP");
  const gates = await getJson<{ items: Gate[] }>(
    api,
    `/api/v1/projects/${pid}/gates`,
  );
  const g = gates.items.find((x) => x.gate_code === gateCode);
  if (!g) throw new Error(`gate ${gateCode} not found`);
  const res = await api.post(`/api/v1/gates/${g.id}/devices`, {
    data: { device_id: `TAB-P4-${uid()}`, label: "Phase 4 e2e tablet" },
  });
  expect(res.ok(), `device → ${res.status()}`).toBeTruthy();
  return ((await res.json()) as { device_token: string }).device_token;
}

async function deviceScreen(page: Page, token: string, gateCode: string) {
  await page.goto("/en/gate");
  await page.getByTestId("device-token-input").fill(token);
  await page.getByTestId("device-login").click();
  await expect(page.getByTestId("gate-code")).toHaveText(gateCode);
  await expect(page.getByTestId("gate-ready")).toBeVisible();
}

async function check(page: Page, ref: string) {
  if (await page.getByTestId("next-scan").isVisible())
    await page.getByTestId("next-scan").click();
  await page.getByTestId("manual-ref").fill(ref);
  await page.getByTestId("manual-check").click();
  return page.getByTestId("gate-result");
}

/** Gate equipment check (spec 4 §5.12; AC94, AC95). The guard sees an equipment card, never personal data. */
test.describe("Gate equipment check", () => {
  test("AC94: RW-MEWP-07 is DENIED out of service; SH-TH-02's old sticker is DENIED as revoked", async ({
    page,
  }) => {
    const token = await deviceToken("G-ANIA-01");
    await deviceScreen(page, token, "G-ANIA-01");
    const res = await check(page, "ANIA-EXP-RW-MEWP-07");
    await expect(res).toHaveAttribute("data-result", "DENIED");
    await expect(
      page.locator(
        "[data-testid=reasons] li[data-code=EQUIPMENT_OUT_OF_SERVICE]",
      ),
    ).toBeVisible();
    const card = page.getByTestId("equipment-card");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-colour", "red");

    const res2 = await check(page, "ANIA-EXP-SH-TH-02");
    await expect(res2).toHaveAttribute("data-result", "DENIED");
    await expect(
      page.locator("[data-testid=reasons] li[data-code=CREDENTIAL_REVOKED]"),
    ).toBeVisible();
    await expect(
      page.locator("[data-testid=reasons] li[data-code=EQUIPMENT_BLACKLISTED]"),
    ).toHaveCount(0);
  });

  test("AC95: RW-MC-03 at the airside pre-check gate is GRANTED with 'also scan the vehicle sticker'", async ({
    page,
  }) => {
    const token = await deviceToken("G-AAP3");
    await deviceScreen(page, token, "G-AAP3");
    const res = await check(page, "ANIA-EXP-RW-MC-03");
    await expect(res).toHaveAttribute("data-result", /^GRANTED/);
    await expect(
      page.locator(
        "[data-testid=reasons] li[data-code=ALSO_SCAN_VEHICLE_STICKER]",
      ),
    ).toBeVisible();
    const card = page.getByTestId("equipment-card");
    await expect(card).toContainText("AICC-EQ-TEST-25-1106");
    await expect(card).toContainText("50.000 t");
  });
});
