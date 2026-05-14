/**
 * SSML synthesis integration tests for `piper-plus` (openjtalk-web).
 *
 * Verifies that:
 *   1. The high-level package re-exports `isSsml` / `parseSsml` / `SsmlParser`
 *      so consumers do not need a second package dependency.
 *   2. `synthesize()` auto-detects SSML and dispatches to `synthesizeSsml`.
 *   3. `synthesizeSsml()` iterates segments, calls `_infer` once per text
 *      segment with the segment-local `length_scale`, and concatenates the
 *      resulting audio with `<break>` silence between segments.
 *   4. The cross-runtime fixture (`tests/fixtures/ssml/contract.json`) is
 *      consistent with the constants the runtime relies on (byte-for-byte).
 *
 * Run with: node --test test/js/test-piper-plus-ssml.js
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

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
// Import the package under test.
// ---------------------------------------------------------------------------

let PiperPlus, AudioResult, isSsml, parseSsml, SsmlParser;
let importError = null;

try {
  const mod = await import("../../src/index.js");
  PiperPlus = mod.PiperPlus;
  AudioResult = mod.AudioResult;
  isSsml = mod.isSsml;
  parseSsml = mod.parseSsml;
  SsmlParser = mod.SsmlParser;
} catch (e) {
  importError = e;
}

const skip = PiperPlus === null || PiperPlus === undefined;
if (importError) {
  // Surface the import error so test failures are debuggable.
  console.error("SSML test suite import error:", importError);
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/**
 * Build a mock PiperPlus instance whose `_infer` simply records the call
 * arguments and returns a fixed-size silence buffer. This lets us assert
 * which segments were inferred and with which length_scale, without
 * loading an actual ONNX model.
 */
function createMockInstance(overrides = {}) {
  const instance = new PiperPlus();

  const calls = [];
  const samplesPerCall = overrides.samplesPerCall ?? 1000;

  instance._config = overrides.config || {
    audio: { sample_rate: 22050 },
    inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
  };

  instance._phonemizer = {
    detectLanguage: () => "en",
    encode: () => ({ phonemeIds: [1, 2, 3], prosodyFeatures: null }),
    dispose: () => {},
    supportedLanguages: ["en", "ja"],
  };

  // We bypass the real phonemizer path by stubbing `_textToPhonemeIds`.
  instance._textToPhonemeIds = async (text, _lang) => ({
    phonemeIds: [1, 2, 3, text.length], // include text length so we can tell segments apart
    prosodyFeatures: null,
  });

  instance._detectLanguage = () => "en";

  instance._infer = async (phonemeIds, prosodyFeatures, opts) => {
    calls.push({
      phonemeIds: Array.from(phonemeIds),
      lengthScale: opts.lengthScale,
      noiseScale: opts.noiseScale,
      noiseW: opts.noiseW,
      language: opts.language,
    });
    return { audio: new Float32Array(samplesPerCall), durations: null };
  };

  instance._initialized = true;
  return { instance, calls };
}

// ===========================================================================
// 1. Re-exports
// ===========================================================================

describe("piper-plus: SSML re-exports", { skip }, () => {
  it("re-exports isSsml", () => {
    assert.equal(typeof isSsml, "function");
    assert.equal(isSsml("<speak>hi</speak>"), true);
    assert.equal(isSsml("plain"), false);
  });

  it("re-exports parseSsml", () => {
    assert.equal(typeof parseSsml, "function");
    const segs = parseSsml('<speak>A<break time="500ms"/>B</speak>');
    assert.equal(segs.length, 3);
    assert.equal(segs[0].text, "A");
    assert.equal(segs[1].breakMs, 500);
    assert.equal(segs[2].text, "B");
  });

  it("re-exports SsmlParser class", () => {
    assert.equal(typeof SsmlParser, "function");
    assert.equal(SsmlParser.isSsml("<speak/>"), false); // self-closing root is not detected
    assert.equal(SsmlParser.isSsml("<speak>x</speak>"), true);
  });
});

