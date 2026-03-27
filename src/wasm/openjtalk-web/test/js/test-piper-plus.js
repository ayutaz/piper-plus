/**
 * Unit Tests for PiperPlus class (src/index.js)
 *
 * Run with: node --test test/js/test-piper-plus.js
 *
 * Browser APIs (fetch, AudioContext, indexedDB, ort) are mocked.
 * No actual model loading or ONNX inference is performed.
 */

import { describe, it, mock, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Minimal browser API mocks
// ---------------------------------------------------------------------------

// Mock fetch — returns a config.json with the fields PiperPlus._init reads
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
        phoneme_id_map: { _: [0], '^': [1], $: [2] },
        num_speakers: 1,
        num_languages: 6,
      }),
    };
  }
  // Non-JSON URLs (model download etc.)
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    arrayBuffer: async () => new ArrayBuffer(16),
  };
};

// Mock onnxruntime-web
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

// Mock indexedDB (needed by ModelManager / DictManager internally)
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
// Import the module under test (after mocks are in place)
// ---------------------------------------------------------------------------

let PiperPlus;
let SimpleUnifiedPhonemizer, WebGPUSessionManager, ModelManager, DictManager;
let AudioResult, StreamingTTSPipeline;

let importError = null;
try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
  SimpleUnifiedPhonemizer = mod.SimpleUnifiedPhonemizer;
  WebGPUSessionManager = mod.WebGPUSessionManager;
  ModelManager = mod.ModelManager;
  DictManager = mod.DictManager;
  AudioResult = mod.AudioResult;
  StreamingTTSPipeline = mod.StreamingTTSPipeline;
} catch (e) {
  importError = e;
}

const skip = PiperPlus == null;

// ===========================================================================
// 1. PiperPlus class existence
// ===========================================================================

describe('PiperPlus class existence', { skip }, () => {
  it('should be importable from src/index.js', () => {
    assert.ok(PiperPlus, 'PiperPlus should be defined');
    assert.equal(typeof PiperPlus, 'function', 'PiperPlus should be a constructor');
  });

  it('PiperPlus.initialize should be a static function', () => {
    assert.equal(typeof PiperPlus.initialize, 'function');
  });

  it('prototype should expose synthesize, synthesizeStreaming, dispose', () => {
    assert.equal(typeof PiperPlus.prototype.synthesize, 'function');
    assert.equal(typeof PiperPlus.prototype.synthesizeStreaming, 'function');
    assert.equal(typeof PiperPlus.prototype.dispose, 'function');
  });

  it('prototype should expose isInitialized and config getters', () => {
    const instance = new PiperPlus();
    assert.equal(instance.isInitialized, false);
    assert.equal(instance.config, null);
  });
});

// ===========================================================================
// 2. Re-exports
// ===========================================================================

describe('re-exports from src/index.js', { skip }, () => {
  it('SimpleUnifiedPhonemizer is exported', () => {
    assert.ok(SimpleUnifiedPhonemizer, 'SimpleUnifiedPhonemizer should be exported');
    assert.equal(typeof SimpleUnifiedPhonemizer, 'function');
  });

  it('WebGPUSessionManager is exported', () => {
    assert.ok(WebGPUSessionManager, 'WebGPUSessionManager should be exported');
    assert.equal(typeof WebGPUSessionManager, 'function');
  });

  it('ModelManager is exported', () => {
    assert.ok(ModelManager, 'ModelManager should be exported');
    assert.equal(typeof ModelManager, 'function');
  });

  it('DictManager is exported', () => {
    assert.ok(DictManager, 'DictManager should be exported');
    assert.equal(typeof DictManager, 'function');
  });

  it('AudioResult is exported', () => {
    assert.ok(AudioResult, 'AudioResult should be exported');
    assert.equal(typeof AudioResult, 'function');
  });

  it('StreamingTTSPipeline is exported', () => {
    assert.ok(StreamingTTSPipeline, 'StreamingTTSPipeline should be exported');
    assert.equal(typeof StreamingTTSPipeline, 'function');
  });
});

