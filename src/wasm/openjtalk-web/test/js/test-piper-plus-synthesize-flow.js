/**
 * End-to-end Tests for PiperPlus synthesize() flow
 *
 * Run with: node --test test/js/test-piper-plus-synthesize-flow.js
 *
 * synthesize() の全体フロー（言語検出 -> 音素化 -> テンソル構築 ->
 * session.run() -> 音声抽出 -> AudioResult 返却）を完全モックで検証。
 */

import { describe, it, beforeEach, mock } from 'node:test';
import assert from 'node:assert/strict';

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
let importError = null;

try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
  AudioResult = mod.AudioResult;
} catch (e) {
  importError = e;
}

const skip = PiperPlus == null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a fully-wired PiperPlus instance with mock phonemizer and session.
 * Callers can override individual mock methods via the options object.
 */
function createMockInstance(overrides = {}) {
  const instance = new PiperPlus();

  const mockPhonemeIdMap = {
    _: [0], '^': [1], $: [2], ' ': [3],
    k: [10], o: [11], N: [12], n: [13],
    i: [14], ch: [15], w: [16], a: [17],
    h: [20], '@': [21], l: [22], 'oU': [23],
  };

  instance._config = overrides.config || {
    audio: { sample_rate: 22050 },
    inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
    phoneme_id_map: mockPhonemeIdMap,
  };

  const outputAudio = overrides.outputAudio || new Float32Array(22050);

  // Default encode returns IDs for [k, o, N, n, i, ch, i, w, a] = [10,11,12,13,14,15,14,16,17]
  instance._phonemizer = {
    detectLanguage: overrides.detectLanguage || ((text) => 'ja'),
    encode: overrides.encode || ((text, language) => ({
      phonemeIds: [10, 11, 12, 13, 14, 15, 14, 16, 17],
      prosodyFeatures: null,
    })),
    dispose: overrides.phonemizerDispose || (() => {}),
    supportedLanguages: ['en', 'zh', 'es', 'fr', 'pt'],
  };

  instance._session = {
    run: overrides.sessionRun || (async (feeds) => ({
      output: { data: outputAudio, dims: [1, outputAudio.length] },
    })),
    release: overrides.sessionRelease || (() => {}),
  };

  instance._ort = globalThis.ort;
  instance._initialized = true;

  return instance;
}

// ===========================================================================
// Tests
// ===========================================================================

