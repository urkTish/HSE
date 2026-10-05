import { execFileSync } from "node:child_process";
import { expect, request as pwRequest, type APIRequestContext, type Page } from "@playwright/test";

export const PASSWORD = process.env.SEED_PASSWORD ?? "Demo-Passw0rd!2026";
export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export const USERS = {
  faisal: "faisal.harbi@example.com",
  noura: "noura.qahtani@example.com",
  omar: "omar.siddiqui@example.com",
  khalid: "khalid.otaibi@example.com",
  ramesh: "ramesh.kumar@example.com",
  ahmed: "ahmed.zahrani@example.com",
  sarah: "sarah.mitchell@example.com",
  yousef: "yousef.ghamdi@example.com",
} as const;

/** Sign in through the UI and wait for the authenticated shell. */
export async function login(page: Page, email: string, locale: "en" | "ar" = "en", password = PASSWORD): Promise<void> {
  await page.goto(`/${locale}/login`);
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("button[type=submit]").click();
  await expect(page.getByTestId("topbar")).toBeVisible();
}

/** API context signed in as a user (for looking up IDs during test setup). */
export async function apiAs(email: string, password = PASSWORD): Promise<APIRequestContext> {
  const ctx = await pwRequest.newContext({ baseURL: BASE_URL });
  const res = await ctx.post("/api/v1/auth/login", { data: { email, password } });
  expect(res.ok(), `login ${email}`).toBeTruthy();
  return ctx;
}

interface Page_<T> {
  items: T[];
}

export async function getJson<T>(ctx: APIRequestContext, url: string): Promise<T> {
  const res = await ctx.get(url);
  expect(res.ok(), `${url} → ${res.status()}`).toBeTruthy();
  return (await res.json()) as T;
}

export async function projectId(ctx: APIRequestContext, code: string): Promise<string> {
  const page = await getJson<Page_<{ id: string; code: string }>>(ctx, `/api/v1/projects?q=${encodeURIComponent(code)}`);
  const p = page.items.find((x) => x.code === code);
  if (!p) throw new Error(`project ${code} not found`);
  return p.id;
}

export async function contractorId(ctx: APIRequestContext, code: string): Promise<string> {
  const page = await getJson<Page_<{ id: string; short_code: string }>>(ctx, `/api/v1/contractors?q=${encodeURIComponent(code)}`);
  const c = page.items.find((x) => x.short_code === code);
  if (!c) throw new Error(`contractor ${code} not found`);
  return c.id;
}

export async function userId(ctx: APIRequestContext, email: string): Promise<string> {
  const page = await getJson<Page_<{ id: string; email: string | null }>>(ctx, `/api/v1/users?q=${encodeURIComponent(email)}`);
  const u = page.items.find((x) => x.email === email);
  if (!u) throw new Error(`user ${email} not found`);
  return u.id;
}

/** Run SQL against the e2e database (test setup only: reading the email outbox, ageing tokens). */
export function sql(query: string): string {
  const db = process.env.E2E_DB_NAME ?? "hse_e2e";
  return execFileSync(
    "psql",
    ["-h", process.env.PGHOST ?? "localhost", "-p", process.env.PGPORT ?? "5432", "-U", process.env.PGUSER ?? "hse", "-d", db, "-At", "-c", query],
    { env: { ...process.env, PGPASSWORD: process.env.PGPASSWORD ?? "hse" }, encoding: "utf8" },
  ).trim();
}

/** Unique suffix for records created by a test run. */
export function uid(): string {
  return Date.now().toString(36).toUpperCase().slice(-5);
}

/** Select the first <option> whose text starts with `prefix`. */
export async function selectByPrefix(select: import("@playwright/test").Locator, prefix: string): Promise<void> {
  await expect(select.locator("option", { hasText: prefix }).first()).toBeAttached();
  const value = await select.evaluate((el, p) => {
    const opt = Array.from((el as HTMLSelectElement).options).find((o) => o.text.trim().startsWith(p));
    return opt?.value ?? "";
  }, prefix);
  if (!value) throw new Error(`no option starting with ${prefix}`);
  await select.selectOption(value);
}
