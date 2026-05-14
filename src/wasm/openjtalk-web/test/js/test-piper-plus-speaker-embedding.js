/**
 * Speaker-Embedding integration tests for PiperPlus.synthesize() /
 * synthesizeFromReferenceAudio() — mock-only, no ONNX runtime required.
 *
 * Verifies the WASM-runtime parity claim that voice-cloning is wired
 * end-to-end on par with Python / Rust / Go / C# / C++ (CLAUDE.md →
 * Voice Cloning section). Mirrors the structure of
 * test-piper-plus-synthesize-flow.js.
 *
 * Run with:
 *   node --test test/js/test-piper-plus-speaker-embedding.js
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

// ---------------------------------------------------------------------------
// Minimal ort mock (Tensor constructor only — session is per-test)
// ---------------------------------------------------------------------------

globalThis.ort = {
  Tensor: class {
    constructor(type, data, dims) {
      this.type = type;
      this.data = data;
      this.dims = dims;
    }
  },
};

// ---------------------------------------------------------------------------
// Import
// ---------------------------------------------------------------------------

let PiperPlus, AudioResult;

try {
  const mod = await import("../../src/index.js");
  PiperPlus = mod.PiperPlus;
  AudioResult = mod.AudioResult;
} catch {
  // import errors → tests skip via the guard below
}

const skip = PiperPlus === undefined || PiperPlus === null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockInstance(overrides = {}) {
  const instance = new PiperPlus();

  instance._config = overrides.config || {
    audio: { sample_rate: 22050 },
    inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
    phoneme_id_map: { _: [0], "^": [1], $: [2], k: [10], o: [11], n: [12] },
  };

  const outputAudio = overrides.outputAudio || new Float32Array(22050);
  const capturedFeeds = [];

  instance._phonemizer = {
    detectLanguage: () => "ja",
    encode: () => ({
      phonemeIds: [10, 11, 12, 11, 10],
      prosodyFeatures: null,
    }),
    dispose: () => {},
    supportedLanguages: ["en", "zh", "es", "fr", "pt"],
  };

  instance._session = {
    run: async (feeds) => {
      capturedFeeds.push(feeds);
      return { output: { data: outputAudio, dims: [1, outputAudio.length] } };
    },
    release: () => {},
  };

  instance._ort = globalThis.ort;
  instance._initialized = true;

  // Expose the feeds captured during the most recent inference so tests can
  // assert what tensors were actually fed into the ONNX session.
  instance._capturedFeeds = capturedFeeds;
  return instance;
}

function zeroEmbedding(dim = 256) {
  return new Float32Array(dim);
}

function randomEmbedding(dim = 256, seed = 1) {
  // Deterministic pseudo-random (LCG) so test failures are reproducible.
  const out = new Float32Array(dim);
  let state = seed >>> 0;
  for (let i = 0; i < dim; i++) {
    state = (state * 1664525 + 1013904223) >>> 0;
    out[i] = (state / 0xffffffff) * 2 - 1;
  }
  // L2 normalise (matches Python / Rust reference encoder output).
  let sumSq = 0;
  for (let i = 0; i < dim; i++) {
    sumSq += out[i] * out[i];
  }
  const norm = Math.sqrt(sumSq);
  if (norm > 0) {
    for (let i = 0; i < dim; i++) {
      out[i] /= norm;
    }
  }
  return out;
}

// ===========================================================================
// Tests
// ===========================================================================

describe("PiperPlus.synthesize() — speakerEmbedding option", { skip }, () => {
  it("zeros 埋め込みを渡しても synthesize が AudioResult を返す", async () => {
    const instance = createMockInstance();
    const result = await instance.synthesize("こんにちは", {
      speakerEmbedding: zeroEmbedding(256),
    });
    assert.ok(result instanceof AudioResult);
    assert.equal(result.sampleRate, 22050);
    assert.ok(result.samples.length > 0);
  });

  it("ランダム正規化埋め込みを渡しても synthesize が落ちない", async () => {
    const instance = createMockInstance();
    const result = await instance.synthesize("こんにちは", {
      speakerEmbedding: randomEmbedding(256, 42),
    });
    assert.ok(result instanceof AudioResult);
    assert.ok(result.samples.length > 0);
  });

  it("speakerEmbedding 指定時に feeds に speaker_embedding テンソルが含まれる", async () => {
    const instance = createMockInstance();
    const emb = randomEmbedding(256, 7);
    await instance.synthesize("こんにちは", { speakerEmbedding: emb });

    assert.equal(instance._capturedFeeds.length, 1);
    const feeds = instance._capturedFeeds[0];
    assert.ok(feeds.speaker_embedding, "speaker_embedding tensor must be wired");
    assert.deepEqual(feeds.speaker_embedding.dims, [1, 256]);
    assert.equal(feeds.speaker_embedding.type, "float32");
    assert.strictEqual(feeds.speaker_embedding.data, emb);
    assert.ok(feeds.speaker_embedding_mask, "speaker_embedding_mask must be wired");
    assert.deepEqual(feeds.speaker_embedding_mask.dims, [1]);
  });

  it("speakerEmbedding 未指定なら feeds に speaker_embedding が含まれない (back-compat)", async () => {
    const instance = createMockInstance();
    await instance.synthesize("こんにちは");

    const feeds = instance._capturedFeeds[0];
    assert.equal(
      feeds.speaker_embedding,
      undefined,
      "synthesize() without speakerEmbedding must not attach the tensor"
    );
    assert.equal(feeds.speaker_embedding_mask, undefined);
  });

  it("Float32Array でない speakerEmbedding は TypeError を投げる", async () => {
    const instance = createMockInstance();
    await assert.rejects(
      () => instance.synthesize("こんにちは", { speakerEmbedding: [0, 0, 0] }),
      TypeError
    );
    await assert.rejects(
      () => instance.synthesize("こんにちは", { speakerEmbedding: new Array(256) }),
      TypeError
    );
  });

  it("既存の synthesizeWithVoiceCloning() は引き続き動作する (back-compat)", async () => {
    const instance = createMockInstance();
    const result = await instance.synthesizeWithVoiceCloning("こんにちは", randomEmbedding(256, 3));
    assert.ok(result instanceof AudioResult);
    const feeds = instance._capturedFeeds[0];
    assert.ok(feeds.speaker_embedding);
  });
});

describe("PiperPlus.synthesizeFromReferenceAudio() — high-level API", { skip }, () => {
  // Fake SpeakerEncoder that records inputs and returns a fixed embedding.
  function makeFakeEncoder(returnEmbedding) {
    const calls = [];
    return {
      encode: async (audio, sampleRate) => {
        calls.push({ audio, sampleRate });
        return returnEmbedding;
      },
      _calls: calls,
    };
  }

  it("encoder.encode() を呼び出して結果を synthesize に流す", async () => {
    const instance = createMockInstance();
    const emb = randomEmbedding(256, 99);
    const encoder = makeFakeEncoder(emb);
    const referenceWav = new Float32Array(16000); // 1 second of silence

    const result = await instance.synthesizeFromReferenceAudio({
      text: "こんにちは",
      referenceWav,
      encoder,
    });

    assert.ok(result instanceof AudioResult);
    assert.equal(encoder._calls.length, 1, "encoder.encode must be called exactly once");
    assert.strictEqual(encoder._calls[0].audio, referenceWav);

    const feeds = instance._capturedFeeds[0];
    assert.strictEqual(feeds.speaker_embedding.data, emb);
  });

  it("encoder が未提供だと TypeError", async () => {
    const instance = createMockInstance();
    await assert.rejects(
      () =>
        instance.synthesizeFromReferenceAudio({
          text: "x",
          referenceWav: new Float32Array(16000),
          encoder: null,
        }),
      TypeError
    );
  });

  it("encoder.encode が無い object でも TypeError", async () => {
    const instance = createMockInstance();
    await assert.rejects(
      () =>
        instance.synthesizeFromReferenceAudio({
          text: "x",
          referenceWav: new Float32Array(16000),
          encoder: {},
        }),
      TypeError
    );
  });

  it("text 無しは Error", async () => {
    const instance = createMockInstance();
    await assert.rejects(
      () =>
        instance.synthesizeFromReferenceAudio({
          text: "",
          referenceWav: new Float32Array(16000),
          encoder: makeFakeEncoder(zeroEmbedding()),
        }),
      /text is required/
    );
  });

  it("referenceWav 無しは Error", async () => {
    const instance = createMockInstance();
    await assert.rejects(
      () =>
        instance.synthesizeFromReferenceAudio({
          text: "こんにちは",
          referenceWav: null,
          encoder: makeFakeEncoder(zeroEmbedding()),
        }),
      /referenceWav is required/
    );
  });

  it("options を synthesize に転送する (language 指定)", async () => {
    const instance = createMockInstance();
    instance._config.language_id_map = { ja: 0, en: 1 };
    const encoder = makeFakeEncoder(randomEmbedding(256, 5));

    await instance.synthesizeFromReferenceAudio({
      text: "Hello",
      referenceWav: new Float32Array(16000),
      encoder,
      options: { language: "en" },
    });

    const feeds = instance._capturedFeeds[0];
    assert.ok(feeds.lid, "language id tensor must be set when language is forwarded");
  });
});

describe("PiperPlus speaker-encoder re-export", { skip }, () => {
  it("SpeakerEncoder クラスが index.js から re-export されている", async () => {
    const mod = await import("../../src/index.js");
    assert.equal(typeof mod.SpeakerEncoder, "function");
  });
});
