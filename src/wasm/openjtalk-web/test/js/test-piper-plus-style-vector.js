/**
 * Unit tests for PiperPlus.synthesize({ styleVector }) —.
 *
 * Run with: node --test test/js/test-piper-plus-style-vector.js
 *
 * Validates:
 *   - SynthesizeOptions.styleVector type checking (throws on non-Float32Array)
 *   - ONNX feeds contain `style_vector` + `style_vector_mask` when the model
 *     exposes the `style_vector` input
 *   - mask=0 with zero-fill when styleVector is omitted
 *   - mask=1 with user vector when styleVector is provided
 *   - length mismatch between styleVector and configured style_vector_dim
 *     raises a descriptive error
 *
 * Browser APIs are mocked; no real model load or ONNX inference.
 */

import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

const ORIGINAL_FETCH = globalThis.fetch;
const ORIGINAL_ORT = globalThis.ort;
const ORIGINAL_INDEXEDDB = globalThis.indexedDB;

const STYLE_VECTOR_DIM = 256;

function makeConfigJson(overrides = {}) {
  return {
    audio: { sample_rate: 22050 },
    inference: {
      noise_scale: 0.667,
      length_scale: 1.0,
      noise_w: 0.8,
    },
    phoneme_id_map: { _: [0], '^': [1], $: [2] },
    num_speakers: 1,
    num_languages: 6,
    style_vector_dim: STYLE_VECTOR_DIM,
    ...overrides,
  };
}

/**
 * Captures every `session.run(feeds)` call for assertions.
 * @type {Array<Record<string, { type: string, data: ArrayLike<number>, dims: number[] }>>}
 */
let capturedFeeds = [];

