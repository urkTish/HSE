import { expect, type Page } from "@playwright/test";
import { apiAs, login, projectId, USERS } from "./helpers";

/** Phase 6a seed users (6a-occupational-health Appendix A.2) and the Phase 5 user the 6a ACs reuse. */
export const USERS6 = {
  huda: "huda.mansour@example.com",
  grace: "grace.villanueva@example.com",
  fahad: "fahad.mutairi@example.com",
} as const;

/** Pin the shell to a project (6a users serve two projects). */
export async function pinProject(page: Page, code = "ANIA-EXP"): Promise<void> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, code);
  await page.goto(`/en?project=${pid}`);
  await expect(page.getByTestId("topbar")).toBeVisible();
}

/** Sign in, pin the project and open a page. */
export async function openAs(page: Page, email: string, path: string, locale: "en" | "ar" = "en", project = "ANIA-EXP"): Promise<void> {
  await login(page, email, locale);
  await pinProject(page, project);
  await page.goto(`/${locale}${path}`);
}
