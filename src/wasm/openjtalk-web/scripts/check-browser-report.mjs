import { readFileSync } from "node:fs";
// Usage: check-browser-report.mjs [report.xml case-name...]
// Without arguments, checks the default browser synthesis report.
const [report = "test-results/browser.xml", ...names] = process.argv.slice(2);
const mandatory = names.length
  ? names
  : [
      "CSS10 official demo",
      "README importmap",
      "README Basic Usage",
      "README importmap synthesizes Japanese at full length",
      "WASM fetch failure rejects Japanese and Chinese but keeps English",
    ];
const xml = readFileSync(report, "utf8");
for (const name of mandatory) {
  if (!xml.includes(`<testcase name="${name}`)) {
    throw new Error(`Mandatory browser case missing: ${name}`);
  }
}
if (/skipped="[1-9]\d*"|<skipped(?:\s|\/?>)/.test(xml)) {
  throw new Error("Mandatory browser synthesis tests must not skip.");
}
