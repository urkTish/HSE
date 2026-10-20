import { test as base, expect, type Browser, type BrowserContext, type BrowserContextOptions } from "@playwright/test";
import { CLOCK_OFFSET_MS } from "../clock";

/**
 * Playwright `test` whose browser contexts run on the shared e2e clock (see ../clock.ts).
 * Playwright's clock anchors the fake time to the driver's Date.now(), which runs in this (shifted) process,
 * so the offset is added once more to land the browser on the same instant as the tests and the API.
 * Installed on the context, so every page of the default context (and `page`) shares it.
 */
async function installClock(ctx: BrowserContext): Promise<void> {
  await ctx.clock.install({ time: Date.now() + CLOCK_OFFSET_MS });
}

export const test = base.extend({
  context: async ({ context }, provide) => {
    await installClock(context);
    await provide(context);
  },
});
export { expect };

/** `browser.newContext()` on the shared clock, for tests that need a second user or a phone viewport. */
export async function newClockContext(browser: Browser, options?: BrowserContextOptions): Promise<BrowserContext> {
  const ctx = await browser.newContext(options);
  await installClock(ctx);
  return ctx;
}
