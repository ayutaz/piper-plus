import { defineConfig } from "@playwright/test";
const liveUrl = process.env.PIPER_PLUS_DEMO_URL;
export default defineConfig({
  testDir: "test/browser",
  timeout: 180000,
  expect: { timeout: 60000 },
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [
    ["list"],
    ["junit", { outputFile: "test-results/browser.xml" }],
    ["html", { open: "never" }],
  ],
  use: {
    baseURL: liveUrl ? `${liveUrl.replace(/\/$/, "")}/` : "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: { args: ["--autoplay-policy=no-user-gesture-required"] },
  },
  webServer: liveUrl
    ? undefined
    : {
        command: "node test/browser/server.mjs",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: false,
      },
});