// ===========================================================================
// 3. PiperPlus.initialize validation
// ===========================================================================

describe('PiperPlus.initialize validation', { skip }, () => {
  it('should reject when model option is not provided', async () => {
    await assert.rejects(
      () => PiperPlus.initialize({ ort: globalThis.ort }),
      (err) => {
        assert.ok(err instanceof Error, 'should throw an Error');
        return true;
      },
      'initialize() without model should reject'
    );
  });

  it('should reject when model is an empty string', async () => {
    await assert.rejects(
      () => PiperPlus.initialize({ model: '', ort: globalThis.ort }),
      (err) => {
        assert.ok(err instanceof Error);
        return true;
      },
      'initialize() with empty model string should reject'
    );
  });

  it('should reject when model name cannot be resolved', async () => {
    // Override fetch to simulate a 404 from HuggingFace
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url) => {
      if (typeof url === 'string' && url.includes('api/models')) {
        return { ok: false, status: 404, statusText: 'Not Found' };
      }
      return originalFetch(url);
    };

    await assert.rejects(
      () => PiperPlus.initialize({ model: 'nonexistent/model', ort: globalThis.ort }),
      (err) => {
        assert.ok(err instanceof Error);
        return true;
      },
      'initialize() with unresolvable model should reject'
    );

    globalThis.fetch = originalFetch;
  });

  it('should reject when ort is not available', async () => {
    const savedOrt = globalThis.ort;
    delete globalThis.ort;

    await assert.rejects(
      () => PiperPlus.initialize({ model: 'tsukuyomi' }),
      (err) => {
        assert.ok(err instanceof Error);
        assert.ok(
          err.message.includes('onnxruntime-web'),
          `message should mention onnxruntime-web, got: "${err.message}"`
        );
        return true;
      },
      'initialize() without ort should reject'
    );

    globalThis.ort = savedOrt;
  });
});

// ===========================================================================
// 4. SynthesizeOptions default values
// ===========================================================================

