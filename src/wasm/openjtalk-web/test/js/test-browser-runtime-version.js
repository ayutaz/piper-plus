import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { alignRuntimeUrls, checkRuntimeUrls } from "../../scripts/sync-browser-runtime.mjs";

test("rejects a stale runtime URL without substituting installed bytes", () => {
  const text = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/ort.min.mjs";
  assert.throws(() => checkRuntimeUrls(text, "1.30.0"), /1.22.0/);
});

test("aligns both script and module URLs to the manifest pin", () => {
  const text = "onnxruntime-web@1.22.0/dist/ort.min.js onnxruntime-web@1.21.0/dist/ort.min.mjs";
  const result = alignRuntimeUrls(text, "1.30.0");
  assert.equal(
    result,
    "onnxruntime-web@1.30.0/dist/ort.min.js onnxruntime-web@1.30.0/dist/ort.min.mjs"
  );
  checkRuntimeUrls(result, "1.30.0");
});

test("missing URLs and non-exact pins cannot silently pass", () => {
  assert.throws(() => checkRuntimeUrls("no runtime dependency", "1.30.0"), /missing/i);
  assert.throws(() => alignRuntimeUrls("onnxruntime-web@1.22.0/", "^1.30.0"), /exact/i);
});

test("active demo and npm README use the manifest browser runtime", () => {
  const root = new URL("../../", import.meta.url);
  const pin = JSON.parse(readFileSync(new URL("package.json", root), "utf8")).devDependencies[
    "onnxruntime-web"
  ];
  for (const path of ["README.npm.md", "test/multilingual-demo/index.html"]) {
    checkRuntimeUrls(readFileSync(new URL(path, root), "utf8"), pin);
  }
});
