/**
 * Integration tests for PiperPlus timing information.
 *
 * テスト対象: src/wasm/openjtalk-web/src/timing.js +
 *             src/wasm/openjtalk-web/src/audio-result.js
 *
 * Run with: node --test test/js/test-piper-plus-timing.js
 *
 * The full PiperPlus.synthesize() pipeline depends on a WASM phonemizer and
 * an ONNX session, both of which are non-trivial to mock in Node.js. This
 * suite therefore validates the same logical contract that synthesize() must
 * deliver — `AudioResult.timing` and `AudioResult.hasTimingInfo` — by driving
 * `durationsToTiming()` and the AudioResult constructor exactly as the real
 * `_infer()` path does. If this integration is correct, synthesize() will
 * propagate timing data correctly to its callers.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { durationsToTiming, DEFAULT_HOP_LENGTH } from '../../src/timing.js';
import { AudioResult } from '../../src/audio-result.js';

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const FRAME_TIME_22050_256_MS = (DEFAULT_HOP_LENGTH / 22050) * 1000;
const FLOAT_EPSILON = 0.01;

/**
 * Assert that two floats are within `FLOAT_EPSILON` of each other.
 * @param {number} actual
 * @param {number} expected
 * @param {string} [message]
 */
function assertCloseTo(actual, expected, message) {
  assert.ok(
    Math.abs(actual - expected) < FLOAT_EPSILON,
    `${message || 'assertCloseTo'}: expected ${expected}, got ${actual} (epsilon=${FLOAT_EPSILON})`,
  );
}

// ---------------------------------------------------------------------------
// 1. Happy path: durations -> timing -> AudioResult
// ---------------------------------------------------------------------------

describe('PiperPlus timing integration', () => {
  it('creates AudioResult with timing from durations', () => {
    // Arrange — durations as the ONNX `durations` output tensor would provide.
    const durations = new Float32Array([5, 8, 12, 10, 7]);
    const sampleRate = 22050;

    // Act — exactly the steps PiperPlus._infer() performs when durations are
    // present in the model output.
    const timing = durationsToTiming(durations, sampleRate);
    const audio = new Float32Array(22050);
    const result = new AudioResult(audio, sampleRate, timing);

    // Assert
    assert.ok(result.hasTimingInfo, 'hasTimingInfo should be true');
    assert.strictEqual(result.timing.sample_rate, 22050);
    assert.strictEqual(result.timing.phonemes.length, 5);
  });

  // -------------------------------------------------------------------------
  // 2. AudioResult without timing
  // -------------------------------------------------------------------------
  it('AudioResult without timing has hasTimingInfo === false', () => {
    // Arrange + Act — mirrors the legacy code path where the model has no
    // `durations` output and AudioResult is constructed without a third arg.
    const audio = new Float32Array(22050);
    const result = new AudioResult(audio, 22050);

    // Assert
    assert.strictEqual(result.hasTimingInfo, false);
    assert.strictEqual(result.timing, null);
  });

  // -------------------------------------------------------------------------
  // 3. Numeric correctness for a single phoneme at 22050 Hz
  // -------------------------------------------------------------------------
  it('timing values match expected ms calculation at 22050Hz', () => {
    // Arrange
    const durations = new Float32Array([10]);

    // Act
    const timing = durationsToTiming(durations, 22050);

    // Assert — 10 frames * (256/22050) * 1000 ≈ 116.09977 ms
    const expected = 10 * FRAME_TIME_22050_256_MS;
    assertCloseTo(
      timing.phonemes[0].duration_ms,
      expected,
      'duration_ms for 10-frame phoneme at 22050Hz',
    );
  });

  // -------------------------------------------------------------------------
  // 4. Empty durations -> empty but valid timing
  // -------------------------------------------------------------------------
  it('empty durations produces empty timing', () => {
    // Arrange
    const durations = new Float32Array([]);

    // Act
    const timing = durationsToTiming(durations, 22050);
    const result = new AudioResult(new Float32Array(100), 22050, timing);

    // Assert
    assert.ok(result.hasTimingInfo, 'hasTimingInfo should still be true for empty timing');
    assert.strictEqual(result.timing.phonemes.length, 0);
    assert.strictEqual(result.timing.total_duration_ms, 0);
  });

  // -------------------------------------------------------------------------
  // 5. Sample rate sensitivity
  // -------------------------------------------------------------------------
  it('different sample rates produce different timings', () => {
    // Arrange
    const durations = new Float32Array([10]);

    // Act
    const timing22050 = durationsToTiming(durations, 22050);
    const timing16000 = durationsToTiming(durations, 16000);

    // Assert — frame_time_ms scales inversely with sample rate, so 22050 Hz
    // and 16000 Hz must yield different per-phoneme durations.
    assert.ok(
      timing22050.phonemes[0].duration_ms !== timing16000.phonemes[0].duration_ms,
      'duration_ms must differ between 22050Hz and 16000Hz',
    );
  });

  // -------------------------------------------------------------------------
  // 6. AudioResult.timing reference identity (additional coverage)
  // -------------------------------------------------------------------------
  it('AudioResult.timing returns the same TimingResult reference passed in', () => {
    // Arrange
    const durations = new Float32Array([5, 8, 12]);
    const timing = durationsToTiming(durations, 22050);

    // Act
    const result = new AudioResult(new Float32Array(1024), 22050, timing);

    // Assert — synthesize() must not clone or mutate the timing object.
    assert.strictEqual(result.timing, timing);
  });

  // -------------------------------------------------------------------------
  // 7. total_duration_ms equals the sum of per-phoneme durations (sanity)
  // -------------------------------------------------------------------------
  it('total_duration_ms equals the sum of per-phoneme duration_ms', () => {
    // Arrange
    const durations = new Float32Array([5, 8, 12, 10, 7]);

    // Act
    const timing = durationsToTiming(durations, 22050);
    const sum = timing.phonemes.reduce((acc, p) => acc + p.duration_ms, 0);

    // Assert
    assertCloseTo(timing.total_duration_ms, sum, 'total_duration_ms vs sum of phonemes');
  });
});


