import { defineConfig, devices } from "@playwright/test";

const CI = Boolean(process.env.CI);
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const BACKEND_PORT = process.env.E2E_BACKEND_PORT ?? "8000";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  // One shared seeded database: run serially so tests that change state do not race.
  fullyParallel: false,
  workers: 1,
  retries: CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    timezoneId: "Asia/Riyadh",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "bash e2e/start-backend.sh",
      url: `http://localhost:${BACKEND_PORT}/api/v1/health`,
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run start",
      url: `${BASE_URL}/en/login`,
      timeout: 120_000,
      reuseExistingServer: !CI,
    },
  ],
});
