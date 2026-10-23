// Run the README importmap against the real CDNs.
//
// The importmap pins a published version. A release PR may bump it before the
// version reaches npm; the CDNs cannot serve it yet, so the check is skipped
// with a notice and runs again after publishing (npm-publish.yml).
//
// --after-publish (npm-publish.yml): the README must pin the version in
// package.json, and the check waits for it to appear on npm instead of
// skipping. The registry showed 0.8.2 about a minute after `npm publish`, so
// without waiting the post-publish check was skipped (2026-10-23).
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";
import { findCdnPackages } from "./check-cdn-delivery.mjs";

const afterPublish = process.argv.includes("--after-publish");
const WAIT_MS = 15 * 60 * 1000;
const POLL_MS = 30 * 1000;

const readme = readFileSync("README.npm.md", "utf8");
const piper = findCdnPackages(readme).find((p) => p.name === "piper-plus");
if (!piper) {
  throw new Error("README importmap does not load piper-plus from a CDN.");
}
if (afterPublish) {
  const { version } = JSON.parse(readFileSync("package.json", "utf8"));
  if (piper.version !== version) {
    throw new Error(
      `README importmap pins piper-plus@${piper.version}, but this release is ${version}.`
    );
  }
}
// npm/npx are .cmd shims on Windows and need a shell; node does not, and a
// shell would split the case name below on its spaces.
const run = (cmd, args) =>
  execFileSync(cmd, args, {
    stdio: "inherit",
    shell: process.platform === "win32" && cmd !== "node",
  });

function isPublished() {
  try {
    const out = execFileSync(
      "npm",
      ["view", `piper-plus@${piper.version}`, "version", "--json", "--prefer-online"],
      { encoding: "utf8", shell: process.platform === "win32" }
    );
    return out.trim().length > 0;
  } catch {
    return false;
  }
}

let published = isPublished();
const deadline = Date.now() + WAIT_MS;
while (!published && afterPublish && Date.now() < deadline) {
  console.log(`piper-plus@${piper.version} is not on npm yet; retrying in 30 s.`);
  await sleep(POLL_MS);
  published = isPublished();
}
if (!published) {
  if (afterPublish) {
    throw new Error(`piper-plus@${piper.version} did not appear on npm within 15 minutes.`);
  }
  console.log(
    `::notice::piper-plus@${piper.version} is not on npm yet; real-CDN README check skipped.`
  );
  process.exit(0);
}

run("node", ["test/browser/prepare-models.mjs"]);
run("npx", ["playwright", "test", "-c", "playwright.real-cdn.config.js"]);
run("node", [
  "scripts/check-browser-report.mjs",
  "test-results/real-cdn.xml",
  "README importmap on real CDNs synthesizes Japanese",
]);
