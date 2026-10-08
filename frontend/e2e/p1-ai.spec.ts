import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { insufficientStream, midStreamErrorStream, trirStream, ANSWER_ID } from "./fixtures/ai-stream";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";

/**
 * The AI provider is not configured in e2e (no API key), so:
 * - AC73/AC75 run against the real backend's /ai/status and /ai/ask.
 * - The streamed UI (AC65, AC72, AC74, insufficient data, mid-stream error) replays a recorded
 *   SSE stream via page.route — a test fixture only, never production code.
 */

async function enableAssistant(page: Page, pid: string) {
  await page.route("**/api/v1/ai/status**", (route) =>
    route.fulfill({
      json: {
        project_id: pid,
        enabled: true,
        available: true,
        reason_code: null,
        can_ask: true,
        can_generate_report: true,
        questions_used_today: 3,
        questions_limit_per_day: 60,
        reports_used_this_month: 0,
        reports_limit_per_month: 10,
        default_model: "claude-sonnet",
        deep_model: "claude-opus",
        suggested_questions_en: ["What was our TRIR in September 2026?"],
        suggested_questions_ar: ["ما معدل الحالات المسجلة في سبتمبر 2026؟"],
      },
    }),
  );
}

function replay(page: Page, body: string) {
  return page.route("**/api/v1/ai/ask", (route) =>
    route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
      },
      body,
    }),
  );
}

test.describe("AI assistant", () => {
  test("AC73/AC75: assistant follows the real /ai/status (hidden when disabled, 'AI unavailable' without a provider)", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    const status = await getJson<{
      enabled: boolean;
      available: boolean;
      reason_code: string | null;
    }>(api, `/api/v1/ai/status?project_id=${ania}`);
    await login(page, USERS.noura);
    await expect(page.getByTestId("lagging-tiles")).toBeVisible();
    if (!status.enabled) {
      // AC73: no transfer approval → hidden, and the API refuses with AI_DISABLED.
      await expect(page.getByTestId("ai-open")).toHaveCount(0);
      const res = await api.post("/api/v1/ai/ask", {
        data: { project_id: ania, question: "TRIR?" },
        headers: { accept: "application/json" },
      });
      expect(res.status()).toBe(403);
      expect((await res.json()).detail.code).toBe("AI_DISABLED");
    } else {
      // AC75: no API key configured → the dashboard loads and the panel says AI unavailable.
      expect(status.available).toBe(false);
      await page.getByTestId("ai-open").click();
      await expect(page.getByTestId("ai-unavailable")).toBeVisible();
      await expect(page.getByTestId("ai-question")).toBeDisabled();
    }
  });

  test("AC65/AC72/AC74: streamed answer with citations, chart and recommendations ordered by hierarchy", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    await enableAssistant(page, ania);
    let sent: Record<string, unknown> | null = null;
    await page.route("**/api/v1/ai/ask", (route) => {
      sent = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: trirStream(ania),
      });
    });
    await login(page, USERS.noura);
    await page.getByTestId("ai-open").click();
    await expect(page.getByTestId("ai-panel")).toBeVisible();
    await page.getByTestId("ai-question").fill("What was our TRIR in September 2026? Call me on +966500000123");
    await page.getByTestId("ai-send").click();

    await expect(page.getByTestId("ai-answer")).toContainText("0.92 per 200,000 h");
    expect(sent).not.toBeNull();
    expect((sent as unknown as { project_id: string }).project_id).toBe(ania);
    // AC74: the user is warned that the mobile number was masked.
    await expect(page.getByTestId("ai-prompt-warning")).toBeVisible();
    // AC65: Sources cite get_kpis with scope, period and base.
    await expect(page.getByTestId("ai-citation").first()).toContainText("get_kpis, ANIA-EXP, Sep 2026, all contractors, per 200,000 h");
    await expect(page.getByTestId("ai-chart").getByTestId("chart-ai-1")).toBeVisible();
    await expect(page.getByTestId("ai-label")).toHaveAttribute("data-grounding", "passed");
    // AC72: ordered by the hierarchy of controls (engineering before administrative), AI label shown.
    const recs = page.getByTestId("ai-recommendation");
    await expect(recs).toHaveCount(2);
    await expect(recs.nth(0)).toHaveAttribute("data-control", "engineering");
    await expect(recs.nth(1)).toHaveAttribute("data-control", "administrative");
    await expect(page.getByTestId("ai-label")).toContainText("AI-generated");

    // "Create CA" pre-fills the CA form from the recommendation (CA-7).
    await recs.nth(0).getByTestId("ai-create-ca").click();
    await expect(page).toHaveURL(new RegExp(`/actions/new\\?.*source_id=${ANSWER_ID}`));
    await expect(page.getByTestId("ai-prefill-note")).toBeVisible();
    await expect(page.locator("#title")).toHaveValue("Install double guardrails and toe-boards");
  });

  test("Arabic: the panel and streamed answer render right-to-left", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    await enableAssistant(page, ania);
    await replay(page, trirStream(ania));
    await login(page, USERS.noura, "ar");
    await page.goto("/ar");
    await page.getByTestId("ai-open").click();
    await page.getByTestId("ai-suggestion").first().click();
    await expect(page.getByTestId("ai-answer")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("ai-citation").first()).toContainText("سبتمبر 2026");
  });

  test("Insufficient data: says so, nothing estimated", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    await enableAssistant(page, ania);
    await replay(page, insufficientStream(ania));
    await login(page, USERS.noura);
    await page.getByTestId("ai-open").click();
    await page.getByTestId("ai-question").fill("TRIR this month?");
    await page.getByTestId("ai-send").click();
    await expect(page.getByTestId("ai-answer")).toContainText("rates cannot be calculated");
    await expect(page.getByTestId("ai-insufficient")).toBeVisible();
    await expect(page.getByTestId("ai-chart")).toHaveCount(0);
  });

  test("Errors: mid-stream AI_UNAVAILABLE and pre-stream AI_RATE_LIMITED are shown honestly", async ({ page }) => {
    const api = await apiAs(USERS.noura);
    const ania = await projectId(api, "ANIA-EXP");
    await enableAssistant(page, ania);
    await replay(page, midStreamErrorStream());
    await login(page, USERS.noura);
    await page.getByTestId("ai-open").click();
    await page.getByTestId("ai-question").fill("Is TRIR trending up?");
    await page.getByTestId("ai-send").click();
    await expect(page.getByTestId("ai-error")).toHaveAttribute("data-code", "AI_UNAVAILABLE");
    await expect(page.getByTestId("lagging-tiles")).toBeVisible();

    await page.unroute("**/api/v1/ai/ask");
    await page.route("**/api/v1/ai/ask", (route) =>
      route.fulfill({
        status: 429,
        headers: { "retry-after": "3600" },
        json: {
          detail: {
            code: "AI_RATE_LIMITED",
            message: "Daily question limit reached",
          },
        },
      }),
    );
    await page.getByTestId("ai-question").fill("And last month?");
    await page.getByTestId("ai-send").click();
    await expect(page.getByTestId("ai-error").last()).toHaveAttribute("data-code", "AI_RATE_LIMITED");
  });
});