// ===========================================================================
// 2. synthesize() auto-detects SSML and dispatches
// ===========================================================================

describe("piper-plus.synthesize(): SSML auto-detect", { skip }, () => {
  it("dispatches to synthesizeSsml when input starts with <speak>", async () => {
    const { instance, calls } = createMockInstance();
    const result = await instance.synthesize('<speak>Hello<break time="100ms"/>World</speak>');
    assert.ok(result instanceof AudioResult);
    // Two text segments => two _infer calls.
    assert.equal(calls.length, 2);
  });

  it("plain text bypasses SSML path", async () => {
    const { instance, calls } = createMockInstance();
    const result = await instance.synthesize("Just plain text.");
    assert.ok(result instanceof AudioResult);
    assert.equal(calls.length, 1);
  });

  it("options.ssml=false disables auto-detect (treats input as plain)", async () => {
    const { instance, calls } = createMockInstance();
    // Even though the input *looks* like SSML, ssml:false forces plain-text.
    const result = await instance.synthesize("<speak>x</speak>", { ssml: false });
    assert.ok(result instanceof AudioResult);
    assert.equal(calls.length, 1);
  });
});

// ===========================================================================
// 3. synthesizeSsml() behaviour
// ===========================================================================

describe("piper-plus.synthesizeSsml()", { skip }, () => {
  it("returns an AudioResult", async () => {
    const { instance } = createMockInstance();
    const result = await instance.synthesizeSsml("<speak>Hello</speak>");
    assert.ok(result instanceof AudioResult);
    assert.equal(result.sampleRate, 22050);
  });

  it("calls _infer once per text segment", async () => {
    const { instance, calls } = createMockInstance();
    await instance.synthesizeSsml('<speak>A<break time="200ms"/>B<break time="300ms"/>C</speak>');
    assert.equal(calls.length, 3);
  });

  it("applies <prosody rate> to length_scale", async () => {
    const { instance, calls } = createMockInstance();
    await instance.synthesizeSsml('<speak><prosody rate="slow">slow</prosody> normal</speak>');
    assert.equal(calls.length, 2);
    // slow => 1.25
    assert.equal(calls[0].lengthScale, 1.25);
    // tail at root => 1.0
    assert.equal(calls[1].lengthScale, 1.0);
  });

  it("compounds <prosody rate=%> with the base length_scale", async () => {
    const { instance, calls } = createMockInstance();
    await instance.synthesizeSsml('<speak><prosody rate="50%">double-length</prosody></speak>', {
      lengthScale: 1.2,
    });
    assert.equal(calls.length, 1);
    // base 1.2 * (100/50 = 2.0) = 2.4
    assert.ok(Math.abs(calls[0].lengthScale - 2.4) < 1e-9);
  });

  it("inserts silence between segments based on <break time>", async () => {
    const { instance } = createMockInstance({ samplesPerCall: 1000 });
    // 100ms @ 22050 Hz = 2205 samples between two 1000-sample chunks.
    const result = await instance.synthesizeSsml('<speak>A<break time="100ms"/>B</speak>');
    // 1000 + 2205 + 1000 = 4205 samples
    assert.equal(result.samples.length, 1000 + 2205 + 1000);
    // The silence frames should be all zeros.
    for (let i = 1000; i < 1000 + 2205; i++) {
      assert.equal(result.samples[i], 0);
    }
  });

  it("uses <break strength=medium> = 400ms by default", async () => {
    const { instance } = createMockInstance({ samplesPerCall: 100 });
    const result = await instance.synthesizeSsml(
      "<speak>A<break/>B</speak>" // no attrs => medium => 400ms
    );
    // 400ms @ 22050 Hz = 8820 samples
    assert.equal(result.samples.length, 100 + 8820 + 100);
  });

  it("non-SSML input becomes a single text segment", async () => {
    const { instance, calls } = createMockInstance();
    const result = await instance.synthesizeSsml("plain text");
    assert.ok(result instanceof AudioResult);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].lengthScale, 1.0);
  });

  it("rejects empty string", async () => {
    const { instance } = createMockInstance();
    await assert.rejects(() => instance.synthesizeSsml(""), /required/);
  });

  it("rejects non-string input", async () => {
    const { instance } = createMockInstance();
    await assert.rejects(() => instance.synthesizeSsml(null), /required/);
    await assert.rejects(() => instance.synthesizeSsml(undefined), /required/);
    await assert.rejects(() => instance.synthesizeSsml(42), /required/);
  });

  it("empty <speak></speak> yields a zero-length AudioResult", async () => {
    const { instance, calls } = createMockInstance();
    const result = await instance.synthesizeSsml("<speak></speak>");
    // parseSsml returns a single empty segment; our iterator skips it
    // because text.length === 0 AND breakMs === 0 (filtered by mergeSegments).
    assert.equal(calls.length, 0);
    assert.equal(result.samples.length, 0);
  });
});

