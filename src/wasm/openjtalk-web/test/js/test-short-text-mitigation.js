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
let importError = null;

try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
  AudioResult = mod.AudioResult;
  padPhonemeIds = mod.padPhonemeIds;
  trimSilence = mod.trimSilence;
  adjustScalesForShortInput = mod.adjustScalesForShortInput;
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

describe('padPhonemeIds (Strategy A - padding)', { skip }, () => {
  it('does not pad when phonemeIds length >= MIN_PHONEME_IDS', () => {
    const ids = new Array(40).fill(4);
    ids[0] = 1; // BOS
    ids[39] = 2; // EOS
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, false);
    assert.deepEqual(result.phonemeIds, ids);
    assert.equal(result.prosodyFeatures, null);
  });

  it('does not pad when phonemeIds length > MIN_PHONEME_IDS', () => {
    const ids = new Array(50).fill(4);
    ids[0] = 1;
    ids[49] = 2;
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, false);
    assert.equal(result.phonemeIds.length, 50);
  });

  it('pads short sequences to MIN_PHONEME_IDS (40)', () => {
    // [BOS, a, a, a, EOS] = 5 elements, needs 35 padding
    const ids = [1, 4, 4, 4, 2];
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, true);
    assert.equal(result.phonemeIds.length, 40);
  });

  it('preserves BOS as first element after padding', () => {
    const ids = [1, 4, 4, 2];
    const result = padPhonemeIds(ids, null);

    assert.equal(result.phonemeIds[0], 1, 'first element should be BOS');
  });

  it('preserves EOS as last element after padding', () => {
    const ids = [1, 4, 4, 2];
    const result = padPhonemeIds(ids, null);

    assert.equal(result.phonemeIds[result.phonemeIds.length - 1], 2,
      'last element should be EOS');
  });

  it('inserts pause tokens (ID=0) for padding', () => {
    const ids = [1, 4, 2]; // 3 elements, needs 37 padding
    const result = padPhonemeIds(ids, null);

    // Count zeros (excluding any that were already there)
    const zeros = result.phonemeIds.filter(id => id === 0).length;
    assert.equal(zeros, 37, 'should have 37 pause tokens inserted');
  });

  it('distributes padding evenly: front gets floor, back gets remainder', () => {
    // 5 elements -> need 35 padding -> front=17, back=18
    const ids = [1, 10, 11, 12, 2];
    const result = padPhonemeIds(ids, null);

    // After BOS (index 0), next 17 should be padding zeros
    for (let i = 1; i <= 17; i++) {
      assert.equal(result.phonemeIds[i], 0, `index ${i} should be pad`);
    }
    // Then body: 10, 11, 12
    assert.equal(result.phonemeIds[18], 10);
    assert.equal(result.phonemeIds[19], 11);
    assert.equal(result.phonemeIds[20], 12);
    // Then 18 padding zeros
    for (let i = 21; i <= 38; i++) {
      assert.equal(result.phonemeIds[i], 0, `index ${i} should be pad`);
    }
    // Then EOS
    assert.equal(result.phonemeIds[39], 2);
  });

  it('pads prosodyFeatures in parallel when present', () => {
    const ids = [1, 4, 4, 2]; // 4 elements -> 36 padding (18 front, 18 back)
    const prosody = [[0, 0, 0], [1, 2, 3], [4, 5, 6], [0, 0, 0]];
    const result = padPhonemeIds(ids, prosody);

    assert.equal(result.wasPadded, true);
    assert.equal(result.prosodyFeatures.length, 40);
    // BOS prosody preserved
    assert.deepEqual(result.prosodyFeatures[0], [0, 0, 0]);
    // Padding prosody should be zero triplets
    assert.deepEqual(result.prosodyFeatures[1], [0, 0, 0]);
    // EOS prosody preserved
    assert.deepEqual(result.prosodyFeatures[39], [0, 0, 0]);
  });

  it('returns null prosodyFeatures when input prosody is null', () => {
    const ids = [1, 4, 2];
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, true);
    assert.equal(result.prosodyFeatures, null);
  });

  it('handles minimum input (2 elements: BOS + EOS)', () => {
    const ids = [1, 2];
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, true);
    assert.equal(result.phonemeIds.length, 40);
    assert.equal(result.phonemeIds[0], 1);
    assert.equal(result.phonemeIds[39], 2);
  });

  it('handles input of length exactly MIN_PHONEME_IDS - 1', () => {
    const ids = new Array(39).fill(4);
    ids[0] = 1;
    ids[38] = 2;
    const result = padPhonemeIds(ids, null);

    assert.equal(result.wasPadded, true);
    assert.equal(result.phonemeIds.length, 40);
  });

  it('padding prosody arrays are independent references (not shared)', () => {
    const ids = [1, 4, 4, 2]; // 4 elements -> 36 padding (18 front, 18 back)
    const prosody = [[0, 0, 0], [1, 2, 3], [4, 5, 6], [0, 0, 0]];
    const result = padPhonemeIds(ids, prosody);

    // Collect all padding prosody entries (front padding: indices 1..18, back: 21..38)
    const frontPad = result.prosodyFeatures.slice(1, 19);
    const backPad = result.prosodyFeatures.slice(21, 39);
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
    const result = adjustScalesForShortInput(40, 0.667, 0.8);

    assert.equal(result.noiseScale, 0.667);
    assert.equal(result.noiseW, 0.8);
  });

  it('does not adjust when phonemeCount > MIN_PHONEME_IDS', () => {
    const result = adjustScalesForShortInput(100, 0.667, 0.8);

    assert.equal(result.noiseScale, 0.667);
    assert.equal(result.noiseW, 0.8);
  });

  it('reduces noiseScale for short input', () => {
    // 20 phonemes -> ratio = 20/40 = 0.5, max(0.5, 0.5) = 0.5
    const result = adjustScalesForShortInput(20, 0.667, 0.8);

    assert.ok(result.noiseScale < 0.667, 'noiseScale should be reduced');
    const expected = 0.667 * 0.5;
    assert.ok(Math.abs(result.noiseScale - expected) < 1e-6,
      `noiseScale should be ${expected}, got ${result.noiseScale}`);
  });

  it('reduces noiseW for short input', () => {
    // 20 phonemes -> ratio = 0.5, max(0.4, 0.5) = 0.5
    const result = adjustScalesForShortInput(20, 0.667, 0.8);

    assert.ok(result.noiseW < 0.8, 'noiseW should be reduced');
    const expected = 0.8 * 0.5;
    assert.ok(Math.abs(result.noiseW - expected) < 1e-6,
      `noiseW should be ${expected}, got ${result.noiseW}`);
  });

  it('clamps noiseScale multiplier at 0.5 for very short input', () => {
    // 5 phonemes -> ratio = 5/40 = 0.125, max(0.5, 0.125) = 0.5
    const result = adjustScalesForShortInput(5, 0.667, 0.8);

    const expected = 0.667 * 0.5;
    assert.ok(Math.abs(result.noiseScale - expected) < 1e-6,
      `noiseScale should clamp at 0.5 * 0.667 = ${expected}, got ${result.noiseScale}`);
  });

  it('clamps noiseW multiplier at 0.4 for very short input', () => {
    // 5 phonemes -> ratio = 0.125, max(0.4, 0.125) = 0.4
    const result = adjustScalesForShortInput(5, 0.667, 0.8);

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
    // 30 phonemes -> ratio = 30/40 = 0.75
    const result = adjustScalesForShortInput(30, 1.0, 1.0);

    assert.ok(Math.abs(result.noiseScale - 0.75) < 1e-6,
      `expected 0.75, got ${result.noiseScale}`);
    assert.ok(Math.abs(result.noiseW - 0.75) < 1e-6,
      `expected 0.75, got ${result.noiseW}`);
  });

  it('handles ratio exactly at the clamp boundary for noiseW', () => {
    // ratio = 0.4 -> phonemes = 0.4 * 40 = 16
    const result = adjustScalesForShortInput(16, 1.0, 1.0);

    const ratio = 16 / 40;
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
    // Return 5 phoneme IDs (well below MIN_PHONEME_IDS=40)
    const instance = createMockInstance({
      phonemeIds: [1, 4, 4, 4, 2],
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(5000), dims: [1, 5000] } };
      },
    });

    await instance.synthesize('hi');

    // Strategy A: phonemeIds should be padded to 40
    const inputIds = Array.from(capturedFeeds.input.data).map(Number);
    assert.equal(inputIds.length, 40, 'padded phonemeIds should be 40');
    assert.equal(inputIds[0], 1, 'BOS preserved');
    assert.equal(inputIds[39], 2, 'EOS preserved');

    // Strategy B: noiseScale and noiseW should be adjusted
    const scales = Array.from(capturedFeeds.scales.data);
    // Original noiseScale = 0.667, ratio = 5/40 = 0.125, clamp 0.5
    // adjusted = 0.667 * 0.5 = 0.3335
    assert.ok(scales[0] < 0.667, `noiseScale should be reduced: ${scales[0]}`);
    // lengthScale should be unchanged
    assert.ok(Math.abs(scales[1] - 1.0) < 1e-6, 'lengthScale unchanged');
    // noiseW should be adjusted: 0.8 * 0.4 = 0.32
    assert.ok(scales[2] < 0.8, `noiseW should be reduced: ${scales[2]}`);
  });

  it('does NOT pad or adjust scales for long phonemeIds', async () => {
    let capturedFeeds = null;
    const longIds = new Array(50).fill(4);
    longIds[0] = 1;
    longIds[49] = 2;

    const instance = createMockInstance({
      encode: () => ({ phonemeIds: longIds, prosodyFeatures: null }),
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(22050), dims: [1, 22050] } };
      },
    });

    await instance.synthesize('a long enough sentence with many phonemes');

    const inputIds = Array.from(capturedFeeds.input.data).map(Number);
    assert.equal(inputIds.length, 50, 'should NOT be padded');

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
      phonemeIds: [1, 4, 2], // very short, triggers padding
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

    const longIds = new Array(45).fill(4);
    longIds[0] = 1;
    longIds[44] = 2;

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
      phonemeIds: [1, 4, 2],
    });

    const result = await instance.synthesize('hi');

    assert.ok(result instanceof AudioResult);
    assert.equal(result.sampleRate, 44100);
  });

  it('passes prosody features through padding correctly', async () => {
    let capturedFeeds = null;
    const prosody = [
      [0, 0, 0], // BOS
      [1, 2, 3],
      [4, 5, 6],
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
        phonemeIds: [1, 4, 4, 2],
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
    // Padded to 40 phonemes, each with 3 features
    assert.deepEqual(capturedFeeds.prosody_features.dims, [1, 40, 3]);
  });

  it('Strategy B uses original phoneme count (before padding) for ratio', async () => {
    let capturedFeeds = null;
    // 10 phoneme IDs -> ratio = 10/40 = 0.25, clamped to 0.5 for noise, 0.4 for noiseW
    const ids = [1, 4, 4, 4, 4, 4, 4, 4, 4, 2];

    const instance = createMockInstance({
      phonemeIds: ids,
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(5000), dims: [1, 5000] } };
      },
    });

    await instance.synthesize('test');

    const scales = Array.from(capturedFeeds.scales.data);
    // noiseScale: 0.667 * max(0.5, 10/40) = 0.667 * 0.5 = 0.3335
    const expectedNoise = 0.667 * 0.5;
    assert.ok(Math.abs(scales[0] - expectedNoise) < 1e-4,
      `noiseScale: expected ~${expectedNoise}, got ${scales[0]}`);
    // noiseW: 0.8 * max(0.4, 10/40) = 0.8 * 0.4 = 0.32
    const expectedNoiseW = 0.8 * 0.4;
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
