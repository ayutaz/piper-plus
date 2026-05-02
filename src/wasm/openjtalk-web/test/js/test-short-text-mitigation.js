/**
 * Tests for short-text synthesis quality mitigation (Strategy A + B)
 *
 * Run with: node --test test/js/test-short-text-mitigation.js
 *
 * Strategy A: Silence Padding + Post-trim
 *   - padPhonemeIds(): pad short phoneme sequences with pause tokens
 *   - trimSilence(): trim leading/trailing silence from audio
 *
 * Strategy B: Dynamic Scales Adjustment
 *   - adjustScalesForShortInput(): reduce noise scales for short inputs
 *
 * Integration: synthesize() applies A+B transparently.
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Import
// ---------------------------------------------------------------------------

let PiperPlus, AudioResult, padPhonemeIds, trimSilence, adjustScalesForShortInput;
let trimPaddingByDurations;
let MIN_PHONEME_IDS, MIN_BODY_FOR_STRATEGY_A, TRIM_EOS_MAX_FRAMES, DEFAULT_HOP_SIZE;
let importError = null;

try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
  AudioResult = mod.AudioResult;
  padPhonemeIds = mod.padPhonemeIds;
  trimSilence = mod.trimSilence;
  trimPaddingByDurations = mod.trimPaddingByDurations;
  adjustScalesForShortInput = mod.adjustScalesForShortInput;
  MIN_PHONEME_IDS = mod.MIN_PHONEME_IDS;
  MIN_BODY_FOR_STRATEGY_A = mod.MIN_BODY_FOR_STRATEGY_A;
  TRIM_EOS_MAX_FRAMES = mod.TRIM_EOS_MAX_FRAMES;
  DEFAULT_HOP_SIZE = mod.DEFAULT_HOP_SIZE;
} catch (e) {
  importError = e;
}

const skip = PiperPlus == null;

// ---------------------------------------------------------------------------
// Minimal ort mock
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
// Helper: create a wired PiperPlus instance with mock phonemizer and session
// ---------------------------------------------------------------------------

function createMockInstance(overrides = {}) {
  const instance = new PiperPlus();

  instance._config = overrides.config || {
    audio: { sample_rate: 22050 },
    inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
    phoneme_id_map: { _: [0], '^': [1], $: [2], ' ': [3], a: [4] },
  };

  const outputAudio = overrides.outputAudio || new Float32Array(22050);

  instance._phonemizer = {
    detectLanguage: overrides.detectLanguage || (() => 'ja'),
    encode: overrides.encode || ((text, language) => ({
      phonemeIds: overrides.phonemeIds || [1, 4, 4, 4, 2],
      prosodyFeatures: overrides.prosodyFeatures || null,
    })),
    dispose: () => {},
    supportedLanguages: ['ja', 'en'],
  };

  instance._session = {
    run: overrides.sessionRun || (async (feeds) => ({
      output: { data: outputAudio, dims: [1, outputAudio.length] },
    })),
    release: () => {},
  };

  instance._ort = globalThis.ort;
  instance._initialized = true;

  return instance;
}


// ===========================================================================
// padPhonemeIds
// ===========================================================================

// Helper: build [BOS, body..., EOS] of a target total length, with body
// large enough for Strategy A to apply (body >= MIN_BODY_FOR_STRATEGY_A).
function makeIds(total) {
  const out = [1];
  for (let i = 0; i < total - 2; i++) {
    out.push(4);
  }
  out.push(2);
  return out;
}

describe('padPhonemeIds (Strategy A - padding)', { skip }, () => {
  it('does not pad when phonemeIds length >= MIN_PHONEME_IDS', () => {
    const ids = makeIds(MIN_PHONEME_IDS);
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, false);
    assert.deepEqual(result.phonemeIds, ids);
    assert.equal(result.prosodyFeatures, null);
  });

  it('does not pad when phonemeIds length > MIN_PHONEME_IDS', () => {
    const ids = makeIds(MIN_PHONEME_IDS + 10);
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, false);
    assert.equal(result.phonemeIds.length, MIN_PHONEME_IDS + 10);
  });

  it('pads short sequences to MIN_PHONEME_IDS', () => {
    // body must be >= MIN_BODY_FOR_STRATEGY_A.
    const ids = makeIds(2 + MIN_BODY_FOR_STRATEGY_A);
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, true);
    assert.equal(result.phonemeIds.length, MIN_PHONEME_IDS);
  });

  it('preserves BOS as first element after padding', () => {
    const ids = makeIds(2 + MIN_BODY_FOR_STRATEGY_A);
    const result = padPhonemeIds(ids, null);

    assert.equal(result.phonemeIds[0], 1, 'first element should be BOS');
  });

  it('preserves EOS as last element after padding', () => {
    const ids = makeIds(2 + MIN_BODY_FOR_STRATEGY_A);
    const result = padPhonemeIds(ids, null);

    assert.equal(result.phonemeIds[result.phonemeIds.length - 1], 2,
      'last element should be EOS');
  });

  it('inserts pause tokens (ID=0) for padding', () => {
    // body=3, so deficit = MIN_PHONEME_IDS - 5.
    const ids = makeIds(2 + MIN_BODY_FOR_STRATEGY_A);
    const expectedPads = MIN_PHONEME_IDS - ids.length;
    const result = padPhonemeIds(ids, null);

    const zeros = result.phonemeIds.filter(id => id === 0).length;
    assert.equal(zeros, expectedPads, `should have ${expectedPads} pause tokens inserted`);
  });

  it('distributes padding evenly: front gets floor, back gets remainder', () => {
    const ids = [1, 10, 11, 12, 2]; // body=3
    const total = MIN_PHONEME_IDS - ids.length;
    const front = Math.floor(total / 2);
    const back = total - front;
    const result = padPhonemeIds(ids, null);

    // After BOS, `front` zeros, then body, then `back` zeros, then EOS.
    for (let i = 1; i <= front; i++) {
      assert.equal(result.phonemeIds[i], 0, `index ${i} should be pad`);
    }
    assert.equal(result.phonemeIds[1 + front], 10);
    assert.equal(result.phonemeIds[1 + front + 1], 11);
    assert.equal(result.phonemeIds[1 + front + 2], 12);
    for (let i = 1 + front + 3; i < MIN_PHONEME_IDS - 1; i++) {
      assert.equal(result.phonemeIds[i], 0, `index ${i} should be pad`);
    }
    assert.equal(result.phonemeIds[MIN_PHONEME_IDS - 1], 2);
    assert.equal(result.phonemeIds.length, MIN_PHONEME_IDS);
    // Distribution split is balanced.
    assert.ok(Math.abs(front - back) <= 1);
  });

  it('pads prosodyFeatures in parallel when present', () => {
    // body must be >= MIN_BODY_FOR_STRATEGY_A.
    const bodySize = MIN_BODY_FOR_STRATEGY_A;
    const ids = [1, ...new Array(bodySize).fill(4), 2];
    const prosody = [[0, 0, 0], ...new Array(bodySize).fill(null).map((_, i) => [i, i + 1, i + 2]), [0, 0, 0]];
    const result = padPhonemeIds(ids, prosody);

    assert.equal(result.wasPadded, true);
    assert.equal(result.prosodyFeatures.length, MIN_PHONEME_IDS);
    // BOS prosody preserved
    assert.deepEqual(result.prosodyFeatures[0], [0, 0, 0]);
    // Padding prosody should be zero triplets
    assert.deepEqual(result.prosodyFeatures[1], [0, 0, 0]);
    // EOS prosody preserved
    assert.deepEqual(result.prosodyFeatures[MIN_PHONEME_IDS - 1], [0, 0, 0]);
  });

  it('returns null prosodyFeatures when input prosody is null', () => {
    // body must be >= MIN_BODY_FOR_STRATEGY_A.
    const ids = [1, ...new Array(MIN_BODY_FOR_STRATEGY_A).fill(4), 2];
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, true);
    assert.equal(result.prosodyFeatures, null);
  });

  it('skips Strategy A when body is too short', () => {
    // body=0 (BOS+EOS only)
    {
      const ids = [1, 2];
      const result = padPhonemeIds(ids, null);
      assert.equal(result.wasPadded, false);
      assert.deepEqual(result.phonemeIds, ids);
    }
    // body=1
    {
      const ids = [1, 4, 2];
      const result = padPhonemeIds(ids, null);
      assert.equal(result.wasPadded, false);
      assert.deepEqual(result.phonemeIds, ids);
    }
    // body=2 (e.g. "あ。" case)
    if (MIN_BODY_FOR_STRATEGY_A > 2) {
      const ids = [1, 4, 5, 2];
      const result = padPhonemeIds(ids, null);
      assert.equal(result.wasPadded, false);
      assert.deepEqual(result.phonemeIds, ids);
    }
  });

  it('handles input of length exactly MIN_PHONEME_IDS - 1', () => {
    const ids = makeIds(MIN_PHONEME_IDS - 1);
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, true);
    assert.equal(result.phonemeIds.length, MIN_PHONEME_IDS);
  });

  it('padding prosody arrays are independent references (not shared)', () => {
    const bodySize = MIN_BODY_FOR_STRATEGY_A;
    const ids = [1, ...new Array(bodySize).fill(4), 2];
    const prosody = [[0, 0, 0], ...new Array(bodySize).fill(null).map((_, i) => [i, i + 1, i + 2]), [0, 0, 0]];
    const result = padPhonemeIds(ids, prosody);
    assert.equal(result.wasPadded, true);

    // Total deficit = MIN_PHONEME_IDS - ids.length, split front/back.
    const total = MIN_PHONEME_IDS - ids.length;
    const front = Math.floor(total / 2);
    const back = total - front;

    // Front padding: indices [1, 1+front), back padding: indices
    // [1+front+bodySize, 1+front+bodySize+back).
    const frontPad = result.prosodyFeatures.slice(1, 1 + front);
    const backPad = result.prosodyFeatures.slice(1 + front + bodySize, 1 + front + bodySize + back);
    const allPad = [...frontPad, ...backPad];

    // Every padding entry must be a distinct array reference
    for (let i = 0; i < allPad.length; i++) {
      for (let j = i + 1; j < allPad.length; j++) {
        assert.notStrictEqual(allPad[i], allPad[j],
          `padding prosody[${i}] and [${j}] must not share the same reference`);
      }
    }

    // Mutating one padding entry must not affect others
    allPad[0][0] = 999;
    for (let i = 1; i < allPad.length; i++) {
      assert.equal(allPad[i][0], 0,
        `mutating padding[0] should not affect padding[${i}]`);
    }
  });

  it('exposes frontPad and backPad on the result (issue #356)', () => {
    // body must be >= MIN_BODY_FOR_STRATEGY_A so Strategy A applies.
    const ids = [1, ...new Array(MIN_BODY_FOR_STRATEGY_A).fill(4), 2];
    const result = padPhonemeIds(ids, null);
    assert.equal(result.wasPadded, true);
    assert.equal(typeof result.frontPad, 'number');
    assert.equal(typeof result.backPad, 'number');
    const total = MIN_PHONEME_IDS - ids.length;
    assert.equal(result.frontPad + result.backPad, total);
  });

  it('reports frontPad=0 / backPad=0 when no padding was applied', () => {
    // body < MIN_BODY_FOR_STRATEGY_A → skipped.
    const skipResult = padPhonemeIds([1, 2], null);
    assert.equal(skipResult.wasPadded, false);
    assert.equal(skipResult.frontPad, 0);
    assert.equal(skipResult.backPad, 0);

    // length >= MIN_PHONEME_IDS → no padding needed.
    const longIds = makeIds(MIN_PHONEME_IDS);
    const longResult = padPhonemeIds(longIds, null);
    assert.equal(longResult.wasPadded, false);
    assert.equal(longResult.frontPad, 0);
    assert.equal(longResult.backPad, 0);
  });
});


// ===========================================================================
// trimPaddingByDurations (precise post-trim, issue #356)
// ===========================================================================
// Mirrors src/python_run/tests/test_short_text_mitigation.py.

describe('trimPaddingByDurations (Strategy A - precise post-trim)', { skip }, () => {
  it('is a no-op when no padding was applied', () => {
    const audio = Float32Array.from({ length: 1000 }, (_, i) => i / 1000);
    const durations = new Float32Array([1, 1, 1, 1, 1]);
    const result = trimPaddingByDurations(audio, durations, 0, 0, 256);
    assert.equal(result.length, audio.length);
  });

  it('trims front padding only', () => {
    // Layout: BOS=2, pad×3 (3+3+3), body=4, EOS=1 → 19 frames total
    const durations = new Float32Array([2, 3, 3, 3, 4, 1]);
    const hop = 100;
    const total = 1900;
    const audio = new Float32Array(total);
    const result = trimPaddingByDurations(audio, durations, 3, 0, hop, 6);
    // BOS + front padding = (2+3+3+3)*100 = 1100
    assert.equal(result.length, total - 1100);
  });

  it('strips the entire EOS region by default', () => {
    const durations = new Float32Array([2, 5, 5, 4, 4, 5, 5, 8]);
    const hop = 100;
    const total = 3800;
    const audio = new Float32Array(total);
    const result = trimPaddingByDurations(audio, durations, 2, 2, hop);
    // BOS + front padding = (2+5+5)*100 = 1200
    // back padding + entire EOS = (5+5+8)*100 = 1800
    assert.equal(result.length, total - 1200 - 1800);
  });

  it('clamps an inflated EOS to eosMaxFrames', () => {
    const durations = new Float32Array([2, 3, 3, 4, 3, 3, 10]);
    const hop = 100;
    const total = 2800;
    const audio = new Float32Array(total);
    const result = trimPaddingByDurations(audio, durations, 2, 2, hop, 6);
    // BOS + front padding = (2+3+3)*100 = 800
    // back padding + EOS excess = (3+3 + (10-6))*100 = 1000
    assert.equal(result.length, total - 800 - 1000);
  });

  it('returns the input unchanged when durations is null', () => {
    const audio = new Float32Array(1000);
    const result = trimPaddingByDurations(audio, null, 3, 3, 256);
    assert.equal(result.length, audio.length);
  });

  it('returns the input unchanged when durations is too short', () => {
    const audio = new Float32Array(1000);
    const durations = new Float32Array([1, 1, 1]);
    const result = trimPaddingByDurations(audio, durations, 5, 5, 256);
    assert.equal(result.length, audio.length);
  });

  it('returns the input unchanged when hopSize is zero', () => {
    const audio = new Float32Array(1000);
    const durations = new Float32Array(8).fill(1);
    const result = trimPaddingByDurations(audio, durations, 2, 2, 0);
    assert.equal(result.length, audio.length);
  });

  it('uses Math.trunc (matches int() / `as i64` in other runtimes)', () => {
    // Layout (frontPad=1, backPad=1, body=3):
    //   [BOS=0.701, pad=0.701, body=2, body=2, body=2, pad=0.703, EOS=0.701]
    // Front trim = trunc((0.701+0.701)*100) = 140
    // Back trim  = trunc(0.703*100) + trunc(0.701*100) = 70+70 = 140
    // Math.round() would diverge → cross-runtime drift.
    const durations = new Float32Array([0.701, 0.701, 2, 2, 2, 0.703, 0.701]);
    const hop = 100;
    let sum = 0;
    for (const d of durations) sum += d;
    const total = Math.trunc(sum * hop);
    const audio = new Float32Array(total);
    const result = trimPaddingByDurations(audio, durations, 1, 1, hop);
    assert.equal(result.length, total - 140 - 140);
  });

  it('exposes TRIM_EOS_MAX_FRAMES = 0 and DEFAULT_HOP_SIZE = 256', () => {
    assert.equal(TRIM_EOS_MAX_FRAMES, 0);
    assert.equal(DEFAULT_HOP_SIZE, 256);
  });
});


// ===========================================================================
// trimSilence
// ===========================================================================

describe('trimSilence (Strategy A - post-trim)', { skip }, () => {
  it('returns input unchanged if length <= TRIM_MIN_SAMPLES', () => {
    const audio = new Float32Array(2205);
    const result = trimSilence(audio);

    assert.equal(result.length, 2205);
  });

  it('returns input unchanged if length is smaller than TRIM_MIN_SAMPLES', () => {
    const audio = new Float32Array(100);
    audio[50] = 0.5;
    const result = trimSilence(audio);

    assert.equal(result.length, 100);
  });

  it('trims leading silence', () => {
    // 10000 samples: first 5000 silent, last 5000 with signal
    const audio = new Float32Array(10000);
    for (let i = 5000; i < 10000; i++) {
      audio[i] = 0.5;
    }
    const result = trimSilence(audio);

    // First non-silent window starts at index 5000 (window 19 with window=256)
    // so trimmed audio should start around sample 4864 (19 * 256)
    assert.ok(result.length < 10000, 'should be shorter than original');
    assert.ok(result.length >= 2205, 'should keep at least TRIM_MIN_SAMPLES');
  });

  it('trims trailing silence', () => {
    // 10000 samples: first 3000 with signal, rest silent
    const audio = new Float32Array(10000);
    for (let i = 0; i < 3000; i++) {
      audio[i] = 0.3;
    }
    const result = trimSilence(audio);

    assert.ok(result.length < 10000, 'should be shorter than original');
    assert.ok(result.length >= 2205, 'should keep at least TRIM_MIN_SAMPLES');
  });

  it('trims both leading and trailing silence', () => {
    // 20000 samples: silence(5000) + signal(5000) + silence(10000)
    const audio = new Float32Array(20000);
    for (let i = 5000; i < 10000; i++) {
      audio[i] = 0.4;
    }
    const result = trimSilence(audio);

    assert.ok(result.length < 20000, 'should be shorter than original');
    assert.ok(result.length >= 2205, 'should keep at least TRIM_MIN_SAMPLES');
    // The signal should still be present in the result
    const maxVal = Math.max(...result);
    assert.ok(maxVal > 0.3, 'trimmed audio should contain the signal');
  });

  it('keeps at least TRIM_MIN_SAMPLES when signal is very short', () => {
    // 5000 samples: mostly silence with a tiny signal burst
    const audio = new Float32Array(5000);
    // Put a very short signal in the middle (just a few samples)
    for (let i = 2500; i < 2510; i++) {
      audio[i] = 0.5;
    }
    const result = trimSilence(audio);

    assert.ok(result.length >= 2205, 'should keep at least TRIM_MIN_SAMPLES');
  });

  it('returns minimum slice when audio is entirely silent', () => {
    const audio = new Float32Array(5000); // all zeros
    const result = trimSilence(audio);

    assert.equal(result.length, 2205);
  });

  it('returns full audio when no silence to trim', () => {
    // Audio is entirely non-silent
    const audio = new Float32Array(5000);
    for (let i = 0; i < 5000; i++) {
      audio[i] = 0.3;
    }
    const result = trimSilence(audio);

    // Should retain all windows (some trailing samples may be lost due
    // to window truncation, but should be close to the original length)
    // nWindows = floor(5000/256) = 19, last window covers up to 19*256 = 4864
    assert.ok(result.length >= 4864, 'should keep most of the audio');
  });

  it('handles audio shorter than one window', () => {
    const audio = new Float32Array(3000);
    for (let i = 0; i < 3000; i++) {
      audio[i] = 0.2;
    }
    // nWindows = floor(3000/256) = 11, should still work
    const result = trimSilence(audio);
    assert.ok(result.length >= 2205);
  });
});


// ===========================================================================
// adjustScalesForShortInput
// ===========================================================================

describe('adjustScalesForShortInput (Strategy B)', { skip }, () => {
  it('does not adjust when phonemeCount >= MIN_PHONEME_IDS', () => {
    const result = adjustScalesForShortInput(MIN_PHONEME_IDS, 0.667, 0.8);

    assert.equal(result.noiseScale, 0.667);
    assert.equal(result.noiseW, 0.8);
  });

  it('does not adjust when phonemeCount > MIN_PHONEME_IDS', () => {
    const result = adjustScalesForShortInput(MIN_PHONEME_IDS + 50, 0.667, 0.8);

    assert.equal(result.noiseScale, 0.667);
    assert.equal(result.noiseW, 0.8);
  });

  it('reduces noiseScale for short input', () => {
    // Half of MIN_PHONEME_IDS — both ratios clamp to their floors at this point.
    const len = Math.floor(MIN_PHONEME_IDS / 2);
    const result = adjustScalesForShortInput(len, 0.667, 0.8);
    const ratio = len / MIN_PHONEME_IDS;
    const expected = 0.667 * Math.max(0.5, ratio);

    assert.ok(result.noiseScale < 0.667, 'noiseScale should be reduced');
    assert.ok(Math.abs(result.noiseScale - expected) < 1e-6,
      `noiseScale should be ${expected}, got ${result.noiseScale}`);
  });

  it('reduces noiseW for short input', () => {
    const len = Math.floor(MIN_PHONEME_IDS / 2);
    const result = adjustScalesForShortInput(len, 0.667, 0.8);
    const ratio = len / MIN_PHONEME_IDS;
    const expected = 0.8 * Math.max(0.4, ratio);

    assert.ok(result.noiseW < 0.8, 'noiseW should be reduced');
    assert.ok(Math.abs(result.noiseW - expected) < 1e-6,
      `noiseW should be ${expected}, got ${result.noiseW}`);
  });

  it('clamps noiseScale multiplier at 0.5 for very short input', () => {
    // 1 phoneme — far below the noiseScale floor (0.5).
    const result = adjustScalesForShortInput(1, 0.667, 0.8);

    const expected = 0.667 * 0.5;
    assert.ok(Math.abs(result.noiseScale - expected) < 1e-6,
      `noiseScale should clamp at 0.5 * 0.667 = ${expected}, got ${result.noiseScale}`);
  });

  it('clamps noiseW multiplier at 0.4 for very short input', () => {
    // 1 phoneme — far below the noiseW floor (0.4).
    const result = adjustScalesForShortInput(1, 0.667, 0.8);

    const expected = 0.8 * 0.4;
    assert.ok(Math.abs(result.noiseW - expected) < 1e-6,
      `noiseW should clamp at 0.4 * 0.8 = ${expected}, got ${result.noiseW}`);
  });

  it('handles zero phonemes gracefully', () => {
    // 0 phonemes -> ratio = 0, max(0.5, 0) = 0.5, max(0.4, 0) = 0.4
    const result = adjustScalesForShortInput(0, 0.667, 0.8);

    assert.ok(Math.abs(result.noiseScale - 0.667 * 0.5) < 1e-6);
    assert.ok(Math.abs(result.noiseW - 0.8 * 0.4) < 1e-6);
  });

  it('applies linear scaling in the mid-range', () => {
    // Pick a length between both floors and the threshold so the ratio is used directly.
    const len = MIN_PHONEME_IDS - 1;
    const result = adjustScalesForShortInput(len, 1.0, 1.0);
    const ratio = len / MIN_PHONEME_IDS;
    const expectedNs = Math.max(0.5, ratio);
    const expectedNw = Math.max(0.4, ratio);

    assert.ok(Math.abs(result.noiseScale - expectedNs) < 1e-6,
      `expected ${expectedNs}, got ${result.noiseScale}`);
    assert.ok(Math.abs(result.noiseW - expectedNw) < 1e-6,
      `expected ${expectedNw}, got ${result.noiseW}`);
  });

  it('handles ratio exactly at the clamp boundary for noiseW', () => {
    // Choose len so ratio == 0.4 (or as close as integer math allows).
    const len = Math.max(1, Math.round(0.4 * MIN_PHONEME_IDS));
    const result = adjustScalesForShortInput(len, 1.0, 1.0);

    const ratio = len / MIN_PHONEME_IDS;
    assert.ok(Math.abs(result.noiseScale - Math.max(0.5, ratio)) < 1e-6);
    assert.ok(Math.abs(result.noiseW - Math.max(0.4, ratio)) < 1e-6);
  });
});


// ===========================================================================
// Integration: synthesize() applies Strategy A+B
// ===========================================================================

describe('synthesize() short-text mitigation integration', { skip }, () => {
  it('applies padding and scale adjustment for short phonemeIds', async () => {
    let capturedFeeds = null;
    // body must be >= MIN_BODY_FOR_STRATEGY_A but length < MIN_PHONEME_IDS.
    const phonemeIds = [1, ...new Array(MIN_BODY_FOR_STRATEGY_A).fill(4), 2];
    const instance = createMockInstance({
      phonemeIds,
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(5000), dims: [1, 5000] } };
      },
    });

    await instance.synthesize('hi');

    // Strategy A: padded to MIN_PHONEME_IDS
    const inputIds = Array.from(capturedFeeds.input.data).map(Number);
    assert.equal(inputIds.length, MIN_PHONEME_IDS, `padded phonemeIds should be ${MIN_PHONEME_IDS}`);
    assert.equal(inputIds[0], 1, 'BOS preserved');
    assert.equal(inputIds[MIN_PHONEME_IDS - 1], 2, 'EOS preserved');

    // Strategy B: noiseScale and noiseW should be adjusted (ratio < 1).
    const scales = Array.from(capturedFeeds.scales.data);
    assert.ok(scales[0] < 0.667, `noiseScale should be reduced: ${scales[0]}`);
    // lengthScale should be unchanged
    assert.ok(Math.abs(scales[1] - 1.0) < 1e-6, 'lengthScale unchanged');
    assert.ok(scales[2] < 0.8, `noiseW should be reduced: ${scales[2]}`);
  });

  it('does NOT pad or adjust scales for long phonemeIds', async () => {
    let capturedFeeds = null;
    const longLen = MIN_PHONEME_IDS + 10;
    const longIds = new Array(longLen).fill(4);
    longIds[0] = 1;
    longIds[longLen - 1] = 2;

    const instance = createMockInstance({
      encode: () => ({ phonemeIds: longIds, prosodyFeatures: null }),
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(22050), dims: [1, 22050] } };
      },
    });

    await instance.synthesize('a long enough sentence with many phonemes');

    const inputIds = Array.from(capturedFeeds.input.data).map(Number);
    assert.equal(inputIds.length, longLen, 'should NOT be padded');

    const scales = Array.from(capturedFeeds.scales.data);
    assert.ok(Math.abs(scales[0] - 0.667) < 1e-6, 'noiseScale unchanged');
    assert.ok(Math.abs(scales[2] - 0.8) < 1e-6, 'noiseW unchanged');
  });

  it('applies post-trim when padding was applied', async () => {
    // Create audio with silence at start and end, signal in middle
    const audio = new Float32Array(10000);
    // Insert signal in middle portion
    for (let i = 3000; i < 7000; i++) {
      audio[i] = 0.5;
    }

    const instance = createMockInstance({
      // body must be >= MIN_BODY_FOR_STRATEGY_A so Strategy A applies.
      phonemeIds: [1, ...new Array(MIN_BODY_FOR_STRATEGY_A).fill(4), 2],
      sessionRun: async () => ({
        output: { data: audio, dims: [1, audio.length] },
      }),
    });

    const result = await instance.synthesize('hi');

    // Audio should be trimmed (shorter than original 10000)
    assert.ok(result.samples.length < 10000,
      `should be trimmed: got ${result.samples.length}`);
    assert.ok(result.samples.length >= 2205,
      'should keep at least TRIM_MIN_SAMPLES');
  });

  it('does NOT trim when no padding was applied', async () => {
    const audio = new Float32Array(10000);
    // Silence at edges, signal in middle
    for (let i = 3000; i < 7000; i++) {
      audio[i] = 0.5;
    }

    const longLen = MIN_PHONEME_IDS + 5;
    const longIds = new Array(longLen).fill(4);
    longIds[0] = 1;
    longIds[longLen - 1] = 2;

    const instance = createMockInstance({
      encode: () => ({ phonemeIds: longIds, prosodyFeatures: null }),
      sessionRun: async () => ({
        output: { data: audio, dims: [1, audio.length] },
      }),
    });

    const result = await instance.synthesize('this is long enough text');

    // No padding -> no trim -> full audio preserved
    assert.equal(result.samples.length, 10000,
      'should NOT trim when not padded');
  });

  it('returns AudioResult with correct sample rate', async () => {
    const instance = createMockInstance({
      config: {
        audio: { sample_rate: 44100 },
        inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
        phoneme_id_map: { _: [0] },
      },
      // body must be >= MIN_BODY_FOR_STRATEGY_A so the path exercises padding too.
      phonemeIds: [1, ...new Array(MIN_BODY_FOR_STRATEGY_A).fill(4), 2],
    });

    const result = await instance.synthesize('hi');

    assert.ok(result instanceof AudioResult);
    assert.equal(result.sampleRate, 44100);
  });

  it('passes prosody features through padding correctly', async () => {
    let capturedFeeds = null;
    const bodySize = MIN_BODY_FOR_STRATEGY_A;
    const prosody = [
      [0, 0, 0], // BOS
      ...new Array(bodySize).fill(null).map((_, i) => [i + 1, i + 2, i + 3]),
      [0, 0, 0], // EOS
    ];

    const instance = createMockInstance({
      config: {
        audio: { sample_rate: 22050 },
        inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
        phoneme_id_map: { _: [0] },
        prosody_id_map: { a1: 0, a2: 1, a3: 2 },
      },
      encode: () => ({
        phonemeIds: [1, ...new Array(bodySize).fill(4), 2],
        prosodyFeatures: prosody,
      }),
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(5000), dims: [1, 5000] } };
      },
    });

    await instance.synthesize('hi');

    // prosody_features tensor should exist and match padded length
    assert.ok(capturedFeeds.prosody_features, 'prosody_features tensor should exist');
    // Padded to MIN_PHONEME_IDS phonemes, each with 3 features
    assert.deepEqual(capturedFeeds.prosody_features.dims, [1, MIN_PHONEME_IDS, 3]);
  });

  it('Strategy B uses original phoneme count (before padding) for ratio', async () => {
    let capturedFeeds = null;
    // Pick a length so ratio is below the noise_scale floor (0.5).
    const len = Math.max(2 + MIN_BODY_FOR_STRATEGY_A,
                         Math.floor(MIN_PHONEME_IDS / 2) + 1);
    const ids = [1, ...new Array(len - 2).fill(4), 2];

    const instance = createMockInstance({
      phonemeIds: ids,
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(5000), dims: [1, 5000] } };
      },
    });

    await instance.synthesize('test');

    const scales = Array.from(capturedFeeds.scales.data);
    const ratio = ids.length / MIN_PHONEME_IDS;
    const expectedNoise = 0.667 * Math.max(0.5, ratio);
    const expectedNoiseW = 0.8 * Math.max(0.4, ratio);
    assert.ok(Math.abs(scales[0] - expectedNoise) < 1e-4,
      `noiseScale: expected ~${expectedNoise}, got ${scales[0]}`);
    assert.ok(Math.abs(scales[2] - expectedNoiseW) < 1e-4,
      `noiseW: expected ~${expectedNoiseW}, got ${scales[2]}`);
  });
});


// ===========================================================================
// Import error report
// ===========================================================================

if (importError) {
  describe('import error', () => {
    it('should not have an import error', () => {
      assert.fail(`Failed to import src/index.js: ${importError.message}`);
    });
  });
}
