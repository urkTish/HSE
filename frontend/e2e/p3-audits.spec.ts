import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";

/** AC90: an unpermitted-work audit needs a critical CA (source ptw_audit) before it can be completed. */
test("AC90 unpermitted work audit: critical CA required, then completed", async ({ page }) => {
  await login(page, USERS.noura);
  await page.goto("/en/ptw-audits/new");
  await page.getByTestId("audit-type").selectOption("unpermitted_work");
  await selectContaining(page.locator("#ac-site"), "S-LAND");
  await selectContaining(page.locator("#ac-eng"), "NAJD");
  await page.locator("#ac-desc").fill("Grinding at Pier B level 2 without a hot work permit; stopped on the spot.");
  await page.getByTestId("ans-A00-non_compliant").check({ force: true });
  await page.getByTestId("save-audit").click();
  await expect(page).toHaveURL(/\/ptw-audits\/[0-9a-f-]{36}/);
  const auditUrl = page.url();
  await expect(page.getByTestId("ptw-audit-detail")).toHaveAttribute("data-status", "draft");
  await expect(page.getByTestId("cas-missing")).toBeVisible();

  await page.getByTestId("complete-audit").click();
  await page.getByTestId("complete-confirm").click();
  await expect(page.getByRole("dialog").getByTestId("form-error")).toHaveAttribute("data-code", "CA_REQUIRED");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

  // Raise the CA from the audit: source, priority, contractor and site come prefilled.
  await page.getByTestId("raise-ca-A00").click();
  const form = page.getByTestId("ca-form");
  await expect(form.locator("#priority")).toHaveValue("critical");
  await form.locator("#description").fill("Brief NAJD supervisors on the PTW rule and add a hot-work patrol on Pier B.");
  await form.locator("#control_level").selectOption("administrative");
  await selectContaining(form.locator("#owner_id"), "Ramesh");
  await selectContaining(form.locator("#verifier_id"), "Noura");
  await page.getByTestId("save-ca").click();
  await expect(page).toHaveURL(/\/actions\/[0-9a-f-]{36}/);

  await page.goto(auditUrl);
  await expect(page.getByTestId("audit-cas")).toContainText("A00");
  await page.getByTestId("complete-audit").click();
  await page.getByTestId("complete-confirm").click();
  await expect(page.getByTestId("ptw-audit-detail")).toHaveAttribute("data-status", "completed");
});