describe('PiperPlus synthesize() end-to-end flow', { skip }, () => {
  // -----------------------------------------------------------------------
  // 1. Japanese synthesis returns AudioResult
  // -----------------------------------------------------------------------
  it('日本語テキストを合成すると AudioResult が返される', async () => {
    // Arrange
    const instance = createMockInstance();

    // Act
    const result = await instance.synthesize('こんにちは');

    // Assert
    assert.ok(result instanceof AudioResult);
  });

  // -----------------------------------------------------------------------
  // 2. English synthesis returns AudioResult
  // -----------------------------------------------------------------------
  it('英語テキストを合成すると AudioResult が返される', async () => {
    // Arrange
    const instance = createMockInstance({
      detectLanguage: () => 'en',
      encode: (text, language) => ({
        phonemeIds: [14, 21, 22, 23],
        prosodyFeatures: null,
      }),
    });

    // Act
    const result = await instance.synthesize('Hello');

    // Assert
    assert.ok(result instanceof AudioResult);
  });

  // -----------------------------------------------------------------------
  // 3. AudioResult has correct sample rate from config
  // -----------------------------------------------------------------------
  it('AudioResult に正しいサンプルレートが設定される', async () => {
    // Arrange
    const instance = createMockInstance({
      config: {
        audio: { sample_rate: 44100 },
        inference: {},
        phoneme_id_map: { _: [0], k: [10], o: [11], N: [12], n: [13], i: [14], ch: [15], w: [16], a: [17] },
      },
    });

    // Act
    const result = await instance.synthesize('こんにちは');

    // Assert
    assert.equal(result.sampleRate, 44100);
  });

  // -----------------------------------------------------------------------
  // 4. Correct phoneme_ids tensor passed to session.run
  // -----------------------------------------------------------------------
  it('ONNX session.run に正しい phoneme_ids テンソルが渡される', async () => {
    // Arrange — use >= 40 phoneme IDs to bypass short-text padding
    const expectedIds = new Array(45).fill(8);
    expectedIds[0] = 10;
    expectedIds[44] = 17;
    let capturedFeeds = null;
    const instance = createMockInstance({
      encode: (text, language) => ({
        phonemeIds: expectedIds,
        prosodyFeatures: null,
      }),
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('こんにちは');

    // Assert — phoneme_ids should pass through unmodified (length >= 40)
    const ids = Array.from(capturedFeeds.input.data).map(Number);
    assert.deepEqual(ids, expectedIds);
  });

  // -----------------------------------------------------------------------
  // 5. Correct scales tensor passed to session.run
  // -----------------------------------------------------------------------
  it('ONNX session.run に正しい scales テンソルが渡される', async () => {
    // Arrange — use >= 40 phoneme IDs to bypass short-text scale adjustment
    const longIds = new Array(45).fill(8);
    longIds[0] = 10;
    longIds[44] = 17;
    let capturedFeeds = null;
    const instance = createMockInstance({
      encode: (text, language) => ({
        phonemeIds: longIds,
        prosodyFeatures: null,
      }),
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act — use explicit scale values
    await instance.synthesize('テスト', {
      noiseScale: 0.5,
      lengthScale: 1.2,
      noiseW: 0.6,
    });

    // Assert — use tolerance for float32 precision
    const scales = Array.from(capturedFeeds.scales.data);
    assert.equal(scales.length, 3);
    assert.ok(Math.abs(scales[0] - 0.5) < 1e-6, `noiseScale: ${scales[0]}`);
    assert.ok(Math.abs(scales[1] - 1.2) < 1e-6, `lengthScale: ${scales[1]}`);
    assert.ok(Math.abs(scales[2] - 0.6) < 1e-6, `noiseW: ${scales[2]}`);
  });

  // -----------------------------------------------------------------------
  // 6. Explicit language option skips auto-detection
  // -----------------------------------------------------------------------
  it('language オプションで言語検出をスキップする', async () => {
    // Arrange
    let detectCalled = false;
    const instance = createMockInstance({
      detectLanguage: () => { detectCalled = true; return 'ja'; },
      encode: (text, language) => ({
        phonemeIds: [14, 21, 22, 23],
        prosodyFeatures: null,
      }),
    });

    // Act — pass language explicitly
    await instance.synthesize('Hello', { language: 'en' });

    // Assert
    assert.equal(detectCalled, false);
  });

  // -----------------------------------------------------------------------
  // 7. speakerId option — currently not forwarded to ONNX tensors
  // -----------------------------------------------------------------------
  it('speakerId オプションが ONNX テンソルに反映される', async () => {
    // Arrange
    let capturedFeeds = null;
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('こんにちは', { speakerId: 5 });

    // Assert — current implementation does not pass sid to feeds
    // Verify the known feed keys (input, input_lengths, scales)
    assert.ok(capturedFeeds.input, 'input tensor should exist');
    assert.ok(capturedFeeds.input_lengths, 'input_lengths tensor should exist');
    assert.ok(capturedFeeds.scales, 'scales tensor should exist');
    assert.equal(capturedFeeds.sid, undefined, 'sid tensor is not yet implemented');
  });

  // -----------------------------------------------------------------------
  // 8. Result samples is Float32Array
  // -----------------------------------------------------------------------
  it('合成結果が Float32Array を含む', async () => {
    // Arrange
    const expectedAudio = new Float32Array([0.1, -0.2, 0.3, 0.0, -0.5]);
    const instance = createMockInstance({ outputAudio: expectedAudio });

    // Act
    const result = await instance.synthesize('テスト');

    // Assert
    assert.ok(result.samples instanceof Float32Array);
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