describe('SynthesizeOptions default values', { skip }, () => {
  it('language defaults to auto-detection when not specified', () => {
    // Verify by inspecting the synthesize() source path:
    // options.language is optional per the JSDoc — when omitted, the code
    // falls back to this._phonemizer.detectLanguage(text).
    // We confirm the contract by constructing a raw instance and checking
    // that synthesize() does not require language.
    const instance = new PiperPlus();
    // Set up minimal internals to exercise the code path
    instance._initialized = true;
    instance._config = {
      inference: {},
      phoneme_id_map: { _: [0] },
    };
    instance._phonemizer = {
      detectLanguage: mock.fn(() => 'ja'),
      textToPhonemes: mock.fn(async () => 'mock-labels'),
      extractPhonemes: mock.fn(() => ['^', 'a', '$']),
      dispose: () => {},
    };
    instance._session = {
      run: mock.fn(async () => ({
        output: { data: new Float32Array(100), dims: [1, 100] },
      })),
      release: () => {},
    };
    instance._ort = globalThis.ort;

    // Call synthesize without specifying language — should not throw
    assert.doesNotReject(
      () => instance.synthesize('test text'),
      'synthesize() without language option should not reject'
    );
  });

  it('noiseScale defaults to 0.667', () => {
    // The default constant is defined in index.js; verify via a round-trip:
    // construct an instance with a config that has no inference overrides,
    // and confirm the infer call receives the expected default.
    const instance = new PiperPlus();
    instance._initialized = true;
    instance._config = {
      phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
    };
    instance._ort = globalThis.ort;

    let capturedScales = null;
    instance._session = {
      run: mock.fn(async (feeds) => {
        capturedScales = Array.from(feeds.scales.data);
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      }),
      release: () => {},
    };
    instance._phonemizer = {
      detectLanguage: () => 'ja',
      textToPhonemes: async () => 'xx^xx-sil+a=sil/A:0+0+0',
      extractPhonemes: () => ['^', 'a', '$'],
      dispose: () => {},
    };

    return instance.synthesize('a').then(() => {
      assert.ok(capturedScales, 'scales should have been captured');
      // [noiseScale, lengthScale, noiseW]
      assert.ok(Math.abs(capturedScales[0] - 0.667) < 1e-3, 'noiseScale default');
      assert.ok(Math.abs(capturedScales[1] - 1.0) < 1e-3, 'lengthScale default');
      assert.ok(Math.abs(capturedScales[2] - 0.8) < 1e-3, 'noiseW default');
    });
  });

  it('config inference overrides take precedence over hard-coded defaults', () => {
    const instance = new PiperPlus();
    instance._initialized = true;
    instance._config = {
      inference: { noise_scale: 0.5, length_scale: 1.2, noise_w: 0.6 },
      phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
    };
    instance._ort = globalThis.ort;

    let capturedScales = null;
    instance._session = {
      run: mock.fn(async (feeds) => {
        capturedScales = Array.from(feeds.scales.data);
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      }),
      release: () => {},
    };
    instance._phonemizer = {
      detectLanguage: () => 'ja',
      textToPhonemes: async () => 'labels',
      extractPhonemes: () => ['^', 'a', '$'],
      dispose: () => {},
    };

    return instance.synthesize('a').then(() => {
      assert.ok(capturedScales);
      assert.ok(Math.abs(capturedScales[0] - 0.5) < 1e-3, 'noiseScale from config');
      assert.ok(Math.abs(capturedScales[1] - 1.2) < 1e-3, 'lengthScale from config');
      assert.ok(Math.abs(capturedScales[2] - 0.6) < 1e-3, 'noiseW from config');
    });
  });

  it('explicit options override config defaults', () => {
    const instance = new PiperPlus();
    instance._initialized = true;
    instance._config = {
      inference: { noise_scale: 0.5, length_scale: 1.2, noise_w: 0.6 },
      phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
    };
    instance._ort = globalThis.ort;

    let capturedScales = null;
    instance._session = {
      run: mock.fn(async (feeds) => {
        capturedScales = Array.from(feeds.scales.data);
        return { output: { data: new Float32Array(100), dims: [1, 100] } };
      }),
      release: () => {},
    };
    instance._phonemizer = {
      detectLanguage: () => 'ja',
      textToPhonemes: async () => 'labels',
      extractPhonemes: () => ['^', 'a', '$'],
      dispose: () => {},
    };

    return instance
      .synthesize('a', { noiseScale: 0.3, lengthScale: 0.9, noiseW: 0.4 })
      .then(() => {
        assert.ok(capturedScales);
        assert.ok(Math.abs(capturedScales[0] - 0.3) < 1e-3, 'noiseScale from explicit option');
        assert.ok(Math.abs(capturedScales[1] - 0.9) < 1e-3, 'lengthScale from explicit option');
        assert.ok(Math.abs(capturedScales[2] - 0.4) < 1e-3, 'noiseW from explicit option');
      });
  });
});

// ===========================================================================
// 5. dispose()
// ===========================================================================

