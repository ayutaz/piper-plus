import { mkdirSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

mkdirSync("test-results", { recursive: true });
const report = "test-results/onnx-inputs.xml";
const result = spawnSync(
  process.execPath,
  [
    "--test",
    "--test-reporter=spec",
    "--test-reporter-destination=stdout",
    "--test-reporter=junit",
    `--test-reporter-destination=${report}`,
    ...process.argv.slice(2),
  ],
  { stdio: "inherit" }
);
if (result.error) {
  throw result.error;
}
if (result.status !== 0) {
  process.exit(result.status ?? 1);
}
const xml = readFileSync(report, "utf8");
const manifest = JSON.parse(readFileSync("test/fixtures/onnx-inputs/manifest.json", "utf8"));
for (const fixture of manifest) {
  if (!xml.includes(fixture.file)) {
    throw new Error(`Mandatory ONNX fixture not tested: ${fixture.file}`);
  }
}
if (!xml.includes("<testcase") || /skipped="[1-9]\d*"|<skipped(?:\s|\/?>)/.test(xml)) {
  throw new Error("Mandatory ONNX input tests must run without skipped cases.");
}
