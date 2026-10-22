import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, USERS } from "./helpers";

/** D-304: the lesson bulletin downloads as a real PDF in English and Arabic. */
test("the lesson page offers the bulletin as EN and AR PDFs", async ({ page }) => {
  const api = await apiAs(USERS.faisal);
  const lessons = await getJson<{ items: { id: string; lesson_no: string }[] }>(api, "/api/v1/lessons?q=LL-2026-007");
  const ls = lessons.items.find((x) => x.lesson_no === "LL-2026-007");
  expect(ls, "LL-2026-007 in the seed").toBeTruthy();
  await api.dispose();
  await login(page, USERS.faisal, "ar");
  await page.goto(`/ar/lessons/${ls!.id}`);
  await expect(page.getByTestId("lesson-bulletin")).toBeVisible();
  for (const lang of ["ar", "en"] as const) {
    const download = page.waitForEvent("download");
    await page.getByTestId(`bulletin-${lang}`).click();
    const file = await download;
    expect(file.suggestedFilename()).toBe(`LL-2026-007-bulletin-${lang.toUpperCase()}.pdf`);
    const path = await file.path();
    const { readFileSync } = await import("node:fs");
    expect(readFileSync(path).subarray(0, 4).toString()).toBe("%PDF");
  }
});
