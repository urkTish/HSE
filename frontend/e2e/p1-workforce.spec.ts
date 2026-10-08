import { type APIRequestContext } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, selectByPrefix, USERS } from "./helpers";

const CONTRACTOR_SITES: [string, string][] = [
  ["RAWABI", "S-AIR"],
  ["NAJD", "S-LAND"],
  ["GULFPAVE", "S-AIR"],
  ["SAHARA", "S-LAND"],
];

function csv(rows: string[][]): Buffer {
  const head = "work_date,project_code,site_code,zone_code,contractor_code,shift,headcount,man_hours,no_work,remarks";
  return Buffer.from([head, ...rows.map((r) => r.join(","))].join("\n"), "utf8");
}

/** Past, unlocked, in-mobilisation dates after the seed window (seed ends 2026-09-30). */
function rows(shift: string, days = [1, 2, 3, 4, 5]): string[][] {
  const out: string[][] = [];
  for (const d of days) for (const [c, s] of CONTRACTOR_SITES) out.push([`2026-10-0${d}`, "ANIA-EXP", s, "", c, shift, "10", "100", "N", ""]);
  return out;
}

async function ids(api: APIRequestContext, pid: string) {
  const sites = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects/${pid}/sites?page_size=100`);
  const engs = await getJson<{
    items: { id: string; contractor: { short_code: string } }[];
  }>(api, `/api/v1/projects/${pid}/engagements?page_size=100`);
  return {
    site: (code: string) => sites.items.find((s) => s.code === code)?.id ?? "",
    eng: (code: string) => engs.items.find((e) => e.contractor.short_code === code)?.id ?? "",
  };
}

test.describe("Workforce & import", () => {
  test("AC3: dry-run shows the E08 row, writes nothing and blocks commit", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/workforce/import");
    const file = csv([...rows("day"), ["2026-10-01", "ANIA-EXP", "S-LAND", "", "NAJD", "night", "10", "200", "N", ""]]);
    await page.getByTestId("import-file").setInputFiles({
      name: "returns.csv",
      mimeType: "text/csv",
      buffer: file,
    });
    await page.getByTestId("import-check").click();
    await expect(page.getByTestId("import-report")).toBeVisible();
    await expect(page.getByTestId("count-rows_error")).toContainText("1");
    const bad = page.locator("[data-testid=import-row][data-status=error]");
    await expect(bad).toHaveCount(1);
    await expect(bad).toHaveAttribute("data-row", "21");
    await expect(bad).toContainText("E08");
    await expect(page.getByTestId("commit-blocked")).toBeVisible();
    await expect(page.getByTestId("import-commit")).toBeDisabled();
  });

  test("AC4: a clean dry-run commits as Submitted", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/workforce/import");
    await page.getByTestId("import-file").setInputFiles({
      name: "night.csv",
      mimeType: "text/csv",
      buffer: csv(rows("night")),
    });
    await page.getByTestId("import-check").click();
    await expect(page.getByTestId("count-rows_error")).toContainText("0");
    await page.getByTestId("import-commit").click();
    await expect(page.getByTestId("count-rows_inserted")).toContainText("20");
    await page.goto("/en/workforce?date_from=2026-10-01&date_to=2026-10-05&shift=night");
    await expect(page.getByTestId("return-row").first()).toBeVisible();
  });

  test("AC2: a second return with the same key is rejected DUPLICATE_RETURN", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    const id = await ids(api, ania);
    const body = {
      site_id: id.site("S-AIR"),
      engagement_id: id.eng("GULFPAVE"),
      work_date: "2026-10-04",
      shift: "all",
      headcount: 5,
      man_hours: 50,
      no_work: false,
    };
    const first = await api.post(`/api/v1/projects/${ania}/workforce-returns`, {
      data: body,
    });
    expect(first.status(), await first.text()).toBe(201);
    await login(page, USERS.noura);
    await page.goto("/en/workforce/new");
    await page.locator("#work_date").fill("2026-10-04");
    await selectByPrefix(page.locator("#site_id"), "S-AIR");
    await selectByPrefix(page.locator("#engagement_id"), "GULFPAVE");
    await page.locator("#shift").selectOption("all");
    await page.locator("#headcount").fill("5");
    await page.locator("#man_hours").fill("50");
    await page.getByTestId("save").click();
    await expect(
      page
        .getByRole("alert")
        .or(page.locator("[role=status]"))
        .filter({ hasText: /already exists/ })
        .first(),
    ).toBeVisible();
  });

  test("AC10: no_work = Y with headcount 5 is E13", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/workforce/import");
    await page.getByTestId("import-file").setInputFiles({
      name: "e13.csv",
      mimeType: "text/csv",
      buffer: csv([["2026-10-02", "ANIA-EXP", "S-LAND", "", "SAHARA", "all", "5", "0", "Y", ""]]),
    });
    await page.getByTestId("import-check").click();
    await expect(page.locator("[data-testid=import-row][data-status=error]")).toContainText("E13");
  });

  test("AC7: a locked month rejects import rows with E11", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const ania = await projectId(api, "ANIA-EXP");
    const months = await getJson<{ items: { month: string; status: string }[] } | { month: string; status: string }[]>(api, `/api/v1/projects/${ania}/workforce-months?year=2026`);
    const list = Array.isArray(months) ? months : months.items;
    const aug = list.find((m) => m.month.startsWith("2026-08"));
    await login(page, USERS.faisal);
    if (aug && aug.status !== "locked") {
      await page.goto("/en/workforce/months");
      await page.getByTestId(`lock-${aug.month}`).click();
      await page.getByTestId("month-confirm").click();
      await expect(page.getByTestId(`unlock-${aug.month}`)).toBeVisible();
    }
    await page.goto("/en/workforce/import");
    await page.getByTestId("import-file").setInputFiles({
      name: "aug.csv",
      mimeType: "text/csv",
      buffer: csv([["2026-08-20", "ANIA-EXP", "S-LAND", "", "SAHARA", "night", "3", "30", "N", ""]]),
    });
    await page.getByTestId("import-mode").selectOption("upsert");
    await page.getByTestId("import-check").click();
    await expect(page.locator("[data-testid=import-row][data-status=error]")).toContainText("E11");
  });
});
