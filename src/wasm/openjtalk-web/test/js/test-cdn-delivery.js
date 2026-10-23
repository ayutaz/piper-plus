import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  CDN_FILE_LIMITS,
  checkCdnDelivery,
  findCdnPackages,
} from "../../scripts/check-cdn-delivery.mjs";

const MB = 1024 * 1024;
// The bundled G2P WASM of 0.8.1 is 60,070,390 bytes.
const piperFiles = [
  { path: "src/index.js", size: 46433 },
  { path: "dist/rust-wasm/piper_plus_wasm_bg.wasm", size: 60070390 },
];
const filesFor = (name) => (name === "piper-plus" ? piperFiles : [{ path: "a.js", size: MB }]);

test("finds scoped and unscoped packages on both CDNs", () => {
  const text = `
    "piper-plus": "https://unpkg.com/piper-plus@0.8.1/src/index.js",
    "@piper-plus/g2p": "https://cdn.jsdelivr.net/npm/@piper-plus/g2p@0.4.2/src/index.js",
    "onnxruntime-web": "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/ort.min.mjs"`;
  assert.deepEqual(findCdnPackages(text), [
    { host: "unpkg.com", name: "piper-plus", version: "0.8.1" },
    { host: "cdn.jsdelivr.net", name: "@piper-plus/g2p", version: "0.4.2" },
    { host: "cdn.jsdelivr.net", name: "onnxruntime-web", version: "1.30.0" },
  ]);
});

test("jsDelivr limit is 50 MB", () => {
  assert.equal(CDN_FILE_LIMITS["cdn.jsdelivr.net"], 50 * MB);
});

test("rejects piper-plus on jsDelivr when it ships a file over 50 MB (#818)", () => {
  const text = '"piper-plus": "https://cdn.jsdelivr.net/npm/piper-plus@0.8.1/src/index.js"';
  const problems = checkCdnDelivery([{ source: "README.npm.md", text }], filesFor);
  assert.equal(problems.length, 1);
  assert.match(problems[0], /piper_plus_wasm_bg\.wasm is 60070390 bytes/);
});

test("accepts the same package on unpkg", () => {
  const text = '"piper-plus": "https://unpkg.com/piper-plus@0.8.1/src/index.js"';
  assert.deepEqual(checkCdnDelivery([{ source: "README.npm.md", text }], filesFor), []);
});

test("skips packages the caller cannot resolve", () => {
  const text = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.21.0/dist/ort.min.js";
  assert.deepEqual(
    checkCdnDelivery([{ source: "x", text }], () => null),
    []
  );
});

test("the npm README importmap does not load piper-plus from a CDN that refuses its WASM", () => {
  const text = readFileSync(new URL("../../README.npm.md", import.meta.url), "utf8");
  const packages = findCdnPackages(text).map((p) => p.name);
  assert.ok(packages.includes("piper-plus"), "README importmap must map piper-plus to a CDN");
  assert.deepEqual(checkCdnDelivery([{ source: "README.npm.md", text }], filesFor), []);
});
