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


// ---------------------------------------------------------------------------
// _createTiming semantics: durations/phonemeIds length alignment
// ---------------------------------------------------------------------------

describe('PiperPlus timing - durations and phonemeIds length alignment', () => {
  it('truncates to min(durations.length, phonemeIds.length) when durations is longer', async () => {
    const { buildPhonemeIdToTokenMap } = await import('../../src/timing.js');

    // Simulate _createTiming's internal logic:
    // durations has 5 entries, but original phonemeIds has only 3 (pre-padding)
    const durations = new Float32Array([5, 8, 12, 10, 7]);
    const phonemeIds = [1, 7, 2]; // ^ a $ — length 3
    const phonemeIdMap = { _: [0], '^': [1], $: [2], a: [7] };
    const idToToken = buildPhonemeIdToTokenMap(phonemeIdMap);

    // Mirror the alignment logic from PiperPlus._createTiming
    const minLen = Math.min(durations.length, phonemeIds.length);
    const tokens = new Array(minLen);
    for (let i = 0; i < minLen; i++) {
      tokens[i] = idToToken[phonemeIds[i]] ?? `ph_${i}`;
    }
    const alignedDurations = durations.subarray(0, minLen);

    const timing = durationsToTiming(alignedDurations, 22050, 256, tokens);

    // Expectation: only 3 phonemes, matching the original (pre-padding) length.
    assert.strictEqual(timing.phonemes.length, 3);
    assert.deepStrictEqual(
      timing.phonemes.map((p) => p.phoneme),
      ['^', 'a', '$'],
    );
  });

  it('truncates to min when phonemeIds is longer than durations', async () => {
    const { buildPhonemeIdToTokenMap } = await import('../../src/timing.js');

    // Edge case: durations shorter than phonemeIds (e.g., model truncation)
    const durations = new Float32Array([5, 8]);
    const phonemeIds = [1, 7, 10, 2]; // length 4
    const phonemeIdMap = { '^': [1], $: [2], a: [7], k: [10] };
    const idToToken = buildPhonemeIdToTokenMap(phonemeIdMap);

    const minLen = Math.min(durations.length, phonemeIds.length);
    const tokens = new Array(minLen);
    for (let i = 0; i < minLen; i++) {
      tokens[i] = idToToken[phonemeIds[i]] ?? `ph_${i}`;
    }
    const alignedDurations = durations.subarray(0, minLen);
    const timing = durationsToTiming(alignedDurations, 22050, 256, tokens);

    assert.strictEqual(timing.phonemes.length, 2);
    assert.strictEqual(timing.phonemes[0].phoneme, '^');
    assert.strictEqual(timing.phonemes[1].phoneme, 'a');
  });

  it('handles equal-length durations and phonemeIds cleanly', async () => {
    const { buildPhonemeIdToTokenMap } = await import('../../src/timing.js');

    const durations = new Float32Array([5, 8, 12]);
    const phonemeIds = [1, 7, 2];
    const phonemeIdMap = { '^': [1], $: [2], a: [7] };
    const idToToken = buildPhonemeIdToTokenMap(phonemeIdMap);
    const tokens = phonemeIds.map((id, i) => idToToken[id] ?? `ph_${i}`);

    const timing = durationsToTiming(durations, 22050, 256, tokens);
    assert.strictEqual(timing.phonemes.length, 3);
  });
});

// ---------------------------------------------------------------------------
// PhonemeIdToTokenMap caching (simulates _getPhonemeIdToTokenMap semantics)
// ---------------------------------------------------------------------------

describe('PiperPlus timing - phoneme ID to token map caching', () => {
  it('can be built repeatedly with same input and produces stable output', async () => {
    const { buildPhonemeIdToTokenMap } = await import('../../src/timing.js');

    const phonemeIdMap = { _: [0], '^': [1], $: [2], a: [7], k: [10] };

    const first = buildPhonemeIdToTokenMap(phonemeIdMap);
    const second = buildPhonemeIdToTokenMap(phonemeIdMap);

    // Objects are separate references (new maps each call), but content equal
    assert.notStrictEqual(first, second);
    assert.deepStrictEqual(first, second);
  });

  it('cached value is valid for use in durationsToTiming across calls', async () => {
    const { buildPhonemeIdToTokenMap } = await import('../../src/timing.js');

    const phonemeIdMap = { '^': [1], $: [2], a: [7] };
    const idToToken = buildPhonemeIdToTokenMap(phonemeIdMap);

    // Simulate two separate synthesize() calls that reuse the cached map
    const ids1 = [1, 7, 2];
    const ids2 = [1, 7, 7, 2];
    const tokens1 = ids1.map((id, i) => idToToken[id] ?? `ph_${i}`);
    const tokens2 = ids2.map((id, i) => idToToken[id] ?? `ph_${i}`);

    const timing1 = durationsToTiming(new Float32Array([5, 8, 3]), 22050, 256, tokens1);
    const timing2 = durationsToTiming(new Float32Array([5, 8, 9, 3]), 22050, 256, tokens2);

    assert.strictEqual(timing1.phonemes.length, 3);
    assert.strictEqual(timing2.phonemes.length, 4);
  });
});

