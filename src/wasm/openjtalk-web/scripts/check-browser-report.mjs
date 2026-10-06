import { readFileSync } from "node:fs";
const xml = readFileSync("test-results/browser.xml", "utf8");
for (const name of ["CSS10 official demo", "README importmap", "README Basic Usage"]) {
  if (!xml.includes(`<testcase name="${name}`)) {
    throw new Error(`Mandatory browser case missing: ${name}`);
  }
}
if (/skipped="[1-9]\d*"|<skipped(?:\s|\/?>)/.test(xml)) {
  throw new Error("Mandatory browser synthesis tests must not skip.");
}
