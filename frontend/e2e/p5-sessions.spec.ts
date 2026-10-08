import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";
import { sessionId, USERS5 } from "./p5-helpers";

/** Training sessions, attendance and close against the Appendix A seed (5-training §5.9–§5.11; AC40, AC45, AC55, AC63, AC64). */
test.describe("Training sessions", () => {
  test("AC40: a CSE-ATTENDANT day of 360 net minutes is refused as too short", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/training-sessions/new");
    await page.getByTestId("ss-course-in").selectOption("CSE-ATTENDANT");
    await selectContaining(page.getByTestId("ss-provider"), "INT-HSE");
    await page.getByTestId("ss-capacity").fill("10");
    await selectContaining(page.getByTestId("ss-tr-user-0"), "Noura");
    await page.getByTestId("ss-tr-roles-0").getByRole("checkbox").first().check();
    await page.getByTestId("ss-offsite").fill("Training room 2, site office");
    await page.getByTestId("ss-day-date-0").fill("2026-10-20");
    await page.getByTestId("ss-day-start-0").fill("07:00");
    await page.getByTestId("ss-day-end-0").fill("14:00");
    await page.getByTestId("ss-day-break-0").fill("60");
    await expect(page.getByTestId("ss-total-net")).toContainText("360");
    await page.getByTestId("save-session").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute("data-code", "SESSION_TOO_SHORT");
  });

  test("AC45: Biju Thomas (on TRS-ANIA-EXP-2026-00057 on 2026-10-07) cannot be nominated to another session that day", async ({ page }) => {
    const noura = await apiAs(USERS.noura);
    const pid = await projectId(noura, "ANIA-EXP");
    const providers = await getJson<{ items: { id: string; provider_code: string }[] }>(noura, "/api/v1/training-providers?page_size=100");
    const me = await getJson<{ id: string }>(noura, "/api/v1/auth/me");
    const res = await noura.post(`/api/v1/projects/${pid}/training-sessions`, {
      data: {
        course_code: "FIRE-WATCH",
        provider_id: providers.items.find((p) => p.provider_code === "INT-HSE")?.id,
        delivery_mode: "classroom",
        trainers: [{ user_id: me.id, roles: ["trainer", "assessor"] }],
        location: { offsite_text: "Training room 4" },
        language: "en",
        interpreter_languages: ["ur"],
        days: [{ date: "2026-10-07", start_time: "07:00", end_time: "12:00", break_minutes: 30 }],
        capacity: 10,
      },
    });
    expect(res.ok(), `session → ${res.status()} ${await res.text()}`).toBeTruthy();
    const { id } = (await res.json()) as { id: string };
    await login(page, USERS.noura);
    await page.goto(`/en/training-sessions/${id}`);
    await page.getByTestId("nominate").click();
    await page.getByTestId("nom-worker-search").fill("WKR-000017");
    await selectContaining(page.getByTestId("nom-worker"), "WKR-000017");
    await page.getByTestId("nom-add").click();
    await page.getByTestId("nom-submit").click();
    await expect(page.locator('[data-testid="nom-error"][data-code="SCHEDULE_CLASH"]')).toBeVisible();
  });

  test("AC55: the HSE Officer has no Void action; AC63: a site engineer sees status and result, not scores", async ({ page }) => {
    const api = await apiAs(USERS.faisal);
    const id = await sessionId(api, "ANIA-EXP", "TRS-ANIA-EXP-2026-00031");
    await login(page, USERS.noura);
    await page.goto(`/en/training-sessions/${id}`);
    await expect(page.getByTestId("attendance-register")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("session-void")).toHaveCount(0);

    // Omar's grant is limited to a site none of these attendees works on, so the site engineer here is Fahad.
    await login(page, USERS5.fahad);
    await page.goto(`/en/training-sessions/${id}`);
    const imran = page.locator('[data-testid="attendee"][data-worker="WKR-000001"]');
    await expect(imran).toHaveAttribute("data-result", "passed");
    await expect(imran).not.toContainText("%");
    await expect(page.getByTestId("att-theory")).toHaveCount(0);
  });

  test("Phone, Arabic: Lina records attendance for TRS-RBT-52-2026-00022 while it is in progress", async ({ page }) => {
    test.setTimeout(180_000);
    const api = await apiAs(USERS.faisal);
    const id = await sessionId(api, "RBT-52", "TRS-RBT-52-2026-00022");
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, USERS5.lina, "ar");
    await page.goto(`/ar/training-sessions/${id}`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("attendance-register")).toBeVisible();
    await page.getByTestId("all-present").click();
    const cards = page.getByTestId("attendee");
    const n = await cards.count();
    expect(n).toBeGreaterThan(0);
    for (let i = 0; i < n; i++) {
      const c = cards.nth(i);
      const theory = c.getByTestId("att-theory");
      if (await theory.count()) await theory.fill("86.50");
      const practical = c.getByTestId("att-practical");
      if (await practical.count()) await practical.selectOption("pass");
    }
    await page.getByTestId("save-attendance").click();
    await expect(page.getByTestId("save-attendance")).toBeDisabled();
    await expect(page.locator('[data-testid="attendee"][data-status="attended"]')).toHaveCount(n);

    // Close needs the session Delivered (16:00 at the earliest), so it is not offered at the 10:00 clock.
    await expect(page.getByTestId("session-close")).toHaveCount(0);
    await page.reload();
    await expect(page.locator('[data-testid="attendee"][data-status="attended"]')).toHaveCount(n);
  });
});
