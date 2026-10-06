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
  it("initializes capabilities before public synthesize with no embedding", async () => {
    const session = await ort.InferenceSession.create(
      readFileSync(new URL("speaker-256-mask2.onnx", root)),
      { executionProviders: ["wasm"] }
    );
    let released = false;
    const trackedSession = {
      inputNames: session.inputNames,
      inputMetadata: session.inputMetadata,
      run: session.run.bind(session),
      release: async () => {
        released = true;
        await session.release();
      },
    };
    const savedFetch = globalThis.fetch;
    let piper;
    try {
      globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({
          audio: { sample_rate: 22050 },
          language_id_map: { en: 0 },
          phoneme_id_map: { _: [0], "^": [1], $: [2], a: [4] },
        }),
      });
      piper = await PiperPlus.initialize({
        model: "https://models.test/model.onnx",
        ort: { Tensor: ort.Tensor, InferenceSession: { create: async () => trackedSession } },
      });
      const audio = await piper.synthesize("Hello, this is a regression test.", { language: "en" });
      assert.ok(audio.samples.length > 0);
      assert.ok(audio.samples.every(Number.isFinite));
    } finally {
      globalThis.fetch = savedFetch;
      if (piper) {
        piper.dispose();
      } else if (!released) {
        await session.release();
      }
    }
  });
  it("refreshes speaker dimensions when falling back to a recreated session", async () => {
    const replacement = await ort.InferenceSession.create(
      readFileSync(new URL("speaker-192-mask2.onnx", root)),
      { executionProviders: ["wasm"] }
    );
    const piper = new PiperPlus();
    piper._ort = ort;
    piper._config = { language_id_map: { en: 0 } };
    piper._session = {
      inputNames: replacement.inputNames,
      inputMetadata: replacement.inputMetadata.map((m) =>
        m.name === "speaker_embedding" ? { ...m, shape: ["batch", 256] } : m
      ),
      run: async () => {
        throw new Error("Unsupported data type");
      },
    };
    piper._sessionManager = { currentProvider: "webgpu", createSession: async () => replacement };
    try {
      const { audio } = await piper._infer([1, 0, 4, 0, 2], null, {
        noiseScale: 0.667,
        lengthScale: 1,
        noiseW: 0.8,
        language: "en",
      });
      assert.equal(audio.length, 16);
      assert.equal(piper._speakerInputContract.embedding.shape[1], 192);
    } finally {
      await replacement.release();
    }
  });
  for (const fixture of manifest) {
    for (const supplied of fixture.dimension === null ? [false] : [false, true]) {
      it(`${fixture.file} embedding=${supplied ? "provided" : "default"}`, async () => {
        const bytes = readFileSync(new URL(fixture.file, root));
        assert.equal(createHash("sha256").update(bytes).digest("hex"), fixture.sha256);
        const session = await ort.InferenceSession.create(bytes, { executionProviders: ["wasm"] });
        const piper = new PiperPlus();
        piper._ort = ort;
        piper._config = { language_id_map: { en: 0 } };
        piper._session = session;
        piper._hasSpeakerEmbedding = session.inputNames.includes("speaker_embedding");
        try {
          const emb = supplied
            ? new Float32Array(
                typeof fixture.dimension === "number" ? fixture.dimension : 256
              ).fill(0.1)
            : undefined;
          const infer = () =>
            piper._infer([1, 0, 4, 0, 2], null, {
              noiseScale: 0.667,
              lengthScale: 1,
              noiseW: 0.8,
              speakerEmbedding: emb,
              language: "en",
            });
          if (fixture.dimension === "embedding_dim" && !supplied) {
            await assert.rejects(infer, /speaker_embedding.*dynamic/i);
          } else {
            const { audio } = await infer();
            const expected = supplied ? 0.35 : 0.25;
            assert.equal(audio.length, 16);
            assert.ok(audio.every((x) => Number.isFinite(x) && Math.abs(x - expected) < 1e-5));
          }
        } finally {
          await session.release();
        }
      });
    }
  }
});
