/**
 * Tests for speaker_embedding functionality in PiperPlus
 *
 * Run with: node --test test/js/test-speaker-embedding.js
 *
 * Covers:
 *   1. synthesize() with speakerEmbedding option → feeds.speaker_embedding tensor created
 *   2. synthesize() without speakerEmbedding → feeds does NOT include speaker_embedding
 *   3. synthesizeWithVoiceCloning() → speakerEmbedding forwarded to _infer()
 *   4. speaker_embedding_mask NOT sent → feeds does NOT contain speaker_embedding_mask
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Minimal ort mock (same pattern as test-piper-plus-synthesize-flow.js)
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

let PiperPlus;
let importError = null;

try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
} catch (e) {
  importError = e;
}

const skip = PiperPlus == null;

// ---------------------------------------------------------------------------
// Helper: build a fully-wired PiperPlus instance with mock internals.
// Use >= 40 phoneme IDs to bypass short-text mitigation (Strategy A+B).
// ---------------------------------------------------------------------------

/**
 * @param {Object} [overrides]
 * @param {Object} [overrides.config]       - Merged into the default config.
 * @param {string[]} [overrides.inputNames] - ONNX session inputNames.
 * @param {Function} [overrides.sessionRun] - Override session.run().
 * @returns {InstanceType<typeof PiperPlus>}
 */
function createMockInstance(overrides = {}) {
  const instance = new PiperPlus();

  instance._config = overrides.config || {
    audio: { sample_rate: 22050 },
    inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
    phoneme_id_map: { _: [0], '^': [1], $: [2] },
  };

  // Use >= 40 phoneme IDs to bypass padding / scale-adjustment in synthesize()
  const longIds = new Array(45).fill(8);
  longIds[0] = 1;   // BOS
  longIds[44] = 2;  // EOS

  instance._phonemizer = {
    detectLanguage: () => 'ja',
    encode: () => ({ phonemeIds: longIds, prosodyFeatures: null }),
    dispose: () => {},
    supportedLanguages: ['ja', 'en'],
  };

  instance._session = {
    run: overrides.sessionRun || (async (feeds) => ({
      output: { data: new Float32Array(100), dims: [1, 100] },
    })),
    release: () => {},
    inputNames: overrides.inputNames || ['input', 'input_lengths', 'scales'],
    outputNames: ['output'],
  };

  instance._ort = globalThis.ort;
  instance._initialized = true;

  // Set capability flags based on inputNames (mirrors _init() logic)
  const inputNames = instance._session.inputNames || [];
  instance._hasSpeakerEmbedding = inputNames.includes('speaker_embedding');
  instance._hasProsodyFeatures = inputNames.includes('prosody_features');

  return instance;
}

// ===========================================================================
// 1. synthesize() WITH speakerEmbedding → tensor present in feeds
// ===========================================================================

describe('synthesize() with speakerEmbedding option', { skip }, () => {
  it('feeds.speaker_embedding テンソルが生成される', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);
    embedding.fill(0.1);

    const instance = createMockInstance({
      inputNames: ['input', 'input_lengths', 'scales', 'speaker_embedding'],
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('テスト', { speakerEmbedding: embedding });

    // Assert — speaker_embedding tensor must be present
    assert.ok(capturedFeeds, 'session.run should have been called');
    assert.ok(
      capturedFeeds.speaker_embedding !== undefined,
      'feeds.speaker_embedding should be set when speakerEmbedding option is provided'
    );
  });

  it('speaker_embedding テンソルの型は float32', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);

    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('テスト', { speakerEmbedding: embedding });

    // Assert
    assert.equal(capturedFeeds.speaker_embedding.type, 'float32');
  });

  it('speaker_embedding テンソルの dims が [1, 192]', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);

    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('テスト', { speakerEmbedding: embedding });

    // Assert
    assert.deepEqual(
      capturedFeeds.speaker_embedding.dims,
      [1, 192],
      'speaker_embedding tensor should have shape [1, 192]'
    );
  });

  it('speaker_embedding テンソルのデータが入力と一致する', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);
    for (let i = 0; i < 192; i++) embedding[i] = i / 192;

    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('テスト', { speakerEmbedding: embedding });

    // Assert — data should be the same Float32Array passed in
    assert.strictEqual(
      capturedFeeds.speaker_embedding.data,
      embedding,
      'speaker_embedding tensor data should be the Float32Array passed in options'
    );
  });
});

// ===========================================================================
// 2. synthesize() WITHOUT speakerEmbedding → tensor absent from feeds
// ===========================================================================

