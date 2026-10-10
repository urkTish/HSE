import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, selectByPrefix, USERS } from "./helpers";
import { accessCard, pickMulti } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

type Dep = { id: string; worker_no: string; engagement: { short_code: string } | null; sites: { code: string }[] };

/** Toolbox talks and briefing campaigns (6d §3.7–§3.9, TBT-1…TBT-10, CMP-1…CMP-5). */
test.describe("Toolbox talks", () => {
  test("phone: Noura records a NAJD talk with a scanned card and a signed list row; the viewer sees counts only", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const deps = await getJson<{ items: Dep[] }>(api, `/api/v1/projects/${pid}/deployments?status=mobilised&page_size=200`);
    const najd = deps.items.filter((d) => d.engagement?.short_code === "NAJD" && d.sites.some((s) => s.code === "S-LAND"));
    const [scanned, listed] = najd;
    expect(listed).toBeTruthy();
    const card = await accessCard(await apiAs(USERS.faisal), scanned?.id ?? "");

    await page.setViewportSize({ width: 390, height: 844 });
    await openAs(page, USERS.noura, "/toolbox-talks/new");
    // The worker list comes from the offline pack, downloaded on first use.
    await expect(page.getByTestId("offline-pack")).toHaveAttribute("data-cached", "yes", { timeout: 30_000 });
    await selectByPrefix(page.getByTestId("tf-site"), "S-LAND");
    await selectByPrefix(page.getByTestId("tf-host"), "NAJD");
    await pickMulti(page, "tf-topics", [/TT-014/]);

    await page.getByTestId("att-payload").fill(card.qr_payload);
    await page.getByTestId("att-payload-go").click();
    await expect(page.locator('[data-testid="att-row"][data-method="card_scan"]')).toHaveCount(1);

    await page.getByTestId("att-search").fill(listed?.worker_no ?? "");
    await page.locator(`[data-testid="att-match"][data-worker="${listed?.worker_no}"]`).click();
    const listRow = page.locator('[data-testid="att-row"][data-method="list"]');
    await expect(listRow).toHaveCount(1);
    // An unsigned list row needs the signed sheet photo; a signature clears that.
    await expect(page.getByTestId("sheet-needed")).toBeVisible();
    await listRow.getByTestId("att-sign").click();
    const pad = page.getByTestId("signature-canvas");
    const box = await pad.boundingBox();
    if (!box) throw new Error("no signature pad");
    await page.mouse.move(box.x + 20, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + 15, { steps: 6 });
    await page.mouse.move(box.x + box.width - 20, box.y + box.height - 15, { steps: 6 });
    await page.mouse.up();
    await page.getByTestId("signature-done").click();
    await expect(listRow).toHaveAttribute("data-signed", "yes");
    await expect(page.getByTestId("sheet-needed")).toHaveCount(0);
    await expect(page.getByTestId("att-count")).toContainText("2");

    await page.getByTestId("tf-submit").click();
    const saved = page.getByTestId("talk-saved");
    await expect(saved).toHaveAttribute("data-no", /^TBT-ANIA-EXP-2026-/);
    await page.getByTestId("talk-open").click();
    await expect(page.getByTestId("talk-detail")).toHaveAttribute("data-status", "delivered");
    await expect(page.getByTestId("att-detail-row")).toHaveCount(2);
    const talkUrl = new URL(page.url()).pathname.replace(/^\/en/, "");

    await openAs(page, USERS.sarah, talkUrl);
    await expect(page.getByTestId("talk-detail")).toBeVisible();
    await expect(page.getByTestId("names-hidden")).toBeVisible();
    // Rows stay countable, without names or worker numbers (AC58).
    await expect(page.getByTestId("att-detail-row")).toHaveCount(2);
    await expect(page.getByTestId("att-table")).not.toContainText(listed?.worker_no ?? "WKR");
    await expect(page.getByTestId("talk-add-rows")).toHaveCount(0);
  });

  test("Noura issues a briefing campaign and sees its contractor-site pairs", async ({ page }) => {
    await openAs(page, USERS.noura, "/briefing-campaigns");
    await page.getByTestId("campaign-new").click();
    await selectByPrefix(page.getByTestId("cd-topic"), "TT-022");
    await page.getByTestId("cd-reason").selectOption("lesson");
    // 6f LK-2: reason `lesson` needs a Published lesson (LL-2026-007 in the seed)
    await page.getByTestId("cd-ref").fill("LL-2026-007");
    await page.getByTestId("cd-message").fill("Temporary electrical: check every lead and RCD before use this week.");
    await page.locator("button#cd-sites").click();
    await page.getByRole("listbox").getByRole("option", { name: "S-LAND" }).getByRole("button").click();
    await page.getByRole("listbox").press("Escape");
    await page.getByTestId("campaign-save").click();
    const detail = page.getByTestId("campaign-detail");
    await expect(detail).toHaveAttribute("data-status", "draft");
    await page.getByTestId("campaign-issue").click();
    await page.getByTestId("campaign-issue-confirm").click();
    await expect(detail).toHaveAttribute("data-status", "issued");
    await expect(page.getByTestId("pair-row").first()).toBeVisible();
  });
});
