/**
 * Shared mock factories for ONNX Runtime (ort) in Node.js tests.
 *
 * Provides reusable mocks that mirror the onnxruntime-web API surface
 * used by PiperPlus (InferenceSession.create, session.run, Tensor).
 *
 * Usage:
 *   import { createMockOrt, createMockSession } from '../helpers/create-mock-ort.js';
 *   globalThis.ort = createMockOrt();
 *
 * @module test/helpers/create-mock-ort
 */

// ---------------------------------------------------------------------------
// Default constants
// ---------------------------------------------------------------------------

/** Default number of audio samples returned by mock session.run(). */
const DEFAULT_NUM_SAMPLES = 22050;

// ---------------------------------------------------------------------------
// MockTensor
// ---------------------------------------------------------------------------

/**
 * Lightweight mock of ort.Tensor.
 * Stores type, data, and dims exactly as the real Tensor constructor does.
 */
class MockTensor {
  /**
   * @param {string} type - Data type (e.g. 'int64', 'float32').
   * @param {TypedArray} data - Tensor data.
   * @param {number[]} dims - Shape dimensions.
   */
  constructor(type, data, dims) {
    this.type = type;
    this.data = data;
    this.dims = dims;
  }
}

// ---------------------------------------------------------------------------
// createMockSession
// ---------------------------------------------------------------------------

/**
 * テスト用モック ONNX セッションを生成する。
 *
 * session.run(feeds) の呼び出しを記録し、戻り値をカスタマイズできる。
 * session.release() の呼び出しも記録される。
 *
 * @param {Object} [options]
 * @param {Float32Array} [options.outputAudio] - run() が返す音声データ。
 *   省略時は DEFAULT_NUM_SAMPLES 個のゼロ埋め Float32Array。
 * @param {string} [options.outputKey='output'] - 出力テンソルのキー名。
 * @param {Function} [options.runHandler] - run(feeds) のカスタムハンドラ。
 *   指定すると outputAudio/outputKey より優先される。
 *   feeds を受け取り、結果オブジェクトを返す (async 可)。
 * @param {Error} [options.runError] - run() で投げるエラー。
 *   指定すると runHandler/outputAudio より優先される。
 * @returns {{
 *   run: Function,
 *   release: Function,
 *   calls: Array<{feeds: Object}>,
 *   releaseCount: number,
 *   inputNames: string[],
 *   outputNames: string[],
 * }}
 *
 * @example
 * const session = createMockSession({ outputAudio: new Float32Array([0.1, -0.2]) });
 * const result = await session.run({ input: tensor });
 * assert.equal(session.calls.length, 1);
 * assert.deepEqual(session.calls[0].feeds, { input: tensor });
 */
export function createMockSession(options = {}) {
  const {
    outputAudio = new Float32Array(DEFAULT_NUM_SAMPLES),
    outputKey = 'output',
    runHandler = null,
    runError = null,
  } = options;

  /** @type {Array<{feeds: Object}>} */
  const calls = [];

  /** @type {number} */
  let releaseCount = 0;

  /**
   * Mock run() that records feeds and returns configurable output.
   * @param {Object} feeds - ONNX input feeds.
   * @returns {Promise<Object>} Output tensors keyed by name.
   */
  async function run(feeds) {
    calls.push({ feeds });

    if (runError) {
      throw runError;
    }

    if (runHandler) {
      return runHandler(feeds);
    }

    return {
      [outputKey]: {
        data: outputAudio,
        cpuData: outputAudio,
        dims: [1, outputAudio.length],
      },
    };
  }

  /**
   * Mock release() that increments the release counter.
   */
  function release() {
    releaseCount += 1;
  }

  return {
    run,
    release,
    /** Captured run() invocations. Each entry has a `feeds` property. */
    get calls() { return calls; },
    /** Number of times release() was called. */
    get releaseCount() { return releaseCount; },
    /** Standard ONNX session metadata. */
    inputNames: ['input', 'input_lengths', 'scales'],
    outputNames: [outputKey],
  };
}

// ---------------------------------------------------------------------------
// createMockOrt
// ---------------------------------------------------------------------------

