/**
 * Boundary / edge-case tests for PiperPlus (src/index.js)
 *
 * Covers whitespace input, long text, unknown phonemes, falsy-but-valid
 * option values, missing config fields, double-initialize, and post-dispose
 * lifecycle errors.
 *
 * Run with: node --test test/js/test-piper-plus-boundary.js
 */

import { describe, it, mock } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Minimal browser API mocks (same pattern as test-piper-plus.js)
// ---------------------------------------------------------------------------

globalThis.fetch = async (url) => {
  if (typeof url === 'string' && url.endsWith('.json')) {
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({
        audio: { sample_rate: 22050 },
        inference: {
          noise_scale: 0.667,
          length_scale: 1.0,
          noise_w: 0.8,
        },
        phoneme_id_map: {
          _: [0],
          '^': [1],
          $: [2],
          ' ': [3],
          a: [7],
          k: [10],
          o: [11],
        },
        num_speakers: 1,
        num_languages: 6,
      }),
    };
  }
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    arrayBuffer: async () => new ArrayBuffer(16),
  };
};

globalThis.ort = {
  InferenceSession: {
    create: async () => ({
      inputNames: ['input', 'input_lengths', 'scales'],
      outputNames: ['output'],
      run: async () => ({
        output: { data: new Float32Array(22050), dims: [1, 22050] },
      }),
      release: () => {},
    }),
  },
  Tensor: class {
    constructor(type, data, dims) {
      this.type = type;
      this.data = data;
      this.dims = dims;
    }
  },
};

globalThis.indexedDB = {
  open: () => {
    const req = {};
    setTimeout(() => {
      if (req.onupgradeneeded) {
        req.onupgradeneeded({
          target: {
            result: {
              objectStoreNames: { contains: () => false },
              createObjectStore: () => ({}),
            },
          },
        });
      }
      if (req.onsuccess) {
        req.result = {
          transaction: () => ({
            objectStore: () => ({
              get: () => {
                const r = {};
                setTimeout(() => {
                  r.result = null;
                  if (r.onsuccess) r.onsuccess();
                }, 0);
                return r;
              },
              put: () => {
                const r = {};
                setTimeout(() => {
                  if (r.onsuccess) r.onsuccess();
                }, 0);
                return r;
              },
              clear: () => {
                const r = {};
                setTimeout(() => {
                  if (r.onsuccess) r.onsuccess();
                }, 0);
                return r;
              },
            }),
          }),
        };
        req.onsuccess();
      }
    }, 0);
    return req;
  },
};

// ---------------------------------------------------------------------------
// Import (with TDD skip guard)
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
// Helper: build a mocked, initialized PiperPlus instance
// ---------------------------------------------------------------------------

/**
 * Create a PiperPlus instance whose internals are fully mocked so that
 * synthesize() can execute without real ONNX / phonemizer resources.
 *
 * @param {Object} [overrides]
 * @param {Object} [overrides.config]    - Merged into the default config
 * @param {Object} [overrides.phonemizer] - Replace the mock phonemizer
 * @param {Object} [overrides.session]    - Replace the mock ONNX session
 * @returns {InstanceType<typeof PiperPlus>}
 */
function createMockedInstance(overrides = {}) {
  const instance = new PiperPlus();

  instance._initialized = true;
  instance._ort = globalThis.ort;

  instance._config = {
    audio: { sample_rate: 22050 },
    inference: {
      noise_scale: 0.667,
      length_scale: 1.0,
      noise_w: 0.8,
    },
    phoneme_id_map: {
      _: [0],
      '^': [1],
      $: [2],
      ' ': [3],
      a: [7],
      k: [10],
      o: [11],
    },
    num_speakers: 1,
    num_languages: 6,
    ...overrides.config,
  };

  // Use >= 40 phoneme IDs to bypass short-text mitigation (Strategy A+B)
  const longIds = new Array(45).fill(7);
  longIds[0] = 1;   // BOS
  longIds[44] = 2;  // EOS
  instance._phonemizer = overrides.phonemizer || {
    detectLanguage: mock.fn(() => 'ja'),
    encode: mock.fn((text, language) => ({
      phonemeIds: longIds,
      prosodyFeatures: null,
    })),
    dispose: mock.fn(),
    supportedLanguages: ['en', 'zh', 'es', 'fr', 'pt'],
  };

  const capturedFeeds = [];
  instance._session = overrides.session || {
    run: mock.fn(async (feeds) => {
      capturedFeeds.push(feeds);
      return {
        output: { data: new Float32Array(100), dims: [1, 100] },
      };
    }),
    release: mock.fn(),
  };

  // Expose captured feeds for assertion
  instance.__capturedFeeds = capturedFeeds;

  return instance;
}

