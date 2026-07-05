import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/support/globalSetup.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // The suite drives ONE stateful backend (single-concurrency Celery worker + one
  // naaf_e2e DB), so specs must run serially — parallel workers contend for the
  // worker and share DB state, which flakes the journey (esp. on slower CI runners).
  workers: 1,
  fullyParallel: false,
  // No retries: the suite is deterministic, and a retry would re-run the journey
  // against a non-reset DB (the scripted task title is fixed), creating a duplicate
  // that trips strict-mode selectors. A clean single failure + trace is more useful.
  retries: 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
