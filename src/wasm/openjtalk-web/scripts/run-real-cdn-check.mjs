// Run the README importmap against the real CDNs.
//
// The importmap pins a published version. A release PR may bump it before the
// version reaches npm; the CDNs cannot serve it yet, so the check is skipped
// with a notice and runs again after publishing (npm-publish.yml).
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { findCdnPackages } from "./check-cdn-delivery.mjs";

const readme = readFileSync("README.npm.md", "utf8");
const piper = findCdnPackages(readme).find((p) => p.name === "piper-plus");
if (!piper) {
  throw new Error("README importmap does not load piper-plus from a CDN.");
}
// npm/npx are .cmd shims on Windows and need a shell; node does not, and a
// shell would split the case name below on its spaces.
const run = (cmd, args) =>
  execFileSync(cmd, args, {
    stdio: "inherit",
    shell: process.platform === "win32" && cmd !== "node",
  });

let published = false;
try {
  const out = execFileSync("npm", ["view", `piper-plus@${piper.version}`, "version", "--json"], {
    encoding: "utf8",
    shell: process.platform === "win32",
  });
  published = out.trim().length > 0;
} catch {
  published = false;
}
if (!published) {
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
