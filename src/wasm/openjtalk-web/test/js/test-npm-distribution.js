import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { verifyDistribution } from "../../scripts/npm-distribution.mjs";

function distribution(t) {
  const root = mkdtempSync(path.join(tmpdir(), "piper-distribution-test-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const packageRoot = path.join(root, "piper-plus");
  const manifest = {
    name: "piper-plus",
    version: "0.8.0",
    exports: { ".": { import: "./src/index.js", types: "./types/index.d.ts" } },
    peerDependencies: { "onnxruntime-web": ">=1.22.0" },
  };
  const files = [
    "src/index.js",
    "types/index.d.ts",
    "src/onnx-input-contract.js",
    "assets/pinyin_single.json",
    "assets/pinyin_phrases.json",
    "dist/rust-wasm/piper_plus_wasm.js",
    "dist/rust-wasm/piper_plus_wasm_bg.wasm",
    "README.npm.md",
    "LICENSE.md",
    "THIRD-PARTY-LICENSES.md",
  ];
  for (const file of files) {
    const target = path.join(packageRoot, file);
    mkdirSync(path.dirname(target), { recursive: true });
    writeFileSync(target, "fixture");
  }
  function save() {
    writeFileSync(path.join(packageRoot, "package.json"), JSON.stringify(manifest));
  }
  save();
  return { root, packageRoot, manifest, save };
}

test("accepts a complete installed distribution of the requested version", (t) => {
  const { root } = distribution(t);
  assert.equal(verifyDistribution(root, "0.8.0").version, "0.8.0");
});

test("rejects the wrong package version", (t) => {
  const { root } = distribution(t);
  assert.throws(() => verifyDistribution(root, "0.7.0"), /version/i);
});

for (const file of [
  "src/index.js",
  "types/index.d.ts",
  "src/onnx-input-contract.js",
  "assets/pinyin_single.json",
  "assets/pinyin_phrases.json",
  "dist/rust-wasm/piper_plus_wasm_bg.wasm",
  "README.npm.md",
  "THIRD-PARTY-LICENSES.md",
]) {
  test(`rejects a distribution missing ${file}`, (t) => {
    const { root, packageRoot } = distribution(t);
    rmSync(path.join(packageRoot, file));
    assert.throws(() => verifyDistribution(root, "0.8.0"), /missing/i);
  });
}

test("rejects an export escaping the installed package", (t) => {
  const { root, manifest, save } = distribution(t);
  manifest.exports["./escape"] = "../outside.js";
  save();
  assert.throws(() => verifyDistribution(root, "0.8.0"), /export/i);
});

test("rejects an empty export map", (t) => {
  const { root, manifest, save } = distribution(t);
  manifest.exports = {};
  save();
  assert.throws(() => verifyDistribution(root, "0.8.0"), /export/i);
});

test("rejects a packed dependency rewritten to a local checkout", (t) => {
  const { root, manifest, save } = distribution(t);
  manifest.dependencies = { "@piper-plus/g2p": "file:../g2p" };
  save();
  assert.throws(() => verifyDistribution(root, "0.8.0"), /local dependency/i);
});