// ---------------------------------------------------------------------------
// E2E: phoneme ID → token reverse lookup integration
// ---------------------------------------------------------------------------

describe('PiperPlus timing - phoneme token integration', () => {
  it('durationsToTiming uses real phoneme tokens when provided', () => {
    const durations = new Float32Array([5, 8, 12]);
    const tokens = ['^', 'k', 'o'];
    const timing = durationsToTiming(durations, 22050, 256, tokens);

    assert.strictEqual(timing.phonemes.length, 3);
    assert.strictEqual(timing.phonemes[0].phoneme, '^');
    assert.strictEqual(timing.phonemes[1].phoneme, 'k');
    assert.strictEqual(timing.phonemes[2].phoneme, 'o');
  });

  it('durationsToTiming falls back to ph_N when tokens are omitted', () => {
    const durations = new Float32Array([5, 8, 12]);
    const timing = durationsToTiming(durations, 22050);

    assert.strictEqual(timing.phonemes[0].phoneme, 'ph_0');
    assert.strictEqual(timing.phonemes[1].phoneme, 'ph_1');
    assert.strictEqual(timing.phonemes[2].phoneme, 'ph_2');
  });

  it('buildPhonemeIdToTokenMap + durationsToTiming produces real phoneme names', async () => {
    const { buildPhonemeIdToTokenMap } = await import('../../src/timing.js');

    // Simulate a model's phoneme_id_map
    const phonemeIdMap = {
      _: [0],
      '^': [1],
      $: [2],
      a: [7],
      k: [10],
      o: [15],
    };
    const idToToken = buildPhonemeIdToTokenMap(phonemeIdMap);

    // Original phoneme IDs for "こんにちは" simulation
    const phonemeIds = [1, 10, 15, 7, 2]; // ^ k o a $
    const durations = new Float32Array([5, 8, 12, 10, 5]);

    // Build tokens from IDs using the reverse map
    const tokens = phonemeIds.map((id, i) => idToToken[id] ?? `ph_${i}`);
    assert.deepStrictEqual(tokens, ['^', 'k', 'o', 'a', '$']);

    const timing = durationsToTiming(durations, 22050, 256, tokens);
    assert.deepStrictEqual(
      timing.phonemes.map((p) => p.phoneme),
      ['^', 'k', 'o', 'a', '$'],
    );
  });
});

// ---------------------------------------------------------------------------
// E2E: models without durations output
// ---------------------------------------------------------------------------

describe('PiperPlus timing - missing durations fallback', () => {
  it('AudioResult with null timing has hasTimingInfo=false', () => {
    const samples = new Float32Array(22050);
    const result = new AudioResult(samples, 22050, null);
    assert.strictEqual(result.hasTimingInfo, false);
    assert.strictEqual(result.timing, null);
  });

  it('AudioResult.duration still works when timing is null', () => {
    const samples = new Float32Array(22050);
    const result = new AudioResult(samples, 22050);
    assert.strictEqual(result.duration, 1.0);
    assert.strictEqual(result.hasTimingInfo, false);
  });
});

// ---------------------------------------------------------------------------
// E2E: multiple synthesize() calls produce independent timing objects
// ---------------------------------------------------------------------------

describe('PiperPlus timing - independent timing objects', () => {
  it('two durations with different lengths produce independent timings', () => {
    const durations1 = new Float32Array([5]);
    const durations2 = new Float32Array([10, 15, 20]);

    const timing1 = durationsToTiming(durations1, 22050);
    const timing2 = durationsToTiming(durations2, 22050);

    assert.notStrictEqual(timing1, timing2);
    assert.strictEqual(timing1.phonemes.length, 1);
    assert.strictEqual(timing2.phonemes.length, 3);
    assert.notStrictEqual(timing1.phonemes, timing2.phonemes);
  });

  it('AudioResult instances with independent timings', () => {
    const timing1 = durationsToTiming(new Float32Array([5]), 22050);
    const timing2 = durationsToTiming(new Float32Array([10]), 22050);

    const result1 = new AudioResult(new Float32Array(100), 22050, timing1);
    const result2 = new AudioResult(new Float32Array(200), 22050, timing2);

    assert.notStrictEqual(result1.timing, result2.timing);
    assert.notStrictEqual(result1.timing.phonemes[0], result2.timing.phonemes[0]);
  });
});
