import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";

/** Lock register (HSE Officer: isolation.manage; the HSE Manager does not hold it, §5.14): register an isolation lock, find it, report it lost. */
test("register an isolation lock and report it lost", async ({ page }) => {
  await login(page, USERS.noura);
  await page.goto("/en/locks");
  const no = `L-E2E-${uid()}`;
  await page.getByTestId("new-lock").click();
  const dlg = page.getByRole("dialog");
  await dlg.locator("#lc-type").selectOption("isolation_lock");
  await dlg.locator("#lc-no").fill(no);
  await dlg.getByTestId("save-lock").click();
  await expect(dlg).toHaveCount(0);

  await page.locator("#lk-q").fill(no);
  const row = page.getByTestId("lock-row").filter({ hasText: no });
  await expect(row).toHaveAttribute("data-status", "available");
  await row.getByTestId("report-lost").click();
  const lost = page.getByRole("dialog");
  await lost.locator("#ll-detail").fill("Dropped in the cable trench during the e2e run");
  await lost.getByTestId("lock-lost-confirm").click();
  await expect(lost).toHaveCount(0);
  await expect(page.getByTestId("lock-row").filter({ hasText: no })).toHaveAttribute("data-status", "lost");
});
