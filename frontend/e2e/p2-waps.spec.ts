import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, login, uid, USERS } from "./helpers";
import { createWorker, ensureCourse, ensureGenCourse, pickMulti, projectIds, recordInduction, selectContaining } from "./p2-helpers";

const SHOTS = "../docs/screenshots/phase-2";

function day(offset: number): string {
  const d = new Date(Date.now() + 3 * 3600_000 + offset * 86400_000); // Riyadh date
  return d.toISOString().slice(0, 10);
}

test.describe.serial("Phase 2 — work-area permits, the WAP board and ops events", () => {
  let supervisorNo = "";
  let wapUrl = "";
  const scope = `Taxiway B shoulder resurfacing ${uid()}`;

  test.beforeAll(async () => {
    const api = await apiAs(USERS.faisal);
    const ids = await projectIds(api);
    const gen = await ensureGenCourse(api, ids.pid);
    const air = await ensureCourse(api, ids.pid, "AIR", "airside", ["GEN"]);
    const sup = await createWorker(api, ids, `WAP Supervisor ${uid()}`);
    await recordInduction(api, ids.pid, sup.id, gen);
    await recordInduction(api, ids.pid, sup.id, air);
    supervisorNo = sup.worker_no;
  });

  async function fillWap(page: Page, from: string, to: string) {
    await page.goto("/en/waps/new");
    await selectContaining(page.locator("#wf-site"), "S-AIR");
    await selectContaining(page.locator("#wf-eng"), "RAWABI");
    await pickMulti(page, "wf-zones", [/Z-TWB/]);
    await page.locator("#wf-wsp").fill(`WSP-${uid()}`);
    await page.locator("#wf-scope-en").fill(scope);
    await page.locator("#wf-scope-ar").fill("إعادة رصف كتف الممر B");
    await page.locator("#wf-from").fill(from);
    await page.locator("#wf-to").fill(to);
    await page.getByTestId("wf-crew-add-search").fill(supervisorNo);
    await selectContaining(page.getByTestId("wf-crew-add"), supervisorNo);
    await expect(page.getByTestId("crew-row")).toHaveCount(1);
    await page.getByTestId("crew-role-0").selectOption("supervisor");
    await page.getByTestId("save-wap").click();
  }

  test("AC48 (UI): a permit longer than wap_max_days is refused", async ({ page }) => {
    await login(page, USERS.ahmed);
    await fillWap(page, day(1), day(31));
    await expect(page.getByTestId("form-error").or(page.locator("[role=alert]").filter({ hasText: /30/ })).first()).toBeVisible();
    await expect(page).toHaveURL(/\/waps\/new$/);
  });

  test("WA: a contractor rep requests a WAP; the permit issuer approves it", async ({ page }) => {
    await login(page, USERS.ahmed);
    await fillWap(page, day(0), day(10));
    await expect(page).toHaveURL(/\/waps\/[0-9a-f-]{36}$/);
    wapUrl = new URL(page.url()).pathname.replace(/^\/en/, "");
    await page.getByTestId("wap-submit").click();
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("wap-status")).toHaveAttribute("data-status", "submitted");

    await login(page, USERS.khalid);
    await page.goto(`/en${wapUrl}`);
    await page.getByTestId("wap-approve").click();
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("wap-status")).toHaveAttribute("data-status", /^(approved|active)$/);
    await expect(page.getByTestId("crew-member")).toHaveCount(1);
  });

  test("WA: the WAP board shows the permit under its zone; the print view has the QR", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/wap-board");
    const zone = page.locator("[data-testid=board-zone][data-zone='Z-TWB']");
    await expect(zone).toBeVisible();
    await expect(zone.getByTestId("board-wap").first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/wap-board-en.png`, fullPage: true });
    await page.goto(`/en${wapUrl}/print`);
    await expect(page.getByTestId("wap-print")).toContainText(scope);
    await expect(page.getByTestId("wap-print").locator("svg, img").first()).toBeVisible();
  });

  test("AC53 (UI): a viewer sees the crew count but no names", async ({ page }) => {
    await login(page, USERS.sarah);
    await page.goto(`/en${wapUrl}`);
    await expect(page.getByTestId("crew-hidden")).toBeVisible();
    await expect(page.getByTestId("crew-member")).toHaveCount(0);
    await expect(page.locator("main")).not.toContainText(supervisorNo);
  });

  test("WA-13: an LVP is declared on S-AIR and ended; any active Z-TWB permit is suspended and resumes only with the FOD check", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto(`/en${wapUrl}`);
    const wasActive = (await page.getByTestId("wap-status").getAttribute("data-status")) === "active";
    await page.goto("/en/ops-events");
    await page.getByTestId("declare-ops").click();
    await page.locator("#dc-type").selectOption("lvp");
    await selectContaining(page.locator("#dc-site"), "S-AIR");
    await expect(page.getByTestId("default-zones")).toContainText("Z-TWB");
    await page.locator("#dc-ref").fill(`ATC-${uid()}`);
    await page.getByTestId("declare-confirm").click();
    await expect(page).toHaveURL(/\/ops-events\/[0-9a-f-]{36}$/);
    if (wasActive) await expect(page.getByTestId("suspended-wap").first()).toBeVisible();
    await page.getByTestId("end-ops").click();
    await page.getByTestId("end-ops-confirm").click();
    await expect(page.getByTestId("end-ops")).toHaveCount(0);
    if (!wasActive) return;
    await page.goto(`/en${wapUrl}`);
    await expect(page.getByTestId("wap-status")).toHaveAttribute("data-status", "suspended");
    await expect(page.getByTestId("suspension-reason")).toBeVisible();
    await page.getByTestId("wap-resume").click();
    await page.getByTestId("fod-result").selectOption("clear");
    await page.getByTestId("fod-confirm").click();
    await expect(page.getByTestId("wap-status")).toHaveAttribute("data-status", "active");
  });
});
