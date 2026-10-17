import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
const root = new URL("./models/", import.meta.url);
const models = JSON.parse(await readFile(new URL("./models.json", import.meta.url), "utf8"));
// Separate file: models.json is also read by other workflows that expect
// one onnx + config.json per entry.
const zeroShot = JSON.parse(
  await readFile(new URL("./zero-shot-models.json", import.meta.url), "utf8")
);

async function fetchPinned(key, file, url, hash) {
  const dir = new URL(`${key}/`, root);
  await mkdir(dir, { recursive: true });
  const path = new URL(file, dir);
  let bytes;
  try {
    bytes = await readFile(path);
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }
  if (!bytes || createHash("sha256").update(bytes).digest("hex") !== hash) {
    console.log("Downloading pinned browser fixture:", url);
    const response = await fetch(url, { signal: globalThis.AbortSignal.timeout(120000) });
    if (!response.ok) {
      throw new Error(`${url}: ${response.status}`);
    }
    bytes = Buffer.from(await response.arrayBuffer());
    if (createHash("sha256").update(bytes).digest("hex") !== hash) {
      throw new Error(`${key}/${file}: SHA-256 mismatch`);
    }
    await writeFile(path, bytes);
  }
  console.log(`${key}/${file}: SHA-256 verified (${bytes.length} bytes)`);
}

for (const model of models) {
  for (const [file, remote, hash] of [
    ["model.onnx", model.onnx, model.onnxSha256],
    ["model.onnx.json", "config.json", model.configSha256],
  ]) {
    const url = `https://huggingface.co/${model.repo}/resolve/${model.revision}/${remote}`;
    await fetchPinned(model.key, file, url, hash);
  }
}
for (const { remote, local, sha256 } of zeroShot.files) {
  const url = `https://huggingface.co/${zeroShot.repo}/resolve/${zeroShot.revision}/${remote}`;
  await fetchPinned(zeroShot.key, local, url, sha256);
}
