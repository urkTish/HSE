import type { Page } from "@playwright/test";
import { expect } from "../fixtures/test";

/** Select the first option of a native select whose text matches (e.g. an engagement "RAWABI · T1"). */
export async function pickByText(page: Page, testId: string, re: RegExp): Promise<void> {
  const select = page.getByTestId(testId);
  await expect(select.locator("option").nth(1)).toBeAttached();
  const options = select.locator("option");
  const n = await options.count();
  for (let i = 0; i < n; i += 1) {
    const text = (await options.nth(i).textContent()) ?? "";
    if (re.test(text)) {
      await select.selectOption((await options.nth(i).getAttribute("value")) ?? "");
      return;
    }
  }
  throw new Error(`No option matching ${re} in ${testId}`);
}