describe('dispose()', { skip }, () => {
  it('should not throw on first call', () => {
    const instance = new PiperPlus();
    assert.doesNotThrow(() => instance.dispose());
  });

  it('should not throw on double dispose', () => {
    const instance = new PiperPlus();
    instance.dispose();
    assert.doesNotThrow(
      () => instance.dispose(),
      'second dispose() call should not throw'
    );
  });

  it('should release the ONNX session', () => {
    const instance = new PiperPlus();
    const releaseFn = mock.fn();
    instance._session = { release: releaseFn };
    instance._phonemizer = { dispose: () => {} };
    instance._initialized = true;

    instance.dispose();

    assert.equal(releaseFn.mock.callCount(), 1, 'session.release() should be called once');
    assert.equal(instance._session, null, 'session should be nulled');
  });

  it('should dispose the phonemizer', () => {
    const instance = new PiperPlus();
    const disposeFn = mock.fn();
    instance._session = { release: () => {} };
    instance._phonemizer = { dispose: disposeFn };
    instance._initialized = true;

    instance.dispose();

    assert.equal(disposeFn.mock.callCount(), 1, 'phonemizer.dispose() should be called once');
    assert.equal(instance._phonemizer, null, 'phonemizer should be nulled');
  });

  it('should set isInitialized to false after dispose', () => {
    const instance = new PiperPlus();
    instance._session = { release: () => {} };
    instance._phonemizer = { dispose: () => {} };
    instance._initialized = true;

    assert.equal(instance.isInitialized, true);
    instance.dispose();
    assert.equal(instance.isInitialized, false);
  });

  it('should handle session without release method gracefully', () => {
    const instance = new PiperPlus();
    instance._session = {}; // no release method
    instance._phonemizer = { dispose: () => {} };
    instance._initialized = true;

    assert.doesNotThrow(
      () => instance.dispose(),
      'dispose() should not throw when session lacks release()'
    );
    assert.equal(instance._session, null);
  });

  it('synthesize() should reject after dispose', async () => {
    const instance = new PiperPlus();
    instance._initialized = true;
    instance._session = { release: () => {} };
    instance._phonemizer = { dispose: () => {} };

    instance.dispose();

    await assert.rejects(
      () => instance.synthesize('hello'),
      (err) => {
        assert.ok(err.message.includes('not initialized'));
        return true;
      },
      'synthesize() after dispose should reject'
    );
  });
});

// ===========================================================================
// 6. synthesize() input validation
// ===========================================================================

describe('synthesize() input validation', { skip }, () => {
  let instance;

  beforeEach(() => {
    instance = new PiperPlus();
    instance._initialized = true;
    instance._config = {
      phoneme_id_map: { _: [0] },
    };
    instance._ort = globalThis.ort;
    instance._session = {
      run: async () => ({
        output: { data: new Float32Array(100), dims: [1, 100] },
      }),
      release: () => {},
    };
    instance._phonemizer = {
      detectLanguage: () => 'ja',
      textToPhonemes: async () => 'labels',
      extractPhonemes: () => ['^', '$'],
      dispose: () => {},
    };
  });

  it('should reject when text is empty', async () => {
    await assert.rejects(
      () => instance.synthesize(''),
      (err) => {
        assert.ok(err.message.includes('text'));
        return true;
      }
    );
  });

  it('should reject when text is null', async () => {
    await assert.rejects(
      () => instance.synthesize(null),
      (err) => {
        assert.ok(err instanceof Error);
        return true;
      }
    );
  });

  it('should reject when called before initialization', async () => {
    const raw = new PiperPlus();
    await assert.rejects(
      () => raw.synthesize('hello'),
      (err) => {
        assert.ok(err.message.includes('not initialized'));
        return true;
      }
    );
  });
});

// ===========================================================================
// 7. synthesizeStreaming() input validation
// ===========================================================================

describe('synthesizeStreaming() input validation', { skip }, () => {
  it('should reject when text is empty', async () => {
    const instance = new PiperPlus();
    instance._initialized = true;

    await assert.rejects(
      () => instance.synthesizeStreaming(''),
      (err) => {
        assert.ok(err.message.includes('text'));
        return true;
      }
    );
  });

  it('should reject when called before initialization', async () => {
    const raw = new PiperPlus();
    await assert.rejects(
      () => raw.synthesizeStreaming('hello'),
      (err) => {
        assert.ok(err.message.includes('not initialized'));
        return true;
      }
    );
  });
});

// ===========================================================================
// Report import error if PiperPlus could not be loaded
// ===========================================================================

if (importError) {
  describe('import error', () => {
    it('should not have an import error', () => {
      assert.fail(`Failed to import src/index.js: ${importError.message}`);
    });
  });
}
