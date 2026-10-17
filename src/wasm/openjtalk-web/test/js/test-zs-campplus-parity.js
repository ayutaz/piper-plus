/**
 * zs-v1 CAM++ embedding parity with the Python recipe, using the real model.
 *
 * The front-end golden (test-kaldi-fbank-golden.js) checks the features; this
 * checks what the demo actually feeds the base model: SpeakerEncoder with
 * frontEnd "kaldi-fbank" on the pinned campplus.onnx, against embeddings that
 * test/generate_zs_campplus_golden.py computed with torchaudio + onnxruntime
 * (the recipe in huggingface-space/zero_shot.py).
 *
 * Needs the pinned model: node test/browser/prepare-models.mjs
 * Run: npm run test:zero-shot-parity
 */

import { describe, it, before } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import * as ortNode from "onnxruntime-node";

import { SpeakerEncoder } from "../../src/speaker-encoder.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..", "..", "..", "..");
const FIXTURE = JSON.parse(
  readFileSync(join(REPO_ROOT, "test", "fixtures", "zs_campplus_golden.json"), "utf8")
);
const ZERO_SHOT = JSON.parse(
  readFileSync(join(__dirname, "..", "browser", "zero-shot-models.json"), "utf8")
);
const MODEL_PATH = join(__dirname, "..", "browser", "models", ZERO_SHOT.key, "campplus.onnx");

// Measured: cosine >= 0.9999999 and max abs <= 4e-5 on these signals
// (1.000000 on real speech). Changing one detail lands below: preemphasis
// 0.97 -> 0.96 gives 0.99969, resampler rolloff 0.99 gives 0.981, a plain
// Hann window gives 0.987.
const MIN_COSINE = 0.9999;
const MAX_ABS = 5e-4;

// onnxruntime-node has no "wasm" provider; SpeakerEncoder asks for it.
const ort = {
  ...ortNode,
  InferenceSession: {
    create: (model, options) =>
      ortNode.InferenceSession.create(model, { ...options, executionProviders: ["cpu"] }),
  },
};

// Mirrors voiced_signal() in the generator: a harmonic tone with vibrato and
// a syllable-rate envelope, high partials in the gaps (they exercise the
// resampler cutoff) and a weak white floor, computed in float64 and stored
// as float32.
function voicedSignal({ sample_rate: rate, seconds, f0, vibrato_hz, vibrato_depth_hz }) {
  const n = Math.round(rate * seconds);
  const out = new Float32Array(n);
  const floor = whiteNoise(n);
  for (let i = 0; i < n; i++) {
    const t = i / rate;
    const phase =
      2 * Math.PI * f0 * t -
      (vibrato_depth_hz / vibrato_hz) * Math.cos(2 * Math.PI * vibrato_hz * t);
    const envelope = 0.5 * (1 - Math.cos(2 * Math.PI * FIXTURE.syllable_hz * t));
    let x = 0;
    for (let k = 1; k * (f0 + vibrato_depth_hz) < rate / 2 && k <= FIXTURE.max_harmonics; k++) {
      x += (FIXTURE.amplitude / k) * Math.sin(k * phase);
    }
    let noise = 0;
    for (const [amplitude, freq] of FIXTURE.noise_partials) {
      if (freq < rate / 2) {
        noise += amplitude * Math.sin(2 * Math.PI * freq * t);
      }
    }
    out[i] = envelope * x + (1 - envelope) * noise + FIXTURE.noise_floor * floor[i];
  }
  return out;
}

// xorshift32 in [-0.5, 0.5), bit-identical to white_noise() in the generator.
function whiteNoise(n) {
  const out = new Float64Array(n);
  let x = FIXTURE.noise_seed >>> 0;
  for (let i = 0; i < n; i++) {
    x = (x ^ (x << 13)) >>> 0;
    x = (x ^ (x >>> 17)) >>> 0;
    x = (x ^ (x << 5)) >>> 0;
    out[i] = x / 2 ** 32 - 0.5;
  }
  return out;
}

function cosine(a, b) {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / Math.sqrt(na * nb);
}

describe("zs-v1 CAM++ embedding parity with the Python recipe", () => {
  let encoder;
  const embeddings = {};

  before(async () => {
    let bytes;
    try {
      bytes = readFileSync(MODEL_PATH);
    } catch (error) {
      throw new Error(
        `${MODEL_PATH} is missing; run node test/browser/prepare-models.mjs (${error.code})`
      );
    }
    const pinned = ZERO_SHOT.files.find((f) => f.local === "campplus.onnx").sha256;
    assert.equal(createHash("sha256").update(bytes).digest("hex"), pinned, "campplus.onnx hash");
    assert.equal(FIXTURE.campplus_sha256, pinned, "fixture was generated with another model");
    encoder = await SpeakerEncoder.initialize({ modelData: bytes, ort, frontEnd: "kaldi-fbank" });
  });

  for (const testCase of FIXTURE.cases) {
    it(`${testCase.name} matches Python`, async () => {
      const embedding = await encoder.encode(voicedSignal(testCase), testCase.sample_rate);
      assert.equal(embedding.length, testCase.embedding.length);
      let maxAbs = 0;
      for (let i = 0; i < embedding.length; i++) {
        maxAbs = Math.max(maxAbs, Math.abs(embedding[i] - testCase.embedding[i]));
      }
      const cos = cosine(embedding, testCase.embedding);
      assert.ok(cos >= MIN_COSINE, `cosine ${cos} < ${MIN_COSINE}`);
      assert.ok(maxAbs <= MAX_ABS, `max abs ${maxAbs} > ${MAX_ABS}`);
      embeddings[testCase.name] = embedding;
    });
  }

  it("tells different voices apart", () => {
    // Guards against a degenerate encoder that returns the same vector for
    // everything, which would pass the per-case checks above trivially only
    // if the fixture were also degenerate.
    const [low, high] = FIXTURE.distinct_pair.map((name) => embeddings[name]);
    assert.ok(low && high, "distinct_pair cases must have run");
    assert.ok(cosine(low, high) < 0.95, `cosine ${cosine(low, high)} between distinct voices`);
  });
});
