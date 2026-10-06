import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
const root = new URL("./models/", import.meta.url);
const models = JSON.parse(await readFile(new URL("./models.json", import.meta.url), "utf8"));
await mkdir(root, { recursive: true });
for (const model of models) {
  for (const [file, remote, hash] of [
    ["model.onnx", model.onnx, model.onnxSha256],
    ["model.onnx.json", "config.json", model.configSha256],
  ]) {
    const dir = new URL(`${model.key}/`, root);
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
      const url = `https://huggingface.co/${model.repo}/resolve/${model.revision}/${remote}`;
      console.log("Downloading pinned browser fixture:", url);
      const response = await fetch(url, { signal: globalThis.AbortSignal.timeout(120000) });
      if (!response.ok) {
        throw new Error(`${url}: ${response.status}`);
      }
      bytes = Buffer.from(await response.arrayBuffer());
      if (createHash("sha256").update(bytes).digest("hex") !== hash) {
        throw new Error(`${model.key}/${file}: SHA-256 mismatch`);
      }
      await writeFile(path, bytes);
    }
    console.log(`${model.key}/${file}: SHA-256 verified (${bytes.length} bytes)`);
  }
}
