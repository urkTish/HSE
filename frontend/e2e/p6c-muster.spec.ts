import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, userId, USERS } from "./helpers";
import { accessCard } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

/** Roll muster on a gated site, phone first: scan, counts, roll list and the printable sheet (6c MU-1…MU-9). */
test("phone: Omar scans an access card at the S-AIR muster; the sheet prints; the worker is an extra", async ({ page }) => {
  const noura = await apiAs(USERS.noura);
  const pid = await projectId(noura, "ANIA-EXP");
  const sites = await getJson<{ items: { id: string; code: string }[] }>(noura, `/api/v1/projects/${pid}/sites?page_size=50`);
  const site = sites.items.find((s) => s.code === "S-AIR");
  const omarId = await userId(noura, USERS.omar);
  const nouraId = await userId(noura, USERS.noura);
  const planned = await noura.post(`/api/v1/projects/${pid}/drills`, {
    data: {
      drill_type: "evacuation_full",
      scenario_code: "SC-FIRE",
      site_id: site?.id,
      zone_ids: [],
      planned_at: "2026-10-06T07:30:00Z",
      shift: "day",
      announced: true,
      suspend_permits: false,
      conductor_user_id: omarId,
      evaluator_user_ids: [nouraId],
      plan_note: "AOCC coordination ref AOCC-LOG-TEST-401.",
    },
  });
  expect(planned.ok(), await planned.text()).toBeTruthy();
  const drill = (await planned.json()) as { id: string };
  const omar = await apiAs(USERS.omar);
  const started = await omar.post(`/api/v1/drills/${drill.id}/transitions`, { data: { action: "start" } });
  expect(started.ok(), await started.text()).toBeTruthy();
  const { muster_id } = (await started.json()) as { muster_id: string };
  const deps = await getJson<{ items: { id: string; worker_no: string }[] }>(noura, `/api/v1/projects/${pid}/deployments?status=mobilised&page_size=1`);
  const dep = deps.items[0];
  const card = await accessCard(noura, dep?.id ?? "");

  await page.setViewportSize({ width: 390, height: 844 });
  await openAs(page, USERS.omar, `/musters/${muster_id}`);
  await expect(page.getByTestId("muster-status")).toHaveAttribute("data-status", "open");
  await expect(page.getByTestId("ms-camera")).toBeVisible();
  // MU-9: the paper fallback is printed while the muster is open (audited export).
  await page.getByTestId("muster-sheet").click();
  await expect(page.getByTestId("muster-sheet-page")).toContainText("MUS-ANIA-EXP-");
  await page.goBack();
  await page.getByTestId("ms-payload").fill(card.qr_payload);
  await page.getByTestId("ms-payload-go").click();
  await expect(page.getByTestId("ms-last")).toHaveAttribute("data-extra", "yes");
  await expect(page.getByTestId("mc-extras")).toContainText("1");
  await page.getByTestId("roll-accounted").click();
  await expect(page.locator(`[data-testid="roll-entry"][data-worker="${dep?.worker_no}"]`)).toHaveAttribute("data-state", "accounted");
});
