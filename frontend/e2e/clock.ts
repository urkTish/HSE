/**
 * Shared e2e clock. The Phase 3 PTW seed (3-ptw.md Appendix A) is built around 2026-10-06, so the API
 * (HSE_CLOCK_AT, set by start-backend.sh from E2E_CLOCK_OFFSET_MS), the test process (Date below) and every
 * browser context (fixtures/test.ts) run at the same shifted instant, with time moving on normally.
 */
const AT = process.env.E2E_CLOCK_AT ?? "2026-10-06T10:00:00+03:00";
if (!process.env.E2E_CLOCK_OFFSET_MS) process.env.E2E_CLOCK_OFFSET_MS = String(Date.parse(AT) - Date.now());
export const CLOCK_OFFSET_MS = Number(process.env.E2E_CLOCK_OFFSET_MS);

const g = globalThis as unknown as { Date: DateConstructor; __hseClockPatched?: boolean };
if (!g.__hseClockPatched && CLOCK_OFFSET_MS) {
  g.__hseClockPatched = true;
  const Real = g.Date;
  const Shifted = function (this: unknown, ...args: unknown[]) {
    if (!(this instanceof Shifted)) return new Real(Real.now() + CLOCK_OFFSET_MS).toString();
    return args.length === 0 ? new Real(Real.now() + CLOCK_OFFSET_MS) : new (Real as unknown as new (...a: unknown[]) => Date)(...args);
  } as unknown as DateConstructor;
  Object.setPrototypeOf(Shifted, Real);
  (Shifted as unknown as { prototype: Date }).prototype = Real.prototype;
  Shifted.now = () => Real.now() + CLOCK_OFFSET_MS;
  g.Date = Shifted;
}
