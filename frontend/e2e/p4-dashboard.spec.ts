import { expect, test } from "./fixtures/test";
import { apiAs, login, projectId, USERS } from "./helpers";

const SEP = "period=month&anchor=2026-09-15";

/** Phase 4 dashboard additions: K-72…K-81 tiles, the certification band and its filters (spec 4 §6.7, §8.1; AC103 Z11). */
test.describe("Dashboard — certification", () => {
  test("AC103: September 2026 KPIs equal Z11 for ANIA-EXP and the certification band shows the seed state", async ({
    page,
  }) => {
    await login(page, USERS.noura);
    await page.goto(`/en?${SEP}`);
    await expect(page.getByTestId("period-label")).toHaveText("Sep 2026");
    const tile = (m: string) =>
      page
        .locator(`[data-testid=kpi-tile][data-metric="${m}"]`)
        .getByTestId("tile-value");
    await expect(tile("K-72")).toHaveText("97.3 %");
    await expect(tile("K-74")).toHaveText("3");
    await expect(tile("K-76")).toHaveText("95.0 %");
    await expect(tile("K-80")).toHaveText("83.3 %");
    await expect(tile("K-81")).toHaveText("96.9 %");

    const band = page.getByTestId("cert-band");
    await expect(band).toBeVisible();
    await expect(band.getByTestId("cert-band-out-of-service")).toContainText(
      "3",
    );
    await expect(
      band.locator('[data-testid=headline-value][data-metric="K-73"]'),
    ).toContainText("11");
    await expect(
      band.locator('[data-testid=headline-value][data-metric="K-77"]'),
    ).toContainText("17");
    const hooks = band.getByTestId("cert-band-hooks").locator("li");
    await expect(hooks.first()).toBeVisible();
    await expect(page.getByTestId("cert-charts")).toBeVisible();
  });

  test("AC103: RBT-52 shows K-72 98.0 % and K-81 100.0 %; equipment-category and certificate-type filters are offered", async ({
    page,
  }) => {
    const api = await apiAs(USERS.faisal);
    const rbt = await projectId(api, "RBT-52");
    await login(page, USERS.faisal);
    await page.getByTestId("project-switcher").selectOption(rbt);
    await page.goto(`/en?${SEP}`);
    const tile = (m: string) =>
      page
        .locator(`[data-testid=kpi-tile][data-metric="${m}"]`)
        .getByTestId("tile-value");
    await expect(tile("K-72")).toHaveText("98.0 %");
    await expect(tile("K-81")).toHaveText("100.0 %");
    await expect(page.locator("#f-eqc")).toBeAttached();
    await expect(page.locator("#f-ctype")).toBeAttached();
  });
});
