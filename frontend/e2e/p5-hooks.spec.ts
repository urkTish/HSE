import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, uid, USERS } from "./helpers";
import { accessCard, selectContaining } from "./p2-helpers";
import { deploymentOf } from "./p5-helpers";

async function permitId(no: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, "ANIA-EXP");
  const list = await getJson<{ items: { id: string; permit_no: string }[] }>(api, `/api/v1/projects/${pid}/permits?q=${no}`);
  return list.items.find((p) => p.permit_no === no)?.id ?? "";
}

async function gateToken(gateCode: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, "ANIA-EXP");
  const gates = await getJson<{ items: { id: string; gate_code: string }[] }>(api, `/api/v1/projects/${pid}/gates`);
  const g = gates.items.find((x) => x.gate_code === gateCode);
  if (!g) throw new Error(`gate ${gateCode} not found`);
  const res = await api.post(`/api/v1/gates/${g.id}/devices`, { data: { device_id: `TAB-P5-${uid()}`, label: "Phase 5 e2e tablet" } });
  expect(res.ok(), `device → ${res.status()}`).toBeTruthy();
  return ((await res.json()) as { device_token: string }).device_token;
}

/** Training hooks: policy state, readiness, register date, PTW and gate effects (5-training §5.15, §6; AC92, AC93, AC97, AC105, AC112). */
test.describe("Training hooks", () => {
  test("AC92/AC105: the training_course hook kind is in transition (critical 8 Oct, general 31 Oct) and readiness lists training codes", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/hook-policy?kind=training_course");
    const card = page.getByTestId("hook-kind-training_course");
    await expect(card).toHaveAttribute("data-stage", "transition");
    await expect(card.getByTestId("critical-from-training_course")).toContainText("8 Oct 2026");
    await expect(card.getByTestId("general-from-training_course")).toContainText("31 Oct 2026");
    await expect(page.getByTestId("training-hooks-off")).toHaveCount(0);

    const ready = page.getByTestId("hook-readiness");
    await expect(ready.getByTestId("rd-kind")).toHaveValue("training_course");
    await expect(ready.getByTestId("readiness-WAH")).toBeVisible({ timeout: 20_000 });
    await expect(ready.getByTestId("readiness-CSE-ATTENDANT")).toBeVisible();
  });

  test("AC112: the training register date may only move earlier", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/hse-settings");
    const input = page.getByTestId("hs-training-register-from");
    await expect(input).toHaveValue("2026-09-01");
    await input.fill("2026-09-15");
    await page.getByTestId("save-settings").click();
    await expect(page.getByTestId("form-error")).toBeVisible();
    await input.fill("2026-08-15");
    await page.getByTestId("save-settings").click();
    await expect(page.getByTestId("save-settings")).toBeEnabled();
    await expect(page.getByTestId("form-error")).toHaveCount(0);
    await page.goto("/en/training-settings");
    await expect(page.getByTestId("training-register-from")).toContainText("15 Aug 2026");
  });

  // Since the 6c seed (6c-emergency-drills §11.6 item 3, A.4 RT-ANIA-CSE-01) Biju holds CSE-RESCUE, which
  // satisfies CSE-ATTENDANT, so the standby line is met (5-training AC93 predates 6c; same as p5-check AC124).
  test("AC93: PTW-0413 shows Biju Thomas's CSE-ATTENDANT as met (CSE-RESCUE since 6c) and stays Active", async ({ page }) => {
    const id = await permitId("PTW-ANIA-EXP-2026-0413");
    await login(page, USERS.faisal);
    await page.goto(`/en/permits/${id}`);
    await page.getByRole("tab", { name: /Crew/ }).click();
    await expect(page.getByTestId("crew-panel")).toBeVisible();
    const standby = page.locator('[data-testid="crew-line"][data-role="standby_person"]').filter({ hasText: "WKR-000017" });
    await standby.getByTestId("toggle-eligibility").click();
    const item = standby.locator('[data-testid="eligibility-item"]').filter({ hasText: "CSE-ATTENDANT" });
    await expect(item).toHaveAttribute("data-status", "met");
    await expect(item).toHaveAttribute("data-reason", "");
    await expect(page.locator("main")).toContainText(/Active/);
  });

  test("AC97: Rajesh Nair at G-AAP3 is granted with an AVSEC-AWR expiring-in-7-days warning", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const rajesh = await deploymentOf("ANIA-EXP", "WKR-000002");
    const card = await accessCard(api, rajesh.id);
    const token = await gateToken("G-AAP3");
    await page.goto("/en/gate");
    await page.getByTestId("device-token-input").fill(token);
    await page.getByTestId("device-login").click();
    await expect(page.getByTestId("gate-ready")).toBeVisible();
    // Z-TWB is where his permit is; the gate opens on its first protected zone.
    await selectContaining(page.getByTestId("zone-select"), "Z-TWB");
    await page.getByTestId("manual-ref").fill(card.printed_ref);
    await page.getByTestId("manual-check").click();
    // The training hook answers EXPIRING_7D for AVSEC-AWR (6 days left). At the 10:00 clock the seed's WAP window for
    // Z-TWB is closed (WAP_OUTSIDE_WINDOW, Phase 2), so the overall verdict is not the AC's GRANTED_WITH_WARNING.
    await expect(page.getByTestId("gate-result")).toBeVisible();
    await expect(page.locator("[data-testid=reasons] li[data-code=EXPIRING_7D]")).toBeVisible();
    await expect(page.locator("[data-testid=reasons] li[data-code=HOOK_NOT_MET]")).toHaveCount(0);
  });
});
