import { test, expect } from "@playwright/test";
import {
  MIN_PINNED_SECONDS,
  PINNED_TEXT,
  observeErrors,
  observeFailedResponses,
  routeModelsToLocal,
  synthesizeWithReadmeImportmap,
} from "../browser/fixtures.mjs";

// The README importmap with the real CDNs; only the models stay local (pinned
// by hash). The tests in test/browser substitute local bytes for every CDN
// request, so they cannot see a CDN refusing a file. That is how jsDelivr's
// 50 MB limit dropped the G2P WASM unnoticed (#818).
test("README importmap on real CDNs synthesizes Japanese", async ({ page }) => {
  const errors = observeErrors(page);
  const failed = observeFailedResponses(page);
  await routeModelsToLocal(page);
  await page.goto("./readme-importmap.html");
  const ja = await synthesizeWithReadmeImportmap(page, PINNED_TEXT.ja);
  expect(failed).toEqual([]);
  expect(ja.error).toBeUndefined();
  expect(ja).toMatchObject({ finite: true, nonzero: true });
  expect(ja.seconds).toBeGreaterThan(MIN_PINNED_SECONDS);
  expect(errors).toEqual([]);
});
