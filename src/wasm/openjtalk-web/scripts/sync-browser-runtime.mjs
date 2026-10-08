/** Keep public examples aligned with package.json's exact browser test runtime. */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const runtimeUrl = /onnxruntime-web@(\d+\.\d+\.\d+)(?=\/|\s|$)/g;

function versions(text, version) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) {
    throw new Error("Browser runtime must have an exact version pin");
  }
  const found = [...text.matchAll(runtimeUrl)].map((match) => match[1]);
  if (!found.length) throw new Error("Browser runtime URL is missing");
  return found;
}

export function checkRuntimeUrls(text, version) {
  const stale = versions(text, version).filter((actual) => actual !== version);
  if (stale.length)
    throw new Error(`Stale browser runtime ${stale.join(", ")}; expected ${version}`);
}

export function alignRuntimeUrls(text, version) {
  versions(text, version);
  return text.replace(runtimeUrl, `onnxruntime-web@${version}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = new URL("../", import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL("package.json", root), "utf8"));
  const version = manifest.devDependencies["onnxruntime-web"];
  for (const filename of ["README.npm.md", "test/multilingual-demo/index.html"]) {
    const file = new URL(filename, root);
    const text = readFileSync(file, "utf8");
    if (process.argv.includes("--write")) {
      writeFileSync(file, alignRuntimeUrls(text, version));
    } else {
      checkRuntimeUrls(text, version);
    }
  }
}
