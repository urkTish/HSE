import { expect, test } from "./fixtures/test";
import { apiAs, getJson, projectId, USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

type Req = { id: string; incident_id: string; rule_code: string; status: string; pack_id: string | null };

/** Incident follow-up panel, packs and submissions with evidence, notification register (6f §3.3–§3.5, NR, PK, SB, P6f-5; AC 11, 16, 18, 19, 44). */
test.describe("Notifications and follow-up", () => {
  let incident = "";
  test.beforeAll(async () => {
    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const reqs = await getJson<{ items: Req[] }>(api, `/api/v1/projects/${pid}/notification-requirements?page_size=100`);
    incident = reqs.items.find((r) => r.rule_code === "GACA-W")?.incident_id ?? "";
    expect(incident).not.toBe("");
  });

  test("Noura generates and approves the GACA occurrence pack and records the portal submission (FU2)", async ({ page }) => {
    await openAs(page, USERS.noura, `/incidents/${incident}`);
    const panel = page.getByTestId("fu-panel");
    await expect(panel.getByTestId("fu-req")).toHaveCount(7);
    const card = (rule: string) => panel.locator(`[data-testid="fu-req"][data-rule="${rule}"]`);
    await expect(card("AO-W")).toHaveAttribute("data-status", "acknowledged");
    await expect(card("CL-F").getByTestId("fu-on-time")).toHaveAttribute("data-on-time", "true");
    await expect(card("GACA-W")).toHaveAttribute("data-status", "due");
    await expect(card("GACA-W").getByTestId("fu-countdown")).toBeVisible();

    await card("GACA-W").getByTestId("fu-generate").click();
    await page.getByTestId("pack-generate-confirm").click();
    await expect(page).toHaveURL(/\/notification-packs\//);
    await expect(page.getByTestId("pack-status")).toHaveAttribute("data-status", "draft");
    await expect(page.getByTestId("pack-snapshot")).toBeVisible();
    await expect(page.getByTestId("pack-field-set")).toHaveAttribute("data-field-set", "none");
    await page.getByTestId("pack-approve").click();
    await page.getByTestId("pack-approve-confirm").click();
    await expect(page.getByTestId("pack-status")).toHaveAttribute("data-status", "approved");

    await page.getByTestId("pack-incident").click();
    await expect(card("GACA-W").getByTestId("fu-pack-status")).toHaveAttribute("data-status", "approved");
    await card("GACA-W").getByTestId("fu-submit").click();
    await expect(page.getByTestId("sub-channel-portal")).toHaveAttribute("aria-checked", "true");
    // Phone and radio are for verbal stages only (SB-2).
    await expect(page.getByTestId("sub-channel-phone_radio")).toHaveCount(0);
    await page.getByTestId("sub-ref").fill("GACA-TEST-7001");
    await page.getByTestId("sub-confirm").click();
    await expect(card("GACA-W")).toHaveAttribute("data-status", "submitted");
    await expect(card("GACA-W").getByTestId("fu-on-time")).toHaveAttribute("data-on-time", "true");
    await expect(card("GACA-W").getByTestId("fu-pack-status")).toHaveAttribute("data-status", "submitted");
  });

  test("the register lists open items first; the viewer sees statuses, never packs or actions (P6f-5)", async ({ page }) => {
    await openAs(page, USERS.sarah, "/notification-register");
    const rows = page.getByTestId("fu-req");
    await expect(rows.first()).toBeVisible();
    await expect(rows.first()).toHaveAttribute("data-status", /due|overdue/);
    await expect(page.getByTestId("fu-generate")).toHaveCount(0);
    await expect(page.getByTestId("fu-submit")).toHaveCount(0);
    await expect(page.getByTestId("fu-req-pack")).toHaveCount(0);
    await page.goto("/en/notification-register?status=submitted");
    await expect(rows.first()).toHaveAttribute("data-status", "submitted");

    const api = await apiAs(USERS.noura);
    const pid = await projectId(api, "ANIA-EXP");
    const reqs = await getJson<{ items: Req[] }>(api, `/api/v1/projects/${pid}/notification-requirements?page_size=100`);
    const pack = reqs.items.find((r) => r.pack_id)?.pack_id;
    await page.goto(`/en/notification-packs/${pack}`);
    await expect(page.getByTestId("pack-snapshot")).toHaveCount(0);
    await expect(page.getByTestId("pack-no")).toHaveCount(0);
  });

  test("Arabic: the register and the incident panel are right-to-left", async ({ page }) => {
    await openAs(page, USERS.noura, "/notification-register", "ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("الإخطارات");
    await page.goto(`/ar/incidents/${incident}`);
    await expect(page.getByTestId("fu-panel")).toContainText("الإخطارات والمتابعة");
    await expect(page.getByTestId("fu-panel").getByTestId("fu-status").first()).toBeVisible();
  });
});