/**
 * テスト用モック ONNX Runtime (ort) を生成する。
 * globalThis.ort に設定して使用する。
 *
 * InferenceSession.create() はモックセッションを返す。
 * ort.Tensor はコンストラクタで type/data/dims を保存する軽量クラス。
 *
 * @param {Object} [options]
 * @param {Float32Array} [options.outputAudio] - session.run() が返す音声データ。
 *   createMockSession に委譲される。
 * @param {string} [options.outputKey='output'] - 出力テンソルのキー名。
 * @param {Function} [options.runHandler] - session.run() のカスタムハンドラ。
 * @param {Error} [options.runError] - session.run() で投げるエラー。
 * @param {Error} [options.createError] - InferenceSession.create() で投げるエラー。
 * @param {Function} [options.createHandler] - InferenceSession.create() のカスタムハンドラ。
 *   (modelData, sessionOptions) を受け取り、セッションオブジェクトを返す (async 可)。
 *   指定すると他のセッション関連オプションは無視される。
 * @param {string[]} [options.supportedProviders] - create() が成功する
 *   executionProvider 名のリスト。指定すると、リストにないプロバイダーで
 *   create() がエラーを投げる (WebGPUSessionManager テスト用)。
 * @returns {{
 *   InferenceSession: { create: Function },
 *   Tensor: typeof MockTensor,
 *   sessions: Array,
 *   createCalls: Array<{modelData: *, options: Object}>,
 * }}
 *
 * @example
 * // Basic usage — install as globalThis.ort
 * globalThis.ort = createMockOrt();
 * const session = await ort.InferenceSession.create('model.onnx', {});
 * const result = await session.run(feeds);
 *
 * @example
 * // With custom audio output
 * const ort = createMockOrt({ outputAudio: new Float32Array([0.5, -0.5]) });
 *
 * @example
 * // Error simulation
 * const ort = createMockOrt({ runError: new Error('inference failed') });
 *
 * @example
 * // WebGPUSessionManager fallback testing
 * const ort = createMockOrt({ supportedProviders: ['wasm'] });
 */
export function createMockOrt(options = {}) {
  const {
    outputAudio,
    outputKey,
    runHandler,
    runError,
    createError = null,
    createHandler = null,
    supportedProviders = null,
  } = options;

  /** @type {Array} All sessions created by InferenceSession.create(). */
  const sessions = [];

  /** @type {Array<{modelData: *, options: Object}>} */
  const createCalls = [];

  const InferenceSession = {
    /**
     * Mock InferenceSession.create().
     * @param {*} modelData - Model path, URL, or ArrayBuffer.
     * @param {Object} [sessionOptions] - Session configuration options.
     * @returns {Promise<Object>} Mock inference session.
     */
    create: async (modelData, sessionOptions = {}) => {
      createCalls.push({ modelData, options: sessionOptions });

      if (createError) {
        throw createError;
      }

      // Provider filtering for WebGPUSessionManager tests
      if (supportedProviders !== null) {
        const providers = sessionOptions.executionProviders || ['wasm'];
        const provider = providers[0];
        const providerName = typeof provider === 'string' ? provider : provider.name;
        if (!supportedProviders.includes(providerName)) {
          throw new Error(`EP ${providerName} not available`);
        }
      }

      if (createHandler) {
        const session = await createHandler(modelData, sessionOptions);
        sessions.push(session);
        return session;
      }

      // Build session options to pass through to createMockSession
      const sessionOpts = {};
      if (outputAudio !== undefined) sessionOpts.outputAudio = outputAudio;
      if (outputKey !== undefined) sessionOpts.outputKey = outputKey;
      if (runHandler !== undefined) sessionOpts.runHandler = runHandler;
      if (runError !== undefined) sessionOpts.runError = runError;

      const session = createMockSession(sessionOpts);
      sessions.push(session);
      return session;
    },
  };

  return {
    InferenceSession,
    Tensor: MockTensor,
    /** All sessions created via InferenceSession.create(). */
    get sessions() { return sessions; },
    /** Captured InferenceSession.create() invocations. */
    get createCalls() { return createCalls; },
  };
}
