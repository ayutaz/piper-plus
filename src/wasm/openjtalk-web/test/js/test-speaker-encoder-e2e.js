/**
 * Layer-2 E2E cosine gate for the speaker encoder (JS / Node).
 *
 * Mirrors test/test_speaker_encoder_e2e.py and the corresponding
 * Rust/Go/C# tests. See docs/spec/speaker-encoder-contract.md.
 *
 * Opt-in: skips by default unless both
 *   1. The fixture has an e2e_cosine_gate block, AND
 *   2. PIPER_SPEAKER_ENCODER_ONNX_PATH points at a local encoder ONNX,
 *   3. `onnxruntime-node` is installed (peerDep, only loaded when test
 *      activates).
 *
 * Run:
 *   PIPER_SPEAKER_ENCODER_ONNX_PATH=/path/to/encoder.onnx \
 *     node --test src/wasm/openjtalk-web/test/js/test-speaker-encoder-e2e.js
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

import { computeMelSpectrogram, resampleLinearForTesting } from "../../src/speaker-encoder.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, "..", "..", "..", "..", "..");
const FIXTURE_PATH = join(REPO_ROOT, "test", "fixtures", "speaker_encoder_golden.json");

function sha256File(path) {
  const h = createHash("sha256");
  h.update(readFileSync(path));
  return h.digest("hex");
}

function cosine(a, b) {
  let dot = 0,
    na = 0,
    nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (na === 0 || nb === 0) {
    return 0;
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

// Minimal mono WAV reader (16-bit / 32-bit PCM) — we don't pull in a
// dependency since this is a single-file opt-in test.
function readMonoWav(path) {
  const buf = readFileSync(path);
  // Locate "fmt " and "data" chunks. WAV is RIFF-LE.
  if (buf.toString("ascii", 0, 4) !== "RIFF") {
    throw new Error("not a RIFF file");
  }
  if (buf.toString("ascii", 8, 12) !== "WAVE") {
    throw new Error("not a WAVE file");
  }
  let off = 12;
  let fmt = null,
    data = null;
  while (off + 8 <= buf.length) {
    const tag = buf.toString("ascii", off, off + 4);
    const size = buf.readUInt32LE(off + 4);
    if (tag === "fmt ") {
      fmt = { off: off + 8, size };
    } else if (tag === "data") {
      data = { off: off + 8, size };
    }
    off += 8 + size + (size & 1); // pad
    if (fmt && data) {
      break;
    }
  }
  if (!fmt || !data) {
    throw new Error("missing fmt/data chunks");
  }
  const audioFormat = buf.readUInt16LE(fmt.off + 0);
  const channels = buf.readUInt16LE(fmt.off + 2);
  const sampleRate = buf.readUInt32LE(fmt.off + 4);
  const bitsPerSample = buf.readUInt16LE(fmt.off + 14);
  if (channels !== 1) {
    throw new Error(`reference WAV must be mono, got ${channels}`);
  }
  if (audioFormat !== 1) {
    throw new Error(`only PCM (audioFormat=1) supported`);
  }

  const out = new Float32Array(data.size / (bitsPerSample / 8));
  if (bitsPerSample === 16) {
    for (let i = 0; i < out.length; i++) {
      out[i] = buf.readInt16LE(data.off + i * 2) / 32768;
    }
  } else if (bitsPerSample === 32) {
    for (let i = 0; i < out.length; i++) {
      out[i] = buf.readInt32LE(data.off + i * 4) / 2147483648;
    }
  } else {
    throw new Error(`unsupported bits per sample: ${bitsPerSample}`);
  }
  return { samples: out, sampleRate };
}

describe("Speaker Encoder — E2E cosine gate (layer 2)", () => {
  it("cosine(actual, expected) >= threshold", async (t) => {
    if (!existsSync(FIXTURE_PATH)) {
      t.skip(`fixture not found: ${FIXTURE_PATH}`);
      return;
    }
    const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf8"));
    const gate = fixture.e2e_cosine_gate;
    if (!gate) {
      t.skip(
        "fixture has no e2e_cosine_gate block — generator was run " +
          "without --encoder-onnx; layer-1 mel parity tests still apply"
      );
      return;
    }

    const encoderPath = process.env.PIPER_SPEAKER_ENCODER_ONNX_PATH;
    if (!encoderPath) {
      t.skip("PIPER_SPEAKER_ENCODER_ONNX_PATH not set — opt-in test, " + "skipping by default");
      return;
    }
    if (!existsSync(encoderPath)) {
      throw new Error(`PIPER_SPEAKER_ENCODER_ONNX_PATH=${encoderPath} does not exist`);
    }

    if (gate.encoder_onnx?.sha256) {
      const actualSha = sha256File(encoderPath);
      assert.equal(
        actualSha,
        gate.encoder_onnx.sha256,
        "encoder ONNX sha256 mismatch (silent upstream replacement?)"
      );
    }

    let wavPath = gate.reference_wav.path;
    if (!wavPath.startsWith("/")) {
      wavPath = join(REPO_ROOT, wavPath);
    }
    if (!existsSync(wavPath)) {
      t.skip(`reference WAV not found at ${wavPath}`);
      return;
    }

    // Lazy ort import — only loaded on the active path.
    let ort;
    try {
      ort = await import("onnxruntime-node");
    } catch {
      try {
        ort = await import("onnxruntime-web");
      } catch {
        t.skip(
          "neither onnxruntime-node nor onnxruntime-web is available; " +
            "install onnxruntime-node as a devDependency to enable E2E gate"
        );
        return;
      }
    }

    const { samples: rawSamples, sampleRate } = readMonoWav(wavPath);
    const samples =
      sampleRate === 16000 ? rawSamples : resampleLinearForTesting(rawSamples, sampleRate, 16000);

    // computeMelSpectrogram returns frame-major (CAM++ canonical):
    // mel[frameIdx * N_MELS + melIdx], shape [n_frames * n_mels].
    const mel = computeMelSpectrogram(samples);
    const N_MELS = 80;
    const nFrames = mel.length / N_MELS;

    const sess = await ort.default.InferenceSession.create(encoderPath);
    const inputName = sess.inputNames[0];
    const inputMeta = sess.inputMetadata?.[inputName];
    const inputShape = inputMeta?.dimensions ?? [1, nFrames, N_MELS];

    let feed;
    if (inputShape.length === 3 && Number(inputShape[2]) === N_MELS) {
      // CAM++ / canonical: [batch, T, 80] — feed our frame-major mel directly.
      feed = new ort.default.Tensor("float32", mel, [1, nFrames, N_MELS]);
    } else if (inputShape.length === 3 && Number(inputShape[1]) === N_MELS) {
      // Legacy / mel-major encoder: transpose from frame-major to [N_MELS, T].
      const t = new Float32Array(N_MELS * nFrames);
      for (let f = 0; f < nFrames; f++) {
        for (let m = 0; m < N_MELS; m++) {
          t[m * nFrames + f] = mel[f * N_MELS + m];
        }
      }
      feed = new ort.default.Tensor("float32", t, [1, N_MELS, nFrames]);
    } else {
      // Fall back to the canonical [batch, T, 80] layout.
      feed = new ort.default.Tensor("float32", mel, [1, nFrames, N_MELS]);
    }

    const result = await sess.run({ [inputName]: feed });
    const outName = sess.outputNames[0];
    const actualEmbedding = Array.from(result[outName].data);

    assert.equal(
      actualEmbedding.length,
      gate.expected_embedding.values.length,
      "embedding dim drift"
    );

    const cos = cosine(actualEmbedding, gate.expected_embedding.values);
    assert.ok(
      cos >= gate.cosine_threshold,
      `cosine gate failed: cos=${cos.toFixed(6)} < ` +
        `threshold=${gate.cosine_threshold.toFixed(6)} ` +
        `(encoder=${encoderPath}, wav=${wavPath})`
    );
  });
});