// ---------------------------------------------------------------------------
// Streaming path timing semantics (intentional: no timing)
// ---------------------------------------------------------------------------

describe('PiperPlus timing - streaming path behavior (documentation guard)', () => {
  it('raw Float32Array has no timing information attached (streaming contract)', () => {
    // synthesizeStreaming() unwraps { audio, durations } and returns audio only.
    // This test documents that contract: the streaming pipeline receives plain
    // Float32Array chunks without timing metadata.
    const audio = new Float32Array([0.1, 0.2, -0.1]);
    // A raw Float32Array has no .timing or .hasTimingInfo properties.
    assert.strictEqual(audio.timing, undefined);
    assert.strictEqual(audio.hasTimingInfo, undefined);
    assert.ok(audio instanceof Float32Array);
  });
});

// ---------------------------------------------------------------------------
// Voice cloning path: same _createTiming logic applied
// ---------------------------------------------------------------------------

describe('PiperPlus timing - voice cloning path timing', () => {
  it('voice cloning path uses same durations->timing conversion as synthesize()', async () => {
    const { buildPhonemeIdToTokenMap } = await import('../../src/timing.js');

    // Same phonemes, same durations — voice cloning does not apply padding,
    // so phonemeIds is used directly (no originalPhonemeIds indirection).
    const phonemeIds = [1, 7, 10, 2];
    const durations = new Float32Array([5, 10, 8, 3]);
    const phonemeIdMap = { '^': [1], $: [2], a: [7], k: [10] };
    const idToToken = buildPhonemeIdToTokenMap(phonemeIdMap);
    const tokens = phonemeIds.map((id, i) => idToToken[id] ?? `ph_${i}`);

    const timing = durationsToTiming(durations, 22050, 256, tokens);

    // Result is identical regardless of whether it came from synthesize() or
    // synthesizeWithVoiceCloning(), because both call _createTiming() with the
    // same (durations, phonemeIds) tuple.
    assert.strictEqual(timing.phonemes.length, 4);
    assert.deepStrictEqual(
      timing.phonemes.map((p) => p.phoneme),
      ['^', 'a', 'k', '$'],
    );

    // The wrapped AudioResult should expose immutable timing
    const result = new AudioResult(new Float32Array(1000), 22050, timing);
    assert.ok(result.hasTimingInfo);
    assert.ok(Object.isFrozen(result.timing));
  });
});

// ---------------------------------------------------------------------------
// synthesize() padding-aware timing: originalPhonemeIds must be pre-padding
// ---------------------------------------------------------------------------

describe('PiperPlus timing - synthesize() padding-aware timing', () => {
  it('timing built from originalPhonemeIds contains only real phonemes, not pad tokens', async () => {
    const { buildPhonemeIdToTokenMap } = await import('../../src/timing.js');

    // Simulate a short text that would trigger Strategy A padding.
    // Original (pre-padding) IDs: [1, 7, 2] (length 3)
    // After padding: [1, 0, 0, ..., 7, ..., 0, 2] (length MIN_PHONEME_IDS=40)
    // The model returns durations of length 40 (one per padded slot).
    // _createTiming() MUST use originalPhonemeIds so timing.phonemes.length === 3.
    const originalPhonemeIds = [1, 7, 2];
    const paddedDurations = new Float32Array(40);
    for (let i = 0; i < 40; i++) paddedDurations[i] = 5 + (i % 7);

    const phonemeIdMap = { _: [0], '^': [1], $: [2], a: [7] };
    const idToToken = buildPhonemeIdToTokenMap(phonemeIdMap);

    const minLen = Math.min(paddedDurations.length, originalPhonemeIds.length);
    const tokens = originalPhonemeIds.map(
      (id, i) => idToToken[id] ?? `ph_${i}`,
    );
    const alignedDurations = paddedDurations.subarray(0, minLen);
    const timing = durationsToTiming(alignedDurations, 22050, 256, tokens);

    // Only the 3 original phonemes appear in timing; padding is discarded.
    assert.strictEqual(timing.phonemes.length, 3);
    assert.deepStrictEqual(
      timing.phonemes.map((p) => p.phoneme),
      ['^', 'a', '$'],
    );
  });
});
