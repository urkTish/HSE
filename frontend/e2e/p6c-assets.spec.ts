import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, USERS } from "./helpers";
import { openAs, USERS6 } from "./p6a-helpers";

type Asset = { id: string; asset_tag: string; sticker_payload: string | null };

/** Emergency equipment register and the phone-first check (6c §3.8, §3.9, EA-1…EA-7). */
test.describe("Emergency equipment", () => {
  test("phone: Fahad scans the FE-SLAND-0142 sticker and records a passing check", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    let fe: Asset | undefined;
    for (let p = 1; !fe && p <= 3; p++) {
      const list = await getJson<{ items: Asset[] }>(api, `/api/v1/projects/${pid}/emergency-assets?asset_type=fire_extinguisher&page_size=200&page=${p}`);
      fe = list.items.find((a) => a.asset_tag === "FE-SLAND-0142");
    }
    expect(fe?.sticker_payload).toBeTruthy();

    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS6.fahad, "/emergency-asset-checks/new");
    await page.getByTestId("ce-payload").fill(fe?.sticker_payload ?? "");
    await page.getByTestId("ce-payload-go").click();
    await page.getByTestId("ce-scan-type").selectOption("fire_extinguisher");
    const items = page.getByTestId("ce-item");
    await expect(items.first()).toBeVisible();
    const codes = await items.evaluateAll((els) => els.map((e) => e.getAttribute("data-code") ?? ""));
    expect(codes).toContain("EC03");
    for (const c of codes) await page.getByTestId(`ce-${c}-pass`).click();
    await page.getByTestId("ce-save").click();
    await expect(page.getByTestId("check-saved")).toHaveAttribute("data-result", "pass");
  });

  test("register: a failed critical item on AED-SAIR-01 raises a CA and makes it not ready", async ({ page }) => {
    await openAs(page, USERS.noura, "/emergency-assets?type=aed");
    const row = page.locator('[data-testid="asset-row"][data-tag="AED-SAIR-01"]');
    await expect(row).toBeVisible();
    await row.getByTestId("asset-check").click();
    await expect(page.getByTestId("ce-tag")).toHaveText("AED-SAIR-01");
    await expect(page.getByTestId("ce-manual-note")).toBeVisible();
    const items = page.getByTestId("ce-item");
    await expect(items.first()).toBeVisible();
    const codes = await items.evaluateAll((els) => els.map((e) => e.getAttribute("data-code") ?? ""));
    for (const c of codes) await page.getByTestId(`ce-${c}-${c === "EC01" ? "fail" : "pass"}`).click();
    await page.getByTestId("ce-save").click();
    await expect(page.getByTestId("check-saved")).toHaveAttribute("data-result", "fail");
    await expect(page.getByTestId("saved-ca")).toContainText("CA-ANIA-EXP");

    await page.goto("/en/emergency-assets?type=aed");
    await expect(page.locator('[data-testid="asset-row"][data-tag="AED-SAIR-01"]')).toHaveAttribute("data-ready", "no");
  });

  test("the client viewer sees the register without check, edit or retire buttons", async ({ page }) => {
    await openAs(page, USERS.sarah, "/emergency-assets");
    await expect(page.getByTestId("asset-row").first()).toBeVisible();
    await expect(page.getByTestId("asset-check")).toHaveCount(0);
    await expect(page.getByTestId("asset-retire")).toHaveCount(0);
    await expect(page.getByTestId("asset-new")).toHaveCount(0);
  });
});
