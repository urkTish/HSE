import { expect, test } from "./fixtures/test";
import { apiAs, getJson, selectByPrefix, USERS } from "./helpers";
import { pickMulti } from "./p2-helpers";
import { openAs } from "./p6a-helpers";

type Item = { item_code: string; item_type: string; numeric_rule: { min: string; max: string } | null; options: { code: string; maps_to: string }[] | null };

/** Field audits: plan with independence, conduct, complete, issue by someone other than the lead (6d §4.4, AUD-1…AUD-7). */
test.describe("Field audits", () => {
  test("Faisal plans a RAWABI audit: an auditor from RAWABI is refused, Noura leads it, Faisal issues the report", async ({ page }) => {
    await openAs(page, USERS.faisal, "/field-audits");
    await page.getByTestId("audit-plan").click();
    await selectByPrefix(page.getByTestId("ap-template"), "CHA");
    await selectByPrefix(page.getByTestId("ap-auditee"), "RAWABI");
    await pickMulti(page, "ap-sites", ["S-LAND"]);
    await selectByPrefix(page.getByTestId("ap-lead"), "Ahmed");
    await page.getByTestId("ap-start").fill("2026-10-12");
    await page.getByTestId("ap-end").fill("2026-10-13");
    await page.getByTestId("audit-plan-confirm").click();
    await expect(page.getByTestId("sod-conflict")).toBeVisible();

    await selectByPrefix(page.getByTestId("ap-lead"), "Noura");
    await page.getByTestId("audit-plan-confirm").click();
    const detail = page.getByTestId("audit-detail");
    await expect(detail).toHaveAttribute("data-status", "planned");
    const auditId = page.url().split("/").pop() ?? "";

    // Noura (lead) starts fieldwork and answers on the conduct screen.
    await openAs(page, USERS.noura, `/field-audits/${auditId}`);
    await page.getByTestId("audit-start").click();
    await expect(detail).toHaveAttribute("data-status", "in_progress");
    await page.getByTestId("audit-conduct").click();
    await expect(page.getByTestId("audit-conduct-card")).toBeVisible();
    await expect(page.getByTestId("run-item").first()).toBeVisible();

    // The rest of the 40 answers go in through the API (the screen saves the same payload).
    const noura = await apiAs(USERS.noura);
    const a = await getJson<{ template_code: string; template_version: number | null }>(noura, `/api/v1/field-audits/${auditId}`);
    const list = await getJson<{ items: { id: string; version: number; status: string }[] }>(noura, `/api/v1/checklist-templates?template_code=${a.template_code}`);
    const tpl = list.items.find((x) => (a.template_version ? x.version === a.template_version : x.status === "published"));
    const full = await getJson<{ items: Item[] }>(noura, `/api/v1/checklist-templates/${tpl?.id}`);
    const answers = full.items.map((i) => {
      if (i.item_type === "rating_0_3") return { item_code: i.item_code, answer: "3" };
      if (i.item_type === "yes_no") return { item_code: i.item_code, answer: "compliant" };
      if (i.item_type === "numeric") return { item_code: i.item_code, numeric_value: i.numeric_rule?.min ?? "0" };
      if (i.item_type === "single_select") return { item_code: i.item_code, answer: i.options?.find((o) => o.maps_to === "compliant")?.code ?? i.options?.[0]?.code };
      if (i.item_type === "count") return { item_code: i.item_code, count_value: 0 };
      return { item_code: i.item_code, answer: "Checked on site" };
    });
    // One weak answer gives a minor nonconformity and so one CA at issue.
    const rated = full.items.find((i) => i.item_type === "rating_0_3");
    if (rated) answers[answers.findIndex((x) => x.item_code === rated.item_code)] = { item_code: rated.item_code, answer: "1", note: "Toolbox talk records incomplete for two weeks" } as never;
    const put = await noura.put(`/api/v1/field-audits/${auditId}/answers`, { data: { answers, manual_findings: [] } });
    expect(put.status()).toBe(200);

    await page.reload();
    // Fieldwork needs the closing meeting and the fieldwork dates.
    await page.getByTestId("audit-meetings").click();
    await page.getByTestId("am-close").fill("2026-10-06T10:30");
    await page.getByTestId("am-fe").fill("2026-10-06");
    await page.getByTestId("meetings-save").click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await page.getByTestId("audit-complete").click();
    await expect(detail).toHaveAttribute("data-status", "fieldwork_complete");
    // The lead cannot issue their own report (AUD-4).
    await expect(page.getByTestId("audit-issue")).toHaveCount(0);
    await expect(page.getByTestId("issue-not-lead")).toBeVisible();

    await openAs(page, USERS.faisal, `/field-audits/${auditId}`);
    await page.getByTestId("audit-issue").click();
    await page.getByTestId("ai-summary").fill("RAWABI site controls are good; toolbox records need attention.");
    await page.getByTestId("issue-confirm").click();
    await expect(detail).toHaveAttribute("data-status", "issued");
    await expect(page.getByTestId("audit-score")).toBeVisible();
    await expect(page.getByTestId("section-scores")).toBeVisible();
  });

  test("the audit programme lists the contractor and system lines; the viewer cannot plan", async ({ page }) => {
    await openAs(page, USERS.noura, "/audit-programme");
    await expect(page.getByTestId("programme-line").first()).toBeVisible();
    await openAs(page, USERS.sarah, "/field-audits");
    await expect(page.getByTestId("audit-row").first()).toBeVisible();
    await expect(page.getByTestId("audit-plan")).toHaveCount(0);
  });
});