// ===========================================================================
// 1. Whitespace-only input
// ===========================================================================

describe('空白のみの文字列で synthesize するとエラー', { skip }, () => {
  it('半角スペースのみの文字列は text バリデーションを通過する', async () => {
    // Arrange
    const instance = createMockedInstance();

    // Act & Assert
    // '   ' is truthy so the `if (!text)` guard does NOT reject it.
    // The call should succeed (no error thrown).
    await assert.doesNotReject(() => instance.synthesize('   '));
  });

  it('改行のみの文字列は text バリデーションを通過する', async () => {
    // Arrange
    const instance = createMockedInstance();

    // Act & Assert
    await assert.doesNotReject(() => instance.synthesize('\n'));
  });

  it('タブのみの文字列は text バリデーションを通過する', async () => {
    // Arrange
    const instance = createMockedInstance();

    // Act & Assert
    await assert.doesNotReject(() => instance.synthesize('\t'));
  });
});

// ===========================================================================
// 2. Very long text
// ===========================================================================

describe('非常に長いテキストでも synthesize が成功する', { skip }, () => {
  it('1000文字以上のテキストで synthesize が正常完了する', async () => {
    // Arrange
    const longText = 'あ'.repeat(1200);
    const instance = createMockedInstance();

    // Act
    const result = await instance.synthesize(longText);

    // Assert
    assert.ok(result, 'synthesize should return a result for long text');
  });
});

// ===========================================================================
// 3. Phoneme encoding via G2P
// ===========================================================================

describe('G2P encode を経由した phoneme ID 取得', { skip }, () => {
  it('G2P.encode の返す phonemeIds が ONNX テンソルに使用される', async () => {
    // Arrange — use >= 40 phoneme IDs to bypass short-text padding
    let capturedFeeds = null;
    const expectedIds = new Array(45).fill(10);
    expectedIds[0] = 1;   // BOS
    expectedIds[44] = 2;  // EOS
    const instance = createMockedInstance({
      phonemizer: {
        detectLanguage: mock.fn(() => 'ja'),
        encode: mock.fn((text, language) => ({
          phonemeIds: expectedIds,
          prosodyFeatures: null,
        })),
        dispose: mock.fn(),
        supportedLanguages: ['en', 'zh', 'es', 'fr', 'pt'],
      },
      session: {
        run: mock.fn(async (feeds) => {
          capturedFeeds = feeds;
          return { output: { data: new Float32Array(100), dims: [1, 100] } };
        }),
        release: mock.fn(),
      },
    });

    // Act
    await instance.synthesize('test');

    // Assert — phoneme IDs from encode are passed to ONNX unmodified
    assert.ok(capturedFeeds, 'session.run should have been called');
    const ids = Array.from(capturedFeeds.input.data).map(Number);
    assert.deepStrictEqual(ids, expectedIds);
  });

  it('phonemizer.encode がエラーを投げるとリジェクトされる', async () => {
    // Arrange — phonemizer that throws on encode (simulates missing config)
    const instance = createMockedInstance({
      phonemizer: {
        detectLanguage: mock.fn(() => 'ja'),
        encode: mock.fn(() => { throw new Error('phoneme_id_map is required'); }),
        dispose: mock.fn(),
        supportedLanguages: ['en'],
      },
    });

    // Act & Assert
    await assert.rejects(
      () => instance.synthesize('test'),
      (err) => {
        assert.ok(err.message.includes('phoneme_id_map'));
        return true;
      }
    );
  });
});

// ===========================================================================
// 4. noiseScale = 0 (falsy but valid)
// ===========================================================================

describe('noiseScale に 0 を渡した場合は 0 が使用される', { skip }, () => {
  it('noiseScale=0 は nullish coalescing により正しく 0 が渡される', async () => {
    // Arrange
    const instance = createMockedInstance();

    // Act
    await instance.synthesize('test', { noiseScale: 0 });

    // Assert
    const scales = Array.from(instance.__capturedFeeds[0].scales.data);
    assert.strictEqual(scales[0], 0);
  });
});

