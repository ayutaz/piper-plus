import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function verifyDistribution(nodeModules, expectedVersion) {
  const root = path.resolve(nodeModules, "piper-plus");
  const pkg = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8"));
  if (pkg.name !== "piper-plus" || pkg.version !== expectedVersion) {
    throw new Error(
      `Package version mismatch: ${pkg.name}@${pkg.version}, expected piper-plus@${expectedVersion}`
    );
  }
  for (const [name, spec] of Object.entries(pkg.dependencies || {})) {
    if (/^(file:|link:|workspace:)/.test(spec)) {
      throw new Error(`Distribution contains local dependency: ${name}@${spec}`);
    }
  }
  const exports = [];
  function flatten(value) {
    if (typeof value === "string") {
      exports.push(value);
    } else if (value && typeof value === "object") {
      Object.values(value).forEach(flatten);
    }
  }
  flatten(pkg.exports);
  if (!exports.length) {
    throw new Error("Package exports must not be empty");
  }
  for (const target of exports) {
    if (!target.startsWith("./") || !path.resolve(root, target).startsWith(root + path.sep)) {
      throw new Error(`Invalid package export: ${target}`);
    }
  }
  const required = [
    ...exports,
    "src/onnx-input-contract.js",
    "assets/pinyin_single.json",
    "assets/pinyin_phrases.json",
    "dist/rust-wasm/piper_plus_wasm.js",
    "dist/rust-wasm/piper_plus_wasm_bg.wasm",
    "README.npm.md",
    "LICENSE.md",
    "THIRD-PARTY-LICENSES.md",
  ];
  for (const file of required) {
    const target = path.join(root, file);
    if (!existsSync(target) || !statSync(target).isFile() || !statSync(target).size) {
      throw new Error(`Distribution missing required file: ${file}`);
    }
  }
  return pkg;
}

function run() {
  const packageRoot = path.resolve(fileURLToPath(new URL("../", import.meta.url)));
  const pkg = JSON.parse(readFileSync(path.join(packageRoot, "package.json"), "utf8"));
  if (!process.env.npm_execpath) {
    throw new Error("Run through npm run test:distribution");
  }
  const npm = (args, options = {}) =>
    execFileSync(process.execPath, [process.env.npm_execpath, ...args], {
      cwd: packageRoot,
      stdio: "inherit",
      ...options,
    });
  const consumer = mkdtempSync(path.join(tmpdir(), "piper-npm-consumer-"));
  if (!path.resolve(consumer).startsWith(path.join(tmpdir(), "piper-npm-consumer-"))) {
    throw new Error(`Unexpected cleanup path: ${consumer}`);
  }
  try {
    let tarball = process.argv[2] && path.resolve(process.argv[2]);
    if (!tarball) {
      const payload = JSON.parse(
        npm(["pack", "--json", "--pack-destination", consumer], {
          stdio: ["ignore", "pipe", "inherit"],
          encoding: "utf8",
        })
      );
      const entry = Array.isArray(payload) ? payload[0] : Object.values(payload)[0];
      tarball = path.join(consumer, entry.filename);
    }
    // The bundled Japanese dictionary makes the real package ~20 MiB compressed.
    // The old 10 MiB gate ran before WASM was downloaded and checked a different package.
    const bytes = statSync(tarball).size;
    if (bytes > 32 * 1024 * 1024) {
      throw new Error(`npm tarball exceeds 32 MiB: ${bytes}`);
    }
    console.log(`Verifying exact tarball: ${tarball} (${bytes} bytes)`);
    npm([
      "install",
      "--prefix",
      consumer,
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
      tarball,
      `onnxruntime-web@${pkg.devDependencies["onnxruntime-web"]}`,
    ]);
    const nodeModules = path.join(consumer, "node_modules");
    const installed = verifyDistribution(nodeModules, pkg.version);
    console.log(`Installed distribution verified: ${installed.name}@${installed.version}`);
    const env = { ...process.env, PIPER_PLUS_DISTRIBUTION_ROOT: nodeModules };
    delete env.PIPER_PLUS_DEMO_URL;
    npm(["run", "test:browser"], { env });
  } finally {
    rmSync(consumer, { recursive: true, force: true });
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  run();
}