describe('synthesize() without speakerEmbedding option', { skip }, () => {
  it('speakerEmbedding 未指定時は feeds.speaker_embedding が存在しない', async () => {
    // Arrange
    let capturedFeeds = null;
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act — no speakerEmbedding passed
    await instance.synthesize('テスト');

    // Assert
    assert.ok(capturedFeeds, 'session.run should have been called');
    assert.equal(
      capturedFeeds.speaker_embedding,
      undefined,
      'feeds.speaker_embedding should be absent when option is not provided'
    );
  });

  it('speakerEmbedding を undefined で渡した場合も feeds.speaker_embedding が存在しない', async () => {
    // Arrange
    let capturedFeeds = null;
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('テスト', { speakerEmbedding: undefined });

    // Assert
    assert.equal(
      capturedFeeds.speaker_embedding,
      undefined,
      'feeds.speaker_embedding should be absent when speakerEmbedding is undefined'
    );
  });

  it('speakerEmbedding に空の Float32Array を渡した場合も feeds.speaker_embedding が存在しない', async () => {
    // Arrange
    let capturedFeeds = null;
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act — empty Float32Array has length 0, so the `length > 0` guard excludes it
    await instance.synthesize('テスト', { speakerEmbedding: new Float32Array(0) });

    // Assert
    assert.equal(
      capturedFeeds.speaker_embedding,
      undefined,
      'feeds.speaker_embedding should be absent when speakerEmbedding is an empty array'
    );
  });

  it('通常の feeds (input, input_lengths, scales) は必ず存在する', async () => {
    // Arrange
    let capturedFeeds = null;
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('テスト');

    // Assert — core feeds always present regardless of speakerEmbedding
    assert.ok(capturedFeeds.input, 'feeds.input should always be present');
    assert.ok(capturedFeeds.input_lengths, 'feeds.input_lengths should always be present');
    assert.ok(capturedFeeds.scales, 'feeds.scales should always be present');
  });
});

// ===========================================================================
// 3. synthesizeWithVoiceCloning() → speakerEmbedding forwarded to _infer()
// ===========================================================================

describe('synthesizeWithVoiceCloning() forwards speakerEmbedding to _infer()', { skip }, () => {
  it('speakerEmbedding が feeds.speaker_embedding として _infer() に渡される', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);
    embedding.fill(0.5);

    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesizeWithVoiceCloning('テスト', embedding);

    // Assert
    assert.ok(capturedFeeds, 'session.run should have been called');
    assert.ok(
      capturedFeeds.speaker_embedding !== undefined,
      'feeds.speaker_embedding should be set by synthesizeWithVoiceCloning'
    );
  });

  it('synthesizeWithVoiceCloning が AudioResult を返す', async () => {
    // Arrange
    const { AudioResult } = await import('../../src/index.js');
    const embedding = new Float32Array(192);
    const instance = createMockInstance();

    // Act
    const result = await instance.synthesizeWithVoiceCloning('テスト', embedding);

    // Assert
    assert.ok(result instanceof AudioResult, 'synthesizeWithVoiceCloning should return AudioResult');
  });

  it('speakerEmbedding が Float32Array でない場合はエラーになる', async () => {
    // Arrange
    const instance = createMockInstance();

    // Act & Assert
    await assert.rejects(
      () => instance.synthesizeWithVoiceCloning('テスト', [0.1, 0.2]),
      (err) => {
        assert.ok(
          err.message.includes('Float32Array'),
          `error message should mention Float32Array, got: ${err.message}`
        );
        return true;
      }
    );
  });

  it('speakerEmbedding が null の場合はエラーになる', async () => {
    // Arrange
    const instance = createMockInstance();

    // Act & Assert
    await assert.rejects(
      () => instance.synthesizeWithVoiceCloning('テスト', null),
      (err) => {
        assert.ok(err.message.includes('Float32Array'));
        return true;
      }
    );
  });

  it('speakerEmbedding のテンソル dims が [1, embedding.length]', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);

    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesizeWithVoiceCloning('テスト', embedding);

    // Assert
    assert.deepEqual(
      capturedFeeds.speaker_embedding.dims,
      [1, 192],
      'speaker_embedding tensor shape should be [1, embedding.length]'
    );
  });
});

// ===========================================================================
// 4. speaker_embedding_mask must NOT appear in feeds
// ===========================================================================

describe('speaker_embedding_mask は feeds に含まれない', { skip }, () => {
  it('synthesize() — feeds に speaker_embedding_mask が存在しない', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('テスト', { speakerEmbedding: embedding });

    // Assert
    assert.equal(
      capturedFeeds.speaker_embedding_mask,
      undefined,
      'feeds should NOT contain speaker_embedding_mask'
    );
  });

  it('synthesize() (no embedding) — feeds に speaker_embedding_mask が存在しない', async () => {
    // Arrange
    let capturedFeeds = null;
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act — no embedding provided
    await instance.synthesize('テスト');

    // Assert
    assert.equal(
      capturedFeeds.speaker_embedding_mask,
      undefined,
      'feeds should NOT contain speaker_embedding_mask even without speakerEmbedding'
    );
  });

  it('synthesizeWithVoiceCloning() — feeds に speaker_embedding_mask が存在しない', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesizeWithVoiceCloning('テスト', embedding);

    // Assert
    assert.equal(
      capturedFeeds.speaker_embedding_mask,
      undefined,
      'synthesizeWithVoiceCloning feeds should NOT contain speaker_embedding_mask'
    );
  });

  it('feeds に未知のキーが追加されていない (既知キーのみ)', async () => {
    // Arrange
    let capturedFeeds = null;
    const embedding = new Float32Array(192);
    const instance = createMockInstance({
      sessionRun: async (feeds) => {
        capturedFeeds = feeds;
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      },
    });

    // Act
    await instance.synthesize('テスト', { speakerEmbedding: embedding });

    // Assert — only the expected keys should be present
    const knownKeys = new Set([
      'input', 'input_lengths', 'scales',
      'lid',               // optional: multilingual models
      'speaker_embedding', // optional: zero-shot models
      'prosody_features',  // optional: prosody-aware models
    ]);
    for (const key of Object.keys(capturedFeeds)) {
      assert.ok(
        knownKeys.has(key),
        `Unexpected feed key: "${key}". feeds should only contain known tensor names.`
      );
    }
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