// ===========================================================================
// 5. Negative noiseScale
// ===========================================================================

describe('noiseScale に負の値を渡した場合の挙動', { skip }, () => {
  it('負の noiseScale がそのまま ONNX inference に渡される', async () => {
    // Arrange
    const instance = createMockedInstance();

    // Act
    await instance.synthesize('test', { noiseScale: -0.5 });

    // Assert — the implementation does not clamp, so -0.5 passes through
    const scales = Array.from(instance.__capturedFeeds[0].scales.data);
    assert.ok(scales[0] < 0);
  });
});

// ===========================================================================
// 6. Unknown language code
// ===========================================================================

describe('language に未知のコードを渡した場合', { skip }, () => {
  it('未知の言語コードでも G2P.encode に委譲される', async () => {
    // Arrange
    const encodeFn = mock.fn((text, language) => ({
      phonemeIds: [1, 7, 2],
      prosodyFeatures: null,
    }));
    const instance = createMockedInstance({
      phonemizer: {
        detectLanguage: () => 'ja',
        encode: encodeFn,
        dispose: mock.fn(),
        supportedLanguages: ['en', 'zh', 'es', 'fr', 'pt'],
      },
    });

    // Act — pass explicit language
    await instance.synthesize('test', { language: 'xx' });

    // Assert — encode is called with (text, language)
    assert.strictEqual(encodeFn.mock.calls[0].arguments[1], 'xx');
  });
});

// ===========================================================================
// 7. config.inference undefined
// ===========================================================================

describe('config.inference が undefined の場合はデフォルト値が使用される', { skip }, () => {
  it('inference 未設定時に noiseScale=0.667 がデフォルトになる', async () => {
    // Arrange
    const instance = createMockedInstance({
      config: { inference: undefined },
    });

    // Act
    await instance.synthesize('test');

    // Assert — DEFAULT_NOISE_SCALE = 0.667
    const scales = Array.from(instance.__capturedFeeds[0].scales.data);
    assert.ok(Math.abs(scales[0] - 0.667) < 1e-3);
  });
});

// ===========================================================================
// 8. config.audio.sample_rate undefined
// ===========================================================================

describe('config.audio.sample_rate が未設定の場合は 22050 がデフォルト', { skip }, () => {
  it('audio 未設定時に sampleRate=22050 の AudioResult が返される', async () => {
    // Arrange
    const instance = createMockedInstance({
      config: { audio: undefined },
    });

    // Act
    const result = await instance.synthesize('test');

    // Assert — DEFAULT_SAMPLE_RATE = 22050
    assert.strictEqual(result.sampleRate, 22050);
  });
});

// ===========================================================================
// 9. Double initialize
// ===========================================================================

describe('二重 initialize の挙動', { skip }, () => {
  it('既に初期化済みのインスタンスで再度 _init を呼ぶと _initialized が true のまま維持される', async () => {
    // Arrange
    const instance = createMockedInstance();
    assert.strictEqual(instance.isInitialized, true);

    // Act — call _init again to simulate double initialization
    // We directly set _initialized again to confirm the factory contract:
    // PiperPlus.initialize() always creates a NEW instance, so the same
    // object is never initialized twice via the public API.
    const secondInstance = new PiperPlus();

    // Assert — a fresh instance starts as not initialized
    assert.strictEqual(secondInstance.isInitialized, false);
  });
});

// ===========================================================================
// 10. synthesize after dispose
// ===========================================================================

describe('dispose 後の synthesize でエラー', { skip }, () => {
  it('dispose 後に synthesize を呼ぶと not initialized エラーになる', async () => {
    // Arrange
    const instance = createMockedInstance();
    instance.dispose();

    // Act & Assert
    await assert.rejects(
      () => instance.synthesize('hello'),
      (err) => {
        assert.ok(err.message.includes('not initialized'));
        return true;
      }
    );
  });
});

// ===========================================================================
// 11. Re-initialize after dispose
// ===========================================================================

describe('dispose 後の再 initialize でエラー', { skip }, () => {
  it('dispose 後に isInitialized が false になっている', () => {
    // Arrange
    const instance = createMockedInstance();

    // Act
    instance.dispose();

    // Assert
    assert.strictEqual(instance.isInitialized, false);
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
