import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

const TARIQ = "tariq.mutairi@example.com";
type Card = { id: string; engagement_code: string; scope: string; month: string };

/** Scorecard register, card page, contractor view, comments and disputes, finalisation (6g §3.2–§3.4, RK, DP, FN; AC 3, 4, 12, 15, 18, 19, 22–24). */
test.describe("Contractor scorecards", () => {
  const cards: Record<string, string> = {};
  test.beforeAll(async () => {
    const api = await apiAs(USERS.faisal);
    const pid = await projectId(api, "ANIA-EXP");
    const page = await getJson<{ items: Card[] }>(api, `/api/v1/projects/${pid}/scorecards?month=2026-09&scope=own&page_size=50`);
    for (const c of page.items) cards[c.engagement_code] = c.id;
    expect(Object.keys(cards)).toEqual(expect.arrayContaining(["RAWABI", "NAJD", "GULFPAVE", "SAHARA"]));
  });

  test("Faisal sees the September ranking, median and the capped NAJD card (SG1, SG3)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/scorecards?month=2026-09");
    const rank = (code: string) => page.locator(`[data-testid="sc-rank-row"][data-engagement="${code}"]`);
    await expect(rank("RAWABI")).toHaveAttribute("data-rank", "1");
    await expect(rank("GULFPAVE")).toHaveAttribute("data-rank", "2");
    await expect(rank("NAJD")).toHaveAttribute("data-rank", "3");
    await expect(rank("SAHARA")).toHaveAttribute("data-rank", "4");
    await expect(rank("NAJD").getByTestId("sc-rank-score")).toHaveText("80.9");
    await expect(rank("NAJD").getByTestId("sc-grade")).toHaveAttribute("data-grade", "C");
    await expect(rank("SAHARA").getByTestId("sc-watch-level")).toHaveAttribute("data-level", "watch");
    await expect(page.getByTestId("sc-median")).toContainText("82.5");
    await expect(page.getByTestId("sc-month-status")).toHaveAttribute("data-status", "issued");

    await rank("NAJD").getByRole("link").click();
    await expect(page.getByTestId("sc-no")).toHaveText("SCR-ANIA-EXP-NAJD-2026-09");
    await expect(page.getByTestId("sc-score")).toHaveText("80.9");
    await expect(page.getByTestId("sc-card-grade")).toHaveAttribute("data-grade", "C");
    await expect(page.locator('[data-testid="sc-cap"][data-cap="CP-2"]')).toContainText("INC-ANIA-EXP-2026-");
    await expect(page.getByTestId("sc-rank")).toHaveText("3 of 4");
    await expect(page.locator('[data-testid="sc-pillar"][data-pillar="LAG"]').getByTestId("sc-pillar-eff")).toHaveText("30.9");
    await expect(page.locator('[data-testid="sc-line"][data-metric="SM-NOTIF"]').getByTestId("sc-line-status")).toHaveAttribute("data-status", "source_not_live");
    // AC12: no field anywhere on the card to type points or a score.
    await expect(page.getByTestId("sc-lines").locator("input")).toHaveCount(0);
    await expect(page.getByTestId("sc-remark")).toHaveCount(1);
  });

  test("Tariq sees only NAJD and SAHARA with 'n of 4' and the median; RAWABI is not found (RK-2)", async ({ page }) => {
    await openAs(page, TARIQ, "/scorecards?month=2026-09");
    await expect(page.getByTestId("sc-rank-row")).toHaveCount(2);
    await expect(page.locator('[data-testid="sc-rank-row"][data-engagement="RAWABI"]')).toHaveCount(0);
    await page.goto(`/en/scorecards/${cards.SAHARA}`);
    await expect(page.getByTestId("sc-rank")).toHaveText("4 of 4");
    await expect(page.getByTestId("sc-card-median")).toContainText("82.5");
    await page.goto(`/en/scorecards/${cards.RAWABI}`);
    await expect(page.getByTestId("not-found")).toBeVisible();
  });

  test("Tariq disputes a NAJD line; Noura cannot exclude a metric and rejects it (DP-2, DP-4, DP-5)", async ({ page }) => {
    await openAs(page, TARIQ, `/scorecards/${cards.NAJD}`);
    await page.getByTestId("sc-new-remark").click();
    await page.getByTestId("sc-remark-kind-dispute").click();
    await page.getByTestId("sc-remark-target").selectOption("SM-CA-ONTIME");
    await page.getByTestId("sc-remark-reason-data_error").click();
    await page.getByTestId("sc-remark-text-input").fill("Two CAs closed on time were recorded late (TEST e2e).");
    await page.getByTestId("sc-remark-confirm").click();
    const dispute = page.locator('[data-testid="sc-remark"][data-kind="dispute"]').filter({ hasText: "recorded late (TEST e2e)" });
    await expect(dispute).toHaveAttribute("data-status", "open");
    await expect(dispute.getByTestId("fu-countdown")).toBeVisible();
    await expect(dispute.getByTestId("sc-resolve")).toHaveCount(0);

    await openAs(page, USERS.noura, `/scorecards/${cards.NAJD}`);
    const row = page.locator('[data-testid="sc-remark"]').filter({ hasText: "recorded late (TEST e2e)" });
    await row.getByTestId("sc-resolve").click();
    await expect(page.getByTestId("sc-resolution-choice-upheld_metric_excluded")).toHaveCount(0);
    await page.getByTestId("sc-resolution-choice-rejected").click();
    await page.getByTestId("sc-resolution-text").fill("Both CAs were closed after their due dates (TEST).");
    await page.getByTestId("sc-resolve-confirm").click();
    await expect(row).toHaveAttribute("data-status", "resolved");
    await expect(row.getByTestId("sc-resolution")).toHaveAttribute("data-resolution", "rejected");
  });

  test("Faisal cannot finalise September while the comment window is open (FN-1)", async ({ page }) => {
    await openAs(page, USERS.faisal, "/scorecards?month=2026-09");
    await page.getByTestId("sc-finalise").click();
    await page.getByTestId("sc-finalise-confirm").click();
    await expect(page.getByText("The comment window is still open")).toBeVisible();
  });

  test("Sarah sees August Final cards, not the Issued September ones; Ramesh has no scorecard menu (RK-4)", async ({ page }) => {
    await openAs(page, USERS.sarah, "/scorecards?month=2026-08");
    await expect(page.getByTestId("sc-month-status")).toHaveAttribute("data-status", "final");
    await expect(page.getByTestId("sc-rank-row")).toHaveCount(4);
    await expect(page.getByTestId("sc-finalise")).toHaveCount(0);
    await page.goto("/en/scorecards?month=2026-09");
    await expect(page.getByTestId("sc-card-row")).toHaveCount(0);
    await openAs(page, USERS.ramesh, "/");
    await expect(page.getByTestId("topbar")).toBeVisible();
    await expect(page.getByTestId("nav-sc-cards")).toHaveCount(0);
  });
});