function installGlobalMocks({ hasStyleVectorInput = true } = {}) {
  capturedFeeds = [];

  globalThis.fetch = async (url) => {
    if (typeof url === 'string' && url.endsWith('.json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => makeConfigJson(),
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () => new ArrayBuffer(16),
    };
  };

  const modelInputNames = ['input', 'input_lengths', 'scales'];
  if (hasStyleVectorInput) {
    modelInputNames.push('style_vector', 'style_vector_mask');
  }

  globalThis.ort = {
    InferenceSession: {
      create: async () => ({
        inputNames: modelInputNames,
        outputNames: ['output', 'durations'],
        run: async (feeds) => {
          capturedFeeds.push(feeds);
          const inputLen =
            (feeds?.input?.data && feeds.input.data.length) ||
            (feeds?.input?.dims && feeds.input.dims[1]) ||
            5;
          const durData = new Float32Array(inputLen);
          return {
            output: { data: new Float32Array(22050), dims: [1, 22050] },
            durations: { data: durData, dims: [1, inputLen] },
          };
        },
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
    open: () => ({
      onsuccess: null,
      onerror: null,
      onupgradeneeded: null,
    }),
  };
}

function restoreGlobalMocks() {
  globalThis.fetch = ORIGINAL_FETCH;
  globalThis.ort = ORIGINAL_ORT;
  globalThis.indexedDB = ORIGINAL_INDEXEDDB;
  capturedFeeds = [];
}

// ---------------------------------------------------------------------------
// Tests: input validation (runs without instantiating PiperPlus — pure option
// shape checks against the d.ts contract).
// ---------------------------------------------------------------------------

describe('PiperPlus styleVector option validation', () => {
  beforeEach(() => installGlobalMocks());
  afterEach(() => restoreGlobalMocks());

  it('rejects non-Float32Array styleVector with a descriptive error', async () => {
    const { PiperPlus } = await import('../../src/index.js');
    const instance = Object.create(PiperPlus.prototype);
    // Mark instance as "ready" so _assertReady() doesn't trip.
    instance._initialized = true;
    instance._warmupPromise = null;
    instance._config = makeConfigJson();

    await assert.rejects(
      () => instance.synthesize('hello', { styleVector: [0.1, 0.2] }),
      /styleVector must be a Float32Array/,
      'should reject plain arrays',
    );
    await assert.rejects(
      () => instance.synthesize('hello', { styleVector: 'not-a-vector' }),
      /styleVector must be a Float32Array/,
      'should reject strings',
    );
  });

  it('accepts undefined styleVector (falls through to zeros + mask=0)', async () => {
    const { PiperPlus } = await import('../../src/index.js');
    const instance = Object.create(PiperPlus.prototype);
    instance._initialized = true;
    instance._warmupPromise = null;
    instance._config = makeConfigJson();
    // synthesize() internally validates; undefined must not throw at the
    // validation step. We cannot drive the full pipeline here because the
    // phonemizer is not mocked, but we can verify that `throw` is not hit
    // purely from the validation code path.
    const fakePipeline = () => {
      throw new Error('pipeline-not-reached');
    };
    instance._detectLanguage = () => 'en';
    instance._textToPhonemeIds = fakePipeline;

    await assert.rejects(
      () => instance.synthesize('hello', { styleVector: undefined }),
      /pipeline-not-reached/,
      'validation must pass, then fail later in _textToPhonemeIds',
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: _infer feeds construction — verify that style_vector +
// style_vector_mask end up in the ONNX feed dict.
// ---------------------------------------------------------------------------

describe('PiperPlus _infer style_vector feeds', () => {
  beforeEach(() => installGlobalMocks({ hasStyleVectorInput: true }));
  afterEach(() => restoreGlobalMocks());

  function makeInstance() {
    return {
      _ort: globalThis.ort,
      _session: {
        inputNames: ['input', 'input_lengths', 'scales', 'style_vector', 'style_vector_mask'],
        run: async (feeds) => {
          capturedFeeds.push(feeds);
          return {
            output: { data: new Float32Array(22050), dims: [1, 22050] },
            durations: { data: new Float32Array(3), dims: [1, 3] },
          };
        },
      },
      _config: makeConfigJson(),
      _sessionManager: null,
    };
  }

  it('sends zeros + mask=0 when styleVector is omitted', async () => {
    const { PiperPlus } = await import('../../src/index.js');
    const instance = makeInstance();
    await PiperPlus.prototype._infer.call(
      instance,
      [1, 2, 3],
      null,
      { noiseScale: 0.667, lengthScale: 1.0, noiseW: 0.8, language: 'en' },
    );
    assert.equal(capturedFeeds.length, 1);
    const feeds = capturedFeeds[0];
    assert.ok(feeds.style_vector, 'style_vector must be attached');
    assert.ok(feeds.style_vector_mask, 'style_vector_mask must be attached');
    assert.deepEqual(feeds.style_vector.dims, [1, STYLE_VECTOR_DIM]);
    const isZeroFilled = Array.from(feeds.style_vector.data).every((v) => v === 0);
    assert.ok(isZeroFilled, 'zero-fill when styleVector is omitted');
    assert.equal(feeds.style_vector_mask.data[0], 0n, 'mask=0 when styleVector is omitted');
  });

  it('sends user vector + mask=1 when styleVector is provided', async () => {
    const { PiperPlus } = await import('../../src/index.js');
    const instance = makeInstance();
    const styleVector = new Float32Array(STYLE_VECTOR_DIM);
    styleVector[0] = 0.5;
    styleVector[STYLE_VECTOR_DIM - 1] = -0.25;

    await PiperPlus.prototype._infer.call(
      instance,
      [1, 2, 3],
      null,
      { noiseScale: 0.667, lengthScale: 1.0, noiseW: 0.8, language: 'en', styleVector },
    );
    const feeds = capturedFeeds[0];
    assert.equal(feeds.style_vector.data[0], 0.5);
    assert.equal(feeds.style_vector.data[STYLE_VECTOR_DIM - 1], -0.25);
    assert.equal(feeds.style_vector_mask.data[0], 1n, 'mask=1 when styleVector is provided');
  });

  it('raises an error when styleVector length != configured dim', async () => {
    const { PiperPlus } = await import('../../src/index.js');
    const instance = makeInstance();
    const badVector = new Float32Array(64); // != STYLE_VECTOR_DIM

    await assert.rejects(
      () =>
        PiperPlus.prototype._infer.call(
          instance,
          [1, 2, 3],
          null,
          { noiseScale: 0.667, lengthScale: 1.0, noiseW: 0.8, language: 'en', styleVector: badVector },
        ),
      /styleVector length 64 != model style_vector_dim 256/,
      'must raise length-mismatch error',
    );
  });

  it('omits style_vector feeds when model lacks the input', async () => {
    restoreGlobalMocks();
    installGlobalMocks({ hasStyleVectorInput: false });
    const { PiperPlus } = await import('../../src/index.js');
    const instance = {
      _ort: globalThis.ort,
      _session: {
        inputNames: ['input', 'input_lengths', 'scales'], // no style_vector
        run: async (feeds) => {
          capturedFeeds.push(feeds);
          return {
            output: { data: new Float32Array(22050), dims: [1, 22050] },
            durations: { data: new Float32Array(3), dims: [1, 3] },
          };
        },
      },
      _config: makeConfigJson(),
    };
    await PiperPlus.prototype._infer.call(
      instance,
      [1, 2, 3],
      null,
      { noiseScale: 0.667, lengthScale: 1.0, noiseW: 0.8, language: 'en' },
    );
    const feeds = capturedFeeds[0];
    assert.equal(
      feeds.style_vector,
      undefined,
      'style_vector must not be attached when the model lacks the input',
    );
    assert.equal(
      feeds.style_vector_mask,
      undefined,
      'style_vector_mask must not be attached when the model lacks the input',
    );
  });
});
