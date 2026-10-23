import { defineConfig } from "@playwright/test";
// README importmap against the real CDNs. Run through
// scripts/run-real-cdn-check.mjs, which skips versions not yet on npm.
export default defineConfig({
  testDir: "test/browser-cdn",
  timeout: 300000,
  expect: { timeout: 60000 },
  workers: 1,
  forbidOnly: !!process.env.CI,
  // Network to third-party CDNs; a failure must reproduce to count.
  retries: 2,
  reporter: [
    ["list"],
    ["junit", { outputFile: "test-results/real-cdn.xml" }],
    ["html", { open: "never", outputFolder: "playwright-report-real-cdn" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "node test/browser/server.mjs",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
  },
});
