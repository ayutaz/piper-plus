/**
 * Unit Tests for AudioResult.timing / AudioResult.hasTimingInfo
 * npm パッケージ: TTS 出力オーディオラッパー (タイミング情報)
 *
 * テスト対象: src/wasm/openjtalk-web/src/audio-result.js
 *
 * AudioResult は新たに以下の機能を持つ:
 *   - constructor(samples, sampleRate = 22050, timing = null)
 *   - get timing      -> TimingResult | null
 *   - get hasTimingInfo -> boolean
 *
 * 既存の samples / sampleRate / duration / toWav() がタイミング引数の有無で
 * 影響を受けないことも併せて検証する。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { AudioResult } from "../../src/audio-result.js";

// -----------------------------------------------------------
// Sample TimingResult-like object used across tests.
// -----------------------------------------------------------
function makeSampleTiming() {
  return {
    phonemes: [
      { phoneme: "ph_0", start_ms: 0, end_ms: 58, duration_ms: 58 },
      { phoneme: "ph_1", start_ms: 58, end_ms: 150.8, duration_ms: 92.8 },
    ],
    total_duration_ms: 150.8,
    sample_rate: 22050,
  };
}

describe("AudioResult.timing / hasTimingInfo", () => {
  // -------------------------------------------------------
  // 1. constructor without timing
  // -------------------------------------------------------
  it("constructor without timing -> timing === null, hasTimingInfo === false", () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const result = new AudioResult(samples, 22050);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  // -------------------------------------------------------
  // 2. constructor with explicit null timing
  // -------------------------------------------------------
  it("constructor with explicit null timing -> timing === null, hasTimingInfo === false", () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const result = new AudioResult(samples, 22050, null);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  // -------------------------------------------------------
  // 3. constructor with timing object
  // -------------------------------------------------------
  it("constructor with timing object -> getter returns the same object", () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    assert.strictEqual(result.timing, timing);
    assert.deepStrictEqual(result.timing, makeSampleTiming());
  });

  // -------------------------------------------------------
  // 4. hasTimingInfo true when timing is provided
  // -------------------------------------------------------
  it("hasTimingInfo === true when timing is provided", () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    assert.strictEqual(result.hasTimingInfo, true);
  });

  // -------------------------------------------------------
  // 5. hasTimingInfo false with explicit null
  // -------------------------------------------------------
  it("hasTimingInfo === false when timing is explicit null", () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const result = new AudioResult(samples, 22050, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  // -------------------------------------------------------
  // 6. hasTimingInfo false with undefined
  // -------------------------------------------------------
  it("hasTimingInfo === false when timing is undefined", () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    // Passing undefined should fall back to the constructor default (null)
    // and therefore behave identically to omitting the argument.
    const result = new AudioResult(samples, 22050, undefined);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  // -------------------------------------------------------
  // 7. timing getter returns the same reference for repeated calls
  // -------------------------------------------------------
  it("timing getter returns the same reference for repeated calls", () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    const first = result.timing;
    const second = result.timing;
    assert.strictEqual(first, second);
    assert.strictEqual(first, timing);
  });

  // -------------------------------------------------------
  // 8. backward compatibility: omitting the timing argument
  // -------------------------------------------------------
  it("backward compatibility: omitting the timing argument defaults to null", () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    // Two-argument form (samples, sampleRate) used by all pre-timing callers.
    const result = new AudioResult(samples, 22050);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
    // Single-argument form (samples) using the default sampleRate.
    const resultDefault = new AudioResult(samples);
    assert.strictEqual(resultDefault.timing, null);
    assert.strictEqual(resultDefault.hasTimingInfo, false);
    assert.strictEqual(resultDefault.sampleRate, 22050);
  });

  // -------------------------------------------------------
  // 9. samples getter still works with timing
  // -------------------------------------------------------
  it("samples getter is unaffected by timing", () => {
    const samples = new Float32Array([0.5, -0.5, 0.0, 0.25]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    assert.strictEqual(result.samples, samples);
    assert.strictEqual(result.samples.length, 4);
  });

  // -------------------------------------------------------
  // 10. sampleRate getter still works with timing
  // -------------------------------------------------------
  it("sampleRate getter is unaffected by timing", () => {
    const samples = new Float32Array(100);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 44100, timing);
    assert.strictEqual(result.sampleRate, 44100);
  });

  // -------------------------------------------------------
  // 11. duration getter still works with timing
  // -------------------------------------------------------
  it("duration getter is unaffected by timing", () => {
    // 22050 samples / 22050 Hz = 1.0 second.
    const samples = new Float32Array(22050);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    assert.strictEqual(result.duration, 1.0);
  });

  // -------------------------------------------------------
  // 12. toWav() still works with timing
  // -------------------------------------------------------
  it("toWav() returns a valid ArrayBuffer when timing is provided", () => {
    const samples = new Float32Array(100);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    const wav = result.toWav();
    assert.ok(wav instanceof ArrayBuffer);
    // Sanity check: 44 byte WAV header + 100 samples * 2 bytes (PCM 16-bit, mono).
    assert.strictEqual(wav.byteLength, 44 + 100 * 2);
  });
});

// ---------------------------------------------------------------------------
// Immutability (timing should be frozen)
// ---------------------------------------------------------------------------

describe("AudioResult.timing - immutability", () => {
  function makeSampleTiming() {
    return {
      phonemes: [
        { phoneme: "^", start_ms: 0, end_ms: 58, duration_ms: 58 },
        { phoneme: "k", start_ms: 58, end_ms: 150.8, duration_ms: 92.8 },
      ],
      total_duration_ms: 150.8,
      sample_rate: 22050,
    };
  }

  it("timing object is frozen", () => {
    const samples = new Float32Array([0.1, 0.2]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);

    assert.ok(Object.isFrozen(result.timing));
  });

  it("timing.phonemes array is frozen", () => {
    const samples = new Float32Array([0.1, 0.2]);
    const result = new AudioResult(samples, 22050, makeSampleTiming());

    assert.ok(Object.isFrozen(result.timing.phonemes));
  });

  it("individual phoneme entries are frozen", () => {
    const samples = new Float32Array([0.1, 0.2]);
    const result = new AudioResult(samples, 22050, makeSampleTiming());

    for (const p of result.timing.phonemes) {
      assert.ok(Object.isFrozen(p));
    }
  });

  it("attempting to mutate timing.phonemes[0].start_ms throws in strict mode", () => {
    "use strict";
    const samples = new Float32Array([0.1, 0.2]);
    const result = new AudioResult(samples, 22050, makeSampleTiming());

    assert.throws(() => {
      result.timing.phonemes[0].start_ms = 999;
    }, TypeError);
  });

  it("attempting to push to timing.phonemes throws in strict mode", () => {
    "use strict";
    const samples = new Float32Array([0.1, 0.2]);
    const result = new AudioResult(samples, 22050, makeSampleTiming());

    assert.throws(() => {
      result.timing.phonemes.push({
        phoneme: "x",
        start_ms: 0,
        end_ms: 1,
        duration_ms: 1,
      });
    }, TypeError);
  });

  it("mutating input timing object after construction does NOT affect result", () => {
    "use strict";
    const samples = new Float32Array([0.1, 0.2]);
    const originalTiming = makeSampleTiming();
    const result = new AudioResult(samples, 22050, originalTiming);

    // The constructor deep-froze the passed reference, so mutations on the
    // same object must fail in strict mode. Verify by attempting writes.
    assert.throws(() => {
      originalTiming.phonemes[0].start_ms = 999;
    }, TypeError);
    assert.throws(() => {
      originalTiming.total_duration_ms = -1;
    }, TypeError);
    assert.throws(() => {
      originalTiming.phonemes.push({
        phoneme: "x",
        start_ms: 0,
        end_ms: 1,
        duration_ms: 1,
      });
    }, TypeError);

    // The result still reflects the original (unmutated) snapshot.
    assert.strictEqual(result.timing.phonemes[0].start_ms, 0);
    assert.strictEqual(result.timing.phonemes[0].end_ms, 58);
  });

  // ---------------------------------------------------------
  // Additional immutability coverage (Wave 5: WASM)
  // ---------------------------------------------------------

  it("result.timing IS the same frozen reference as the input (idempotent freeze)", () => {
    const samples = new Float32Array([0.1]);
    const timing = makeSampleTiming();
    // Freeze before passing — constructor must accept and not double-wrap.
    Object.freeze(timing.phonemes[0]);
    Object.freeze(timing.phonemes[1]);
    Object.freeze(timing.phonemes);
    Object.freeze(timing);
    const result = new AudioResult(samples, 22050, timing);

    // Reference identity preserved (no defensive clone, per spec backward_compat).
    assert.strictEqual(result.timing, timing);
    // All levels still frozen post-construction.
    assert.ok(Object.isFrozen(result.timing));
    assert.ok(Object.isFrozen(result.timing.phonemes));
    for (const p of result.timing.phonemes) {
      assert.ok(Object.isFrozen(p));
    }
  });

  it("attempting to set a new property on result.timing throws in strict mode", () => {
    "use strict";
    const samples = new Float32Array([0.1]);
    const result = new AudioResult(samples, 22050, makeSampleTiming());
    // Primitive fields can't be re-assigned, and adding new fields must fail.
    assert.throws(() => {
      result.timing.new_field = 123;
    }, TypeError);
    assert.throws(() => {
      result.timing.total_duration_ms = 999;
    }, TypeError);
    assert.throws(() => {
      result.timing.sample_rate = 8000;
    }, TypeError);
  });

  it("attempting to delete a property on result.timing throws in strict mode", () => {
    "use strict";
    const samples = new Float32Array([0.1]);
    const result = new AudioResult(samples, 22050, makeSampleTiming());
    assert.throws(() => {
      delete result.timing.total_duration_ms;
    }, TypeError);
    assert.throws(() => {
      delete result.timing.phonemes;
    }, TypeError);
  });

  it("attempting to splice/sort/reverse timing.phonemes throws in strict mode", () => {
    "use strict";
    const samples = new Float32Array([0.1]);
    const result = new AudioResult(samples, 22050, makeSampleTiming());
    // splice modifies the array in place — must throw.
    assert.throws(() => result.timing.phonemes.splice(0, 1), TypeError);
    assert.throws(() => result.timing.phonemes.sort(), TypeError);
    assert.throws(() => result.timing.phonemes.reverse(), TypeError);
    assert.throws(() => result.timing.phonemes.shift(), TypeError);
    assert.throws(() => result.timing.phonemes.unshift({}), TypeError);
    assert.throws(() => result.timing.phonemes.pop(), TypeError);
  });

  it("result.timing returns a deeply frozen object even when input was not pre-frozen", () => {
    const samples = new Float32Array([0.1]);
    const livingTiming = makeSampleTiming();
    // Sanity: input is NOT frozen prior to construction.
    assert.ok(!Object.isFrozen(livingTiming));
    assert.ok(!Object.isFrozen(livingTiming.phonemes));
    assert.ok(!Object.isFrozen(livingTiming.phonemes[0]));

    const result = new AudioResult(samples, 22050, livingTiming);

    // Constructor must have applied the deep freeze to the same reference.
    assert.ok(Object.isFrozen(livingTiming));
    assert.ok(Object.isFrozen(livingTiming.phonemes));
    assert.ok(Object.isFrozen(livingTiming.phonemes[0]));
    assert.ok(Object.isFrozen(livingTiming.phonemes[1]));
  });

  it("null timing does not throw and remains null on the getter", () => {
    const samples = new Float32Array([0.1]);
    // Constructor must accept null without invoking deepFreezeTiming.
    const result = new AudioResult(samples, 22050, null);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  it("empty phonemes array is also frozen", () => {
    const samples = new Float32Array([0.1]);
    const empty = { phonemes: [], total_duration_ms: 0, sample_rate: 22050 };
    const result = new AudioResult(samples, 22050, empty);
    assert.ok(Object.isFrozen(result.timing));
    assert.ok(Object.isFrozen(result.timing.phonemes));
    // Cannot push into the empty frozen array.
    assert.throws(() => {
      "use strict";
      result.timing.phonemes.push({
        phoneme: "a",
        start_ms: 0,
        end_ms: 0,
        duration_ms: 0,
      });
    }, TypeError);
  });
});