// ===========================================================================
// 4. Cross-runtime fixture parity
// ===========================================================================
//
// `tests/fixtures/ssml/contract.json` is the canonical fixture used by
// Rust/Go/C#/(now WASM) implementations to pin their constants against the
// Python source-of-truth. We verify that the same constants are visible to
// the JS runtime via the re-exported parser.

describe("piper-plus: SSML contract fixture parity", { skip }, () => {
  const fixturePath = fileURLToPath(
    new URL("../../../../../tests/fixtures/ssml/contract.json", import.meta.url)
  );
  const fixture = JSON.parse(readFileSync(fixturePath, "utf-8"));

  it("break_strength.map matches parseSsml output", () => {
    for (const [name, expectedMs] of Object.entries(fixture.break_strength.map)) {
      const segs = parseSsml(`<speak><break strength="${name}"/></speak>`);
      // First (and only) segment has the break.
      assert.equal(segs[0].breakMs, expectedMs, `break strength="${name}" => ${expectedMs}ms`);
    }
  });

  it("break_strength default (medium) matches", () => {
    const segs = parseSsml("<speak><break/></speak>");
    assert.equal(segs[0].breakMs, fixture.break_strength.default_ms);
  });

  it("unknown strength falls back to default", () => {
    const segs = parseSsml('<speak><break strength="unrecognised"/></speak>');
    assert.equal(segs[0].breakMs, fixture.break_strength.unknown_strength_fallback_ms);
  });

  it("prosody_rate.named_map matches parseSsml output", () => {
    for (const [name, expectedRate] of Object.entries(fixture.prosody_rate.named_map)) {
      const segs = parseSsml(`<speak><prosody rate="${name}">x</prosody></speak>`);
      assert.equal(segs[0].rate, expectedRate, `prosody rate="${name}" => ${expectedRate}`);
    }
  });

  it("prosody_rate percent formula matches", () => {
    const segs = parseSsml('<speak><prosody rate="150%">x</prosody></speak>');
    // length_scale = 100 / 150
    assert.ok(Math.abs(segs[0].rate - 100.0 / 150.0) < 1e-9);
  });

  it("segment_defaults matches plain-text output", () => {
    const segs = parseSsml("hello"); // plain
    assert.equal(segs[0].breakMs, fixture.segment_defaults.break_ms);
    assert.equal(segs[0].rate, fixture.segment_defaults.rate);
  });

  it("detection regex matches", () => {
    // We don't construct the regex here (it lives in ssml.js); we test that
    // its behaviour matches the fixture's intent.
    assert.equal(isSsml("<speak>x</speak>"), true);
    assert.equal(isSsml("  <speak>x</speak>"), true);
    assert.equal(isSsml("<SPEAK>x</SPEAK>"), false); // case-sensitive
    assert.equal(isSsml("<speakers>x</speakers>"), false);
  });
});
