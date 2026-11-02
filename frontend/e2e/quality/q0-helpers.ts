import type { Page } from "@playwright/test";
import { expect } from "../fixtures/test";
import { login } from "../helpers";
import { pinProject } from "../p6a-helpers";

/** Quality seed users (spec 8-quality Appendix A.1; Joseph's address is D-322). */
export const QU = {
  hatem: "hatem.shehri@example.com",
  bilal: "bilal.qureshi@example.com",
  joseph: "joseph.mathew.qc@example.com",
  rania: "rania.zahrani@example.com",
  reem: "reem.mutairi@example.com",
  imran: "imran.siddiq@example.com",
} as const;

/** Sign in, pin the project and open a Quality page. */
export async function openQ(page: Page, email: string, path: string, opts: { locale?: "en" | "ar"; project?: string } = {}): Promise<void> {
  const locale = opts.locale ?? "en";
  await login(page, email, locale);
  await pinProject(page, opts.project ?? "ANIA-EXP");
  await page.goto(`/${locale}${path}`);
}

/** Pick the first real option of a native select (skips the "Select…" placeholder). */
export async function pickFirst(page: Page, testId: string): Promise<void> {
  const select = page.getByTestId(testId);
  await expect(select.locator("option").nth(1)).toBeAttached();
  const value = await select.locator("option").nth(1).getAttribute("value");
  await select.selectOption(value ?? "");
}
