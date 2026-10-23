// Fail when a CDN URL in the docs or the demo points at a package that holds a
// file the CDN refuses to serve.
//
// jsDelivr answers files over 50 MB with 403 "File size exceeded the
// configured limit of 50 MB." (checked 2026-10-23). The README importmap
// loaded piper-plus from jsDelivr, so the ~60 MB G2P WASM never arrived and
// Japanese synthesis went silent (#818). The browser tests could not see this
// because they substitute local bytes for every CDN request.
//
// Usage: node scripts/check-cdn-delivery.mjs
// Run after `dist/rust-wasm` is built: the WASM is the file that matters.
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** Largest file each CDN serves, in bytes. */
export const CDN_FILE_LIMITS = {
  "cdn.jsdelivr.net": 50 * 1024 * 1024,
};

const CDN_URL =
  /https:\/\/(cdn\.jsdelivr\.net)\/npm\/((?:@[\w.-]+\/)?[\w.-]+)@([\w.+-]+)\/|https:\/\/(unpkg\.com)\/((?:@[\w.-]+\/)?[\w.-]+)@([\w.+-]+)\//g;

/**
 * @param {string} text
 * @returns {{host: string, name: string, version: string}[]} unique entries
 */
export function findCdnPackages(text) {
  const seen = new Map();
  for (const m of text.matchAll(CDN_URL)) {
    const [host, name, version] = m[1] ? [m[1], m[2], m[3]] : [m[4], m[5], m[6]];
    seen.set(`${host} ${name}@${version}`, { host, name, version });
  }
  return [...seen.values()];
}

/**
 * @param {{source: string, text: string}[]} docs
 * @param {(name: string, version: string) => {path: string, size: number}[] | null} filesFor
 *   Files of the package as the CDN would serve them, or null to skip the
 *   package (for example a third-party version that is not installed).
 * @returns {string[]} problems
 */
export function checkCdnDelivery(docs, filesFor) {
  const problems = [];
  for (const { source, text } of docs) {
    for (const { host, name, version } of findCdnPackages(text)) {
      const limit = CDN_FILE_LIMITS[host];
      if (!limit) {
        continue;
      }
      const files = filesFor(name, version);
      if (!files) {
        continue;
      }
      for (const file of files) {
        if (file.size > limit) {
          problems.push(
            `${source}: ${name}@${version} is loaded from ${host}, which refuses files over ` +
              `${limit / 1024 / 1024} MB, but ${file.path} is ${file.size} bytes.`
          );
        }
      }
    }
  }
  return problems;
}

function packedFiles(dir) {
  const out = execFileSync("npm", ["pack", "--dry-run", "--json", "--ignore-scripts"], {
    cwd: dir,
    encoding: "utf8",
    shell: process.platform === "win32",
    stdio: ["ignore", "pipe", "ignore"],
  });
  return JSON.parse(out)[0].files.map((f) => ({ path: f.path, size: f.size }));
}

function installedFiles(dir) {
  const files = [];
  const walk = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "node_modules") {
          walk(full);
        }
      } else {
        files.push({ path: path.relative(dir, full), size: statSync(full).size });
      }
    }
  };
  walk(dir);
  return files;
}

function main() {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const g2pRoot = path.resolve(root, "../g2p");
  const wasm = path.join(root, "dist/rust-wasm/piper_plus_wasm_bg.wasm");
  if (!existsSync(wasm)) {
    throw new Error(`${wasm} is missing. Build the WASM first; it is the file this check is for.`);
  }

  const local = {
    "piper-plus": () => packedFiles(root),
    "@piper-plus/g2p": () => packedFiles(g2pRoot),
  };
  const cache = new Map();
  const filesFor = (name, version) => {
    const key = `${name}@${version}`;
    if (!cache.has(key)) {
      let files = null;
      if (local[name]) {
        files = local[name]();
      } else {
        // Third-party packages are checked only at the installed version.
        const dir = path.join(root, "node_modules", name);
        const manifest = path.join(dir, "package.json");
        if (
          existsSync(manifest) &&
          JSON.parse(readFileSync(manifest, "utf8")).version === version
        ) {
          files = installedFiles(dir);
        } else {
          console.log(`skip ${key}: not installed at this version`);
        }
      }
      cache.set(key, files);
    }
    return cache.get(key);
  };

  const sources = ["README.npm.md", "test/multilingual-demo/index.html"];
  const docs = sources.map((source) => ({
    source,
    text: readFileSync(path.join(root, source), "utf8"),
  }));
  const problems = checkCdnDelivery(docs, filesFor);
  for (const doc of docs) {
    for (const { host, name, version } of findCdnPackages(doc.text)) {
      console.log(`${doc.source}: ${name}@${version} via ${host}`);
    }
  }
  if (problems.length) {
    throw new Error(problems.join("\n"));
  }
  console.log("CDN delivery check passed.");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
