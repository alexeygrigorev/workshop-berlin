import { defineConfig, devices } from "@playwright/test";
import { BASE_URL } from "./stack";

export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.ts", // starts the compose stack; its returned function is the teardown
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
