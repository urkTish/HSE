import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, userId, USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";
import { openAs, USERS6 } from "./p6a-helpers";

/** Drill programme and the drill lifecycle: plan → start (muster, PE-2 suspensions) → counts → timings → conduct → receiver resume → evaluation (6c §4.4, DR-1…DR-9, MU-3, PE-2). */

/** "YYYY-MM-DDTHH:MM[:SS]" + minutes, as a datetime-local value. */
function plus(v: string, min: number): string {
  const d = new Date(`${v.length === 16 ? `${v}:00` : v}Z`);
  return new Date(d.getTime() + min * 60_000).toISOString().slice(0, 16);
}

test.describe.serial("Drills", () => {
  let drillPath = "";

  test("programme lines and the evaluated DRL-ANIA-EXP-2026-031 with its CAs", async ({ page }) => {
    await openAs(page, USERS.noura, "/drill-programme");
    await expect(page.locator('[data-testid="line-row"][data-type="cse_rescue"]')).toBeVisible();
    await expect(page.getByTestId("line-plan").first()).toBeVisible();

    await page.goto("/en/drills");
    await page.locator('[data-testid="drill-row"][data-no="DRL-ANIA-EXP-2026-031"]').getByRole("link").click();
    await expect(page.getByTestId("drill-result").first()).toHaveAttribute("data-result", "unsatisfactory");
    await expect(page.locator('[data-testid="measure"][data-key="headcount_min"]').getByTestId("measure-headcount_min")).toHaveAttribute("data-over", "yes");
    await expect(page.getByTestId("finding-ca").first()).toContainText("CA-ANIA-EXP-2026-");
    await expect(page.getByTestId("drill-start")).toHaveCount(0);
  });

  test("Noura plans an S-LAND evacuation with Fahad conducting", async ({ page }) => {
    await openAs(page, USERS.noura, "/drills");
    await page.getByTestId("drill-new").click();
    await page.getByTestId("dp-type").selectOption("evacuation_full");
    await selectContaining(page.getByTestId("dp-site"), "S-LAND");
    await page.getByTestId("dp-at").fill("2026-10-06T10:30");
    await selectContaining(page.getByTestId("dp-conductor"), "Fahad");
    await pickMulti(page, "dp-evaluators", [/Noura/]);
    await expect(page.getByTestId("dp-suspend")).toBeChecked();
    await page.getByTestId("drill-plan-confirm").click();
    await expect(page).toHaveURL(/\/drills\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("drill-status")).toHaveAttribute("data-status", "planned");
    drillPath = page.url().replace(/^.*\/en/, "");
  });

  test("Fahad starts it, counts the muster on his phone, records timings and conducts it", async ({ page }) => {
    await openAs(page, USERS6.fahad, drillPath);
    await page.getByTestId("drill-start").click();
    await page.getByTestId("drill-start-confirm").click();
    await expect(page.getByTestId("drill-status")).toHaveAttribute("data-status", "in_progress");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByTestId("drill-muster-open").click();
    await expect(page.getByTestId("muster-status")).toHaveAttribute("data-status", "open");
    const raw = page.locator('[data-testid="count-row"][data-eng="RAWABI"]');
    await raw.getByTestId("cr-expected").fill("10");
    await raw.getByTestId("cr-accounted").fill("9");
    await page.getByTestId("counts-save").click();
    await expect(raw).toHaveAttribute("data-outstanding", "1");
    await page.getByTestId("rz-add").click();
    await page.getByTestId("rz-reason-0-off_site_confirmed").click();
    await page.getByTestId("counts-save").click();
    await expect(page.getByTestId("muster-status")).toHaveAttribute("data-status", "reconciled");
    await expect(page.getByTestId("mc-missing")).toHaveAttribute("data-n", "0");

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/en${drillPath}`);
    await expect(page.getByTestId("tl-alarm_at")).toHaveValue(/^2026-/);
    const alarm = await page.getByTestId("tl-alarm_at").inputValue();
    await page.getByTestId("tl-evacuation_complete_at").fill(plus(alarm, 4));
    await page.getByTestId("tl-all_clear_at").fill(plus(alarm, 12));
    await page.getByTestId("timings-save").click();
    await expect(page.getByTestId("measure-evac_min")).toHaveAttribute("data-over", "no");
    await page.getByTestId("drill-conduct").click();
    await page.getByTestId("drill-conduct-confirm").click();
    await expect(page.getByTestId("drill-status")).toHaveAttribute("data-status", "conducted");
  });

  test("Ramesh resumes his permit suspended for the drill (PE-2)", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const ramesh = await userId(api, USERS.ramesh);
    const list = await getJson<{ items: { id: string; status_reason: string | null; receiver: { id: string } }[] }>(api, `/api/v1/projects/${pid}/permits?status=suspended&page_size=100`);
    const permit = list.items.find((p) => p.status_reason === "emergency_drill" && p.receiver.id === ramesh);
    expect(permit, "a permit of Ramesh suspended by the drill").toBeTruthy();

    await openAs(page, USERS.ramesh, `/permits/${permit?.id}`);
    await page.getByTestId("act-drill_resume").click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByTestId("drill-resume-hint")).toBeVisible();
    const rows = dlg.getByTestId("crew-present-row");
    for (let i = 0; i < (await rows.count()); i++) await rows.nth(i).getByTestId("crew-present-check").check();
    if (await dlg.getByTestId("st-temp").count()) await dlg.getByTestId("st-temp").fill("33.0");
    await dlg.getByTestId("step-confirm").click();
    await expect(page.getByTestId("permit-status")).toHaveAttribute("data-status", "active");
  });

  test("Noura evaluates it with one failed criterion: unsatisfactory with a CA", async ({ page }) => {
    await openAs(page, USERS.noura, drillPath);
    const crit = page.getByTestId("eval-criterion");
    await expect(crit.first()).toBeVisible();
    const codes = await crit.evaluateAll((els) => els.map((e) => e.getAttribute("data-code") ?? ""));
    expect(codes).toContain("DC02");
    for (const c of codes) await page.getByTestId(`ev-${c}-${c === "DC02" ? "fail" : "pass"}`).click();
    await page.getByTestId("ev-summary").fill("Route via the north stair was blocked by stored material.");
    await page.getByTestId("ev-submit").click();
    await expect(page.getByTestId("eval-view")).toBeVisible();
    await expect(page.getByTestId("drill-result").first()).toHaveAttribute("data-result", "unsatisfactory");
    await expect(page.getByTestId("finding-ca").first()).toContainText("CA-ANIA-EXP-");
  });
});
