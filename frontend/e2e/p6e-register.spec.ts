import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, USERS } from "./helpers";
import { pickMulti } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

type Aspect = { id: string; aspect_no: string; status: string };

/** Aspects register, project permits and provider licences (6e §3.1–§3.3, ASP-1…ASP-3, PRM-1…PRM-4; 203, 204, 213). */
test.describe("Environmental register", () => {
  test("Noura adds an aspect with an engineering control and activates it", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-aspects");
    await expect(page.getByTestId("aspect-row").first()).toBeVisible();
    await page.getByTestId("aspect-new").click();
    await page.getByTestId("as-activity").selectOption({ index: 1 });
    await page.getByTestId("as-aspect").selectOption("dust_emission");
    await page.getByTestId("as-impact").selectOption({ index: 1 });
    await pickMulti(page, "as-sites", [/^S-LAND/]);
    await page.getByTestId("as-severity").fill("2");
    await page.getByTestId("as-likelihood").fill("2");
    await expect(page.getByTestId("as-score-preview")).toContainText("4");
    await page.getByTestId("as-add-control").click();
    await page.getByTestId("as-control-en").first().fill("Water the haul road every two hours");
    await page.getByTestId("as-control-level").first().selectOption("engineering");
    await page.getByTestId("aspect-save").click();
    await expect(page.getByRole("dialog")).toBeHidden();

    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const list = await getJson<{ items: Aspect[] }>(api, `/api/v1/projects/${pid}/env-aspects?status=draft&page_size=100`);
    const created = list.items.sort((a, b) => b.aspect_no.localeCompare(a.aspect_no))[0];
    expect(created).toBeTruthy();
    await page.goto(`/en/env-aspects/${created?.id}`);
    await expect(page.getByTestId("env-status").first()).toHaveAttribute("data-status", "draft");
    await page.getByTestId("aspect-activate").click();
    await page.getByTestId("aspect-confirm").click();
    await expect(page.getByTestId("env-status").first()).toHaveAttribute("data-status", "active");
  });

  test("Noura records a project permit; a contractor rep and the viewer see no write buttons", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-permits");
    await expect(page.getByTestId("permit-row").first()).toBeVisible();
    await page.getByTestId("permit-new").click();
    await page.getByTestId("pm-type").selectOption({ index: 1 });
    await page.getByTestId("pm-issuer").selectOption({ index: 1 });
    await page.getByTestId("pm-requirement").fill("E2E-HOARDING");
    await page.getByTestId("pm-reference").fill("NCEC-E2E-2026-114");
    await page.getByTestId("pm-valid-from").fill("2026-10-01");
    await page.getByTestId("pm-valid-to").fill("2027-09-30");
    await page.getByTestId("permit-save").click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByTestId("permits-table")).toContainText("NCEC-E2E-2026-114");

    for (const who of [USERS.ahmed, USERS.sarah]) {
      await openAs(page, who, "/env-permits");
      await expect(page.getByTestId("permit-row").first()).toBeVisible();
      await expect(page.getByTestId("permit-new")).toHaveCount(0);
    }
  });

  test("only the HSE Manager approves, suspends or blacklists a provider (213)", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-providers");
    await page.getByTestId("provider-row").filter({ hasText: "HAZMOVE" }).getByRole("link").first().click();
    await expect(page.getByTestId("licence-row").first()).toBeVisible();
    await expect(page.getByTestId("licence-new")).toBeVisible();
    await expect(page.getByTestId("provider-blacklist")).toHaveCount(0);
    await expect(page.getByTestId("provider-suspend")).toHaveCount(0);

    await openAs(page, USERS.faisal, "/env-providers");
    await page.getByTestId("provider-row").filter({ hasText: "HAZMOVE" }).getByRole("link").first().click();
    await expect(page.getByTestId("provider-blacklist")).toBeVisible();
    await expect(page.getByTestId("provider-suspend")).toBeVisible();
  });

  test("Arabic: the aspects register is right-to-left with Arabic labels", async ({ page }) => {
    await openAs(page, USERS.noura, "/env-aspects", "ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("الجوانب والآثار البيئية");
    await expect(page.getByTestId("aspect-row").first()).toBeVisible();
  });
});
