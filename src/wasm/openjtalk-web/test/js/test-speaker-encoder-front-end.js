/**
 * SpeakerEncoder front-end selection (`frontEnd` option).
 *
 * "mel" (default) keeps the mel front end shared with the Rust/Go/C#
 * runtimes. "kaldi-fbank" reproduces the recipe the public zs-v1 base was
 * verified with: kaiser_best resample -> Kaldi fbank -> mean subtraction ->
 * CAM++ -> L2 normalization. A fake onnxruntime records the encoder input.
 *
 * Run: node --test src/wasm/openjtalk-web/test/js/test-speaker-encoder-front-end.js
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { SpeakerEncoder, computeMelSpectrogram } from "../../src/speaker-encoder.js";
import { kaldiFbank, resampleKaiserBest, KALDI_FBANK_NUM_MEL_BINS } from "../../src/kaldi-fbank.js";

function fakeOrt(output = [3, 4]) {
  const fake = {
    created: [],
    feeds: [],
    Tensor: class {
      constructor(type, data, dims) {
        Object.assign(this, { type, data, dims });
      }
    },
    InferenceSession: {
      create: async (model, options) => {
        fake.created.push({ model, options });
        return {
          inputNames: ["input"],
          run: async (feeds) => {
            fake.feeds.push(feeds);
            return { output: { data: Float32Array.from(output) } };
          },
        };
      },
    },
  };
  return fake;
}

function tone(sampleRate, seconds) {
  const out = new Float32Array(Math.round(sampleRate * seconds));
  for (let i = 0; i < out.length; i++) {
    out[i] = 0.4 * Math.sin((2 * Math.PI * 220 * i) / sampleRate) + 0.1 * Math.sin(i / 3);
  }
  return out;
}

describe("SpeakerEncoder frontEnd: mel (default)", () => {
  it("feeds the runtime mel spectrogram and returns the raw embedding", async () => {
    const ort = fakeOrt();
    const encoder = await SpeakerEncoder.initialize({ modelUrl: "enc.onnx", ort });
    const audio = tone(16000, 0.5);
    const embedding = await encoder.encode(audio, 16000);

    const tensor = ort.feeds[0].input;
    const expected = computeMelSpectrogram(audio);
    assert.deepEqual(tensor.dims, [1, expected.length / 80, 80]);
    assert.deepEqual(tensor.data, expected);
    assert.deepEqual(Array.from(embedding), [3, 4]);
  });
});

describe("SpeakerEncoder frontEnd: kaldi-fbank", () => {
  it("feeds mean-subtracted Kaldi fbank of the kaiser_best-resampled audio", async () => {
    const ort = fakeOrt();
    const encoder = await SpeakerEncoder.initialize({
      modelUrl: "campplus.onnx",
      ort,
      frontEnd: "kaldi-fbank",
    });
    const audio = tone(48000, 0.5);
    await encoder.encode(audio, 48000);

    const feats = kaldiFbank(resampleKaiserBest(audio, 48000, 16000));
    const frames = feats.length / KALDI_FBANK_NUM_MEL_BINS;
    const tensor = ort.feeds[0].input;
    assert.deepEqual(tensor.dims, [1, frames, KALDI_FBANK_NUM_MEL_BINS]);
    for (let m = 0; m < KALDI_FBANK_NUM_MEL_BINS; m++) {
      let mean = 0;
      for (let f = 0; f < frames; f++) {
        mean += feats[f * KALDI_FBANK_NUM_MEL_BINS + m];
      }
      mean /= frames;
      for (let f = 0; f < frames; f++) {
        const i = f * KALDI_FBANK_NUM_MEL_BINS + m;
        assert.ok(Math.abs(tensor.data[i] - (feats[i] - mean)) < 1e-5);
      }
    }
  });

  it("L2-normalizes the embedding", async () => {
    const encoder = await SpeakerEncoder.initialize({
      modelUrl: "campplus.onnx",
      ort: fakeOrt([3, 4]),
      frontEnd: "kaldi-fbank",
    });
    const embedding = await encoder.encode(tone(16000, 0.5), 16000);
    assert.ok(embedding instanceof Float32Array);
    assert.ok(Math.abs(embedding[0] - 0.6) < 1e-7);
    assert.ok(Math.abs(embedding[1] - 0.8) < 1e-7);
  });

  it("rejects a zero or non-finite embedding", async () => {
    for (const output of [
      [0, 0],
      [1, Number.NaN],
    ]) {
      const encoder = await SpeakerEncoder.initialize({
        modelUrl: "campplus.onnx",
        ort: fakeOrt(output),
        frontEnd: "kaldi-fbank",
      });
      await assert.rejects(encoder.encode(tone(16000, 0.5), 16000), /embedding/);
    }
  });

  it("rejects audio shorter than one 25 ms frame", async () => {
    const encoder = await SpeakerEncoder.initialize({
      modelUrl: "campplus.onnx",
      ort: fakeOrt(),
      frontEnd: "kaldi-fbank",
    });
    await assert.rejects(encoder.encode(new Float32Array(399), 16000), /too short/);
  });
});

describe("SpeakerEncoder.initialize options", () => {
  it("rejects an unknown frontEnd", async () => {
    await assert.rejects(
      SpeakerEncoder.initialize({ modelUrl: "enc.onnx", ort: fakeOrt(), frontEnd: "mfcc" }),
      /frontEnd/
    );
  });

  it("accepts model bytes via modelData", async () => {
    const ort = fakeOrt();
    const bytes = new Uint8Array([1, 2, 3]);
    await SpeakerEncoder.initialize({ modelData: bytes, ort });
    assert.equal(ort.created[0].model, bytes);
  });

  it("requires modelUrl or modelData", async () => {
    await assert.rejects(SpeakerEncoder.initialize({ ort: fakeOrt() }), /modelUrl/);
  });
});
