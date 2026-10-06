import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import * as ort from "onnxruntime-web";
import { PiperPlus } from "../../src/index.js";

ort.env.wasm.numThreads = 1;
const root = new URL("../fixtures/onnx-inputs/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("manifest.json", root), "utf8"));
console.log("ONNX Runtime Web:", ort.env.versions.web, "provider: wasm");

describe("PiperPlus speaker feeds accepted by real ORT Web WASM", () => {
  for (const fixture of manifest) {
    for (const supplied of fixture.dimension === null ? [false] : [false, true]) {
      it(`${fixture.file} embedding=${supplied ? "provided" : "default"}`, async () => {
        const bytes = readFileSync(new URL(fixture.file, root));
        assert.equal(createHash("sha256").update(bytes).digest("hex"), fixture.sha256);
        const session = await ort.InferenceSession.create(bytes, { executionProviders: ["wasm"] });
        const piper = new PiperPlus();
        piper._ort = ort; piper._config = {}; piper._session = session;
        piper._hasSpeakerEmbedding = session.inputNames.includes("speaker_embedding");
        try {
          const emb = supplied ? new Float32Array(typeof fixture.dimension === "number" ? fixture.dimension : 256).fill(0.1) : undefined;
          const infer = () => piper._infer([1, 0, 4, 0, 2], null, { noiseScale: 0.667, lengthScale: 1, noiseW: 0.8, speakerEmbedding: emb });
          if (fixture.dimension === "embedding_dim" && !supplied) {
            await assert.rejects(infer, /speaker_embedding.*dynamic/i);
          } else {
            const { audio } = await infer();
            const expected = supplied ? 0.35 : 0.25;
            assert.equal(audio.length, 16);
            assert.ok(audio.every((x) => Number.isFinite(x) && Math.abs(x - expected) < 1e-5));
          }
        } finally { await session.release(); }
      });
    }
  }
});
