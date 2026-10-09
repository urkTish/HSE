import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, selectByPrefix, sql, USERS } from "./helpers";
import { makePng } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

/** Start an unplanned GSI run at S-LAND on the phone. */
async function startGsi(page: Page, zone: string, eng: string): Promise<string[]> {
  await selectByPrefix(page.getByTestId("run-template-select"), "GSI");
  await selectByPrefix(page.getByTestId("run-site"), "S-LAND");
  await selectByPrefix(page.getByTestId("run-zone"), zone);
  await selectByPrefix(page.getByTestId("run-eng"), eng);
  await page.getByTestId("run-start").click();
  const items = page.getByTestId("run-item");
  await expect(items.first()).toBeVisible();
  return items.evaluateAll((els) => els.map((e) => e.getAttribute("data-code") ?? ""));
}

/** Phone checklist execution (6d §3.3, EXE-1…EXE-9, FND-7, FND-9, AC59). */
test.describe("Checklist execution", () => {
  test("phone: a failed stop-work item raises an order, which is released once the CA is under way", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS.noura, "/field-inspections/new");
    const codes = await startGsi(page, "Z-PIERB", "NAJD");
    expect(codes).toContain("GSI-05");
    // Airside-only items are hidden on a landside zone.
    expect(codes).not.toContain("GSI-23");
    for (const c of codes) if (c !== "GSI-05") await page.getByTestId(`ans-${c}-compliant`).click();
    await expect(page.getByTestId("run-submit")).toBeDisabled();

    await page.getByTestId("ans-GSI-05-non_compliant").click();
    await expect(page.getByTestId("stop-now")).toBeVisible();
    await expect(page.getByTestId("stop-fields")).toBeVisible();
    await page.getByTestId("note-GSI-05").fill("Open slab edge at grid C-14, no barrier");
    await page.getByTestId("photo-GSI-05-input").setInputFiles({ name: "edge.png", mimeType: "image/png", buffer: makePng(64) });
    await expect(page.getByTestId("photo-GSI-05")).toHaveAttribute("data-count", "1");
    await page.getByTestId("sw-activity").fill("Formwork at level 3 slab edge");
    await page.getByTestId("run-submit").click();

    const done = page.getByTestId("run-done");
    await expect(done).toHaveAttribute("data-result", "fail");
    const stopText = (await page.getByTestId("done-stop").textContent()) ?? "";
    const orderNo = /SWO-[A-Z0-9-]+/.exec(stopText)?.[0] ?? "";
    expect(orderNo).toMatch(/^SWO-ANIA-EXP-2026-/);
    await expect(page.getByTestId("done-cas")).toContainText("CA-ANIA-EXP");

    // The inspection page shows the checklist, score and findings.
    await page.getByTestId("done-open").click();
    await expect(page.getByTestId("response-card")).toHaveAttribute("data-result", "fail");
    await expect(page.getByTestId("response-template")).toContainText("GSI");
    await expect(page.getByTestId("critical-fails")).toBeVisible();
    await expect(page.locator('[data-testid="fd-finding"][data-severity="critical"]').first()).toBeVisible();

    // Release is refused while the CA is still open, then accepted once it is in progress.
    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const list = await getJson<{ items: { id: string; order_no: string; ca_id: string | null }[] }>(api, `/api/v1/projects/${pid}/stop-work-orders?status=active&page_size=50`);
    const order = list.items.find((o) => o.order_no === orderNo);
    expect(order?.ca_id).toBeTruthy();
    await page.goto(`/en/stop-work-orders/${order?.id}`);
    await expect(page.getByTestId("stop-detail")).toHaveAttribute("data-status", "active");
    await page.getByTestId("stop-release").click();
    await page.getByTestId("release-note").fill("Edge protection installed and checked");
    await page.getByTestId("release-photos-input").setInputFiles({ name: "fixed.png", mimeType: "image/png", buffer: makePng(64) });
    await page.getByTestId("release-confirm").click();
    await expect(page.getByRole("dialog")).toContainText("must be in progress or done before release");
    await page.keyboard.press("Escape");

    sql(`UPDATE corrective_actions SET status = 'in_progress' WHERE id = '${order?.ca_id}'`);
    await page.reload();
    await page.getByTestId("stop-release").click();
    await page.getByTestId("release-note").fill("Edge protection installed and checked");
    await page.getByTestId("release-photos-input").setInputFiles({ name: "fixed.png", mimeType: "image/png", buffer: makePng(64) });
    await page.getByTestId("release-confirm").click();
    await expect(page.getByTestId("stop-detail")).toHaveAttribute("data-status", "released");
  });

  test("phone: with no signal the run waits on the device, then sends itself when the signal returns", async ({ page, context }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS.noura, "/field-inspections/new");
    await page.getByTestId("pack-download").click();
    await expect(page.getByTestId("offline-pack")).toHaveAttribute("data-cached", "yes");

    const codes = await startGsi(page, "Z-MSCP", "NAJD");
    for (const c of codes) await page.getByTestId(`ans-${c}-compliant`).click();
    await context.setOffline(true);
    await page.getByTestId("run-submit").click();
    await expect(page.getByTestId("run-queued")).toBeVisible();
    await expect(page.getByTestId("offline-banner")).toBeVisible();
    await expect(page.locator('[data-testid="outbox-item"][data-state="waiting"]')).toHaveCount(1);

    await context.setOffline(false);
    await expect(page.getByTestId("outbox-item")).toHaveCount(0, { timeout: 20_000 });
  });

  test("AC59: the offline cache is wiped at logout and after the 72 h window", async ({ page }) => {
    await openAs(page, USERS.noura, "/field-inspections/new");
    await page.getByTestId("pack-download").click();
    await expect(page.getByTestId("offline-pack")).toHaveAttribute("data-cached", "yes");
    // 73 h later the shell's purge removes the pack.
    await page.clock.fastForward(73 * 3600 * 1000);
    await expect(page.getByTestId("offline-pack")).toHaveAttribute("data-cached", "no", { timeout: 20_000 });

    await page.getByTestId("pack-download").click();
    await expect(page.getByTestId("offline-pack")).toHaveAttribute("data-cached", "yes");
    await page.getByTestId("user-menu").click();
    await page.getByTestId("logout").click();
    await page.waitForURL(/\/login/);
    const left = await page.evaluate(
      () =>
        new Promise<number>((resolve) => {
          const req = indexedDB.open("hse-field");
          req.onsuccess = () => {
            const db = req.result;
            const names = Array.from(db.objectStoreNames);
            if (!names.length) return resolve(0);
            const tx = db.transaction(names, "readonly");
            let n = 0;
            for (const s of names) tx.objectStore(s).count().onsuccess = (e) => (n += (e.target as IDBRequest<number>).result);
            tx.oncomplete = () => resolve(n);
          };
          req.onerror = () => resolve(0);
        }),
    );
    expect(left).toBe(0);
  });
});
