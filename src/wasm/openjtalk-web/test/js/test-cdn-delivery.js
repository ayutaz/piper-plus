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

// The README is the npm package page. It must name the version it ships with:
// 0.9.0 went out with a README that installed and imported 0.8.2, and the only
// check of the pin ran after publishing (run-real-cdn-check.mjs --after-publish).
test("the npm README pins this package version and an in-range @piper-plus/g2p", () => {
  const root = new URL("../../", import.meta.url);
  const text = readFileSync(new URL("README.npm.md", root), "utf8");
  const pkg = JSON.parse(readFileSync(new URL("package.json", root), "utf8"));
  const pins = findCdnPackages(text);
  const piperPins = pins.filter((p) => p.name === "piper-plus").map((p) => p.version);
  assert.ok(piperPins.length > 0, "README importmap must load piper-plus from a CDN");
  for (const v of piperPins) {
    assert.equal(v, pkg.version, `README importmap pins piper-plus@${v}`);
  }
  for (const m of text.matchAll(/npm install piper-plus@(\S+)/g)) {
    assert.equal(m[1], pkg.version, `README installs piper-plus@${m[1]}`);
  }

  const range = pkg.dependencies["@piper-plus/g2p"];
  const caret = /^\^(\d+)\.(\d+)\.(\d+)$/.exec(range);
  assert.ok(caret, `expected a caret range for @piper-plus/g2p, got ${range}`);
  const [maj, min, pat] = caret.slice(1).map(Number);
  const g2pPins = pins.filter((p) => p.name === "@piper-plus/g2p").map((p) => p.version);
  assert.ok(g2pPins.length > 0, "README importmap must load @piper-plus/g2p from a CDN");
  for (const v of g2pPins) {
    const [a, b, c] = v.split(".").map(Number);
    // Caret below 1.0 keeps the minor version (^0.5.0 is >=0.5.0 <0.6.0).
    const ok = maj === 0 ? a === 0 && b === min && c >= pat : a === maj && (b > min || (b === min && c >= pat));
    assert.ok(ok, `README importmap pins @piper-plus/g2p@${v}, outside ${range}`);
  }
});

test("the npm README importmap does not load piper-plus from a CDN that refuses its WASM", () => {
  const text = readFileSync(new URL("../../README.npm.md", import.meta.url), "utf8");
  const packages = findCdnPackages(text).map((p) => p.name);
  assert.ok(packages.includes("piper-plus"), "README importmap must map piper-plus to a CDN");
  assert.deepEqual(checkCdnDelivery([{ source: "README.npm.md", text }], filesFor), []);
});
