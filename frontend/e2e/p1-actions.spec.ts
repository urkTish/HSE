import { expect, test, type APIRequestContext } from "@playwright/test";
import { apiAs, getJson, login, projectId, uid, userId, USERS } from "./helpers";

interface Ca {
  id: string;
  status: string;
  completed_at: string | null;
  original_due_date: string;
  due_date: string;
  extensions: { id: string }[];
}

async function createCa(api: APIRequestContext, owner: string, verifier: string, title: string): Promise<Ca> {
  const ania = await projectId(api, "ANIA-EXP");
  const sites = await getJson<{ items: { id: string; code: string }[] }>(api, `/api/v1/projects/${ania}/sites?page_size=100`);
  const engs = await getJson<{
    items: { id: string; contractor: { short_code: string } }[];
  }>(api, `/api/v1/projects/${ania}/engagements?page_size=100`);
  const res = await api.post(`/api/v1/projects/${ania}/corrective-actions`, {
    data: {
      title,
      description: "Install guardrails on the Pier B platform edges.",
      control_level: "engineering",
      priority: "medium",
      owner_id: await userId(api, owner),
      verifier_id: await userId(api, verifier),
      source_type: "other",
      site_id: sites.items.find((x) => x.code === "S-AIR")?.id,
      responsible_engagement_id: engs.items.find((x) => x.contractor.short_code === "RAWABI")?.id,
    },
  });
  expect(res.status(), await res.text()).toBe(201);
  return (await res.json()) as Ca;
}

async function confirm(page: import("@playwright/test").Page, to: string, text?: string) {
  await page.getByTestId(`transition-${to}`).click();
  if (text !== undefined) await page.locator("#ca-transition-text").fill(text);
  await page.getByTestId("transition-confirm").click();
}

test.describe("Corrective actions", () => {
  test("AC42/AC43/AC40: evidence is required, the owner cannot verify, a rejection reopens the action", async ({ page }) => {
    const noura = await apiAs(USERS.noura);
    const ca = await createCa(noura, USERS.ahmed, USERS.noura, `E2E guardrails ${uid()}`);

    // AC42 at the API: no evidence → EVIDENCE_REQUIRED.
    const ahmed = await apiAs(USERS.ahmed);
    const bad = await ahmed.post(`/api/v1/corrective-actions/${ca.id}/transitions`, { data: { to_status: "pending_verification" } });
    expect(bad.status()).toBe(422);
    expect((await bad.json()).detail.code).toBe("EVIDENCE_REQUIRED");

    await login(page, USERS.ahmed);
    await page.goto(`/en/actions/${ca.id}`);
    await confirm(page, "in_progress");
    await expect(page.getByTestId("transition-pending_verification")).toBeVisible();
    // AC42 in the UI: the dialog refuses short evidence.
    await page.getByTestId("transition-pending_verification").click();
    await page.locator("#ca-transition-text").fill("done");
    await page.getByTestId("transition-confirm").click();
    await expect(page.getByText(/at least 20 characters|20 characters/i).first()).toBeVisible();
    await page.locator("#ca-transition-text").fill("Double guardrails and toe-boards fitted on all Pier B platforms.");
    await page.getByTestId("transition-confirm").click();
    // AC40: the owner is never offered verification.
    await expect(page.getByTestId("transition-pending_verification")).toHaveCount(0);
    await expect(page.getByTestId("transition-closed")).toHaveCount(0);
    expect((await getJson<Ca>(ahmed, `/api/v1/corrective-actions/${ca.id}`)).status).toBe("pending_verification");

    // AC43: the verifier rejects → In Progress, completed_at cleared.
    await page.context().clearCookies();
    await login(page, USERS.noura);
    await page.goto(`/en/actions/${ca.id}`);
    await confirm(page, "in_progress", "Toe-boards missing on grid C-14, please complete.");
    await expect(page.getByTestId("transition-closed")).toHaveCount(0);
    const after = await getJson<Ca>(noura, `/api/v1/corrective-actions/${ca.id}`);
    expect(after.status).toBe("in_progress");
    expect(after.completed_at).toBeNull();
  });

  test("AC41: a third extension is refused and the original due date never changes", async ({ page }) => {
    const noura = await apiAs(USERS.noura);
    const ca = await createCa(noura, USERS.ahmed, USERS.noura, `E2E extensions ${uid()}`);
    const ahmed = await apiAs(USERS.ahmed);
    let due = ca.due_date;
    for (let i = 0; i < 2; i++) {
      const next = new Date(`${due}T00:00:00Z`);
      next.setUTCDate(next.getUTCDate() + 7);
      due = next.toISOString().slice(0, 10);
      const req = await ahmed.post(`/api/v1/corrective-actions/${ca.id}/extensions`, { data: { new_due_date: due, reason: "Material delivery delayed" } });
      expect(req.status(), await req.text()).toBe(201);
      const ext = (await req.json()) as Ca | { id: string };
      const extId = "extensions" in ext ? (ext.extensions.at(-1)?.id ?? "") : ext.id;
      const dec = await noura.post(`/api/v1/corrective-actions/${ca.id}/extensions/${extId}/decision`, { data: { approve: true } });
      expect(dec.ok(), await dec.text()).toBeTruthy();
    }
    await login(page, USERS.ahmed);
    await page.goto(`/en/actions/${ca.id}`);
    await page.getByTestId("request-extension").click();
    const later = new Date(`${due}T00:00:00Z`);
    later.setUTCDate(later.getUTCDate() + 7);
    await page.locator("#ext-due").fill(later.toISOString().slice(0, 10));
    await page.locator("#ext-reason").fill("Further delay");
    await page.getByTestId("extension-submit").click();
    await expect(page.getByText("The maximum number of extensions has been reached.").first()).toBeVisible();
    const now = await getJson<Ca>(noura, `/api/v1/corrective-actions/${ca.id}`);
    expect(now.original_due_date).toBe(ca.original_due_date);
  });

  test("CA list filters from the URL (dashboard links)", async ({ page }) => {
    await login(page, USERS.noura);
    await page.goto("/en/actions?status=open");
    await expect(page.getByTestId("ca-table").or(page.getByText("No records match the current filters."))).toBeVisible();
  });
});
