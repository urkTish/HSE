import { test as base, expect } from "@playwright/test";
import { CLOCK_OFFSET_MS } from "../clock";

/**
 * Playwright `test` whose browser pages run on the shared e2e clock (see ../clock.ts).
 * Playwright's clock anchors the fake time to the driver's Date.now(), which runs in this (shifted) process,
 * so the offset is added once more to land the browser on the same instant as the tests and the API.
 */
export const test = base.extend({
  page: async ({ page }, provide) => {
    await page.clock.install({ time: Date.now() + CLOCK_OFFSET_MS });
    await provide(page);
  },
});
export { expect };
