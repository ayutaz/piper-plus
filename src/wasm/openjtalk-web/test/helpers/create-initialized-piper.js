/**
 * Shared test factory for creating initialized PiperPlus instances.
 *
 * Centralises ALL private-field access into a single location so that
 * individual test files never touch underscored properties directly.
 * When PiperPlus internals change, only this file needs updating.
 *
 * Self-contained -- no imports from other test helpers to avoid circular deps.
 *
 * @module test/helpers/create-initialized-piper
 */

// ---------------------------------------------------------------------------
// TDD skip guard: PiperPlus import
// ---------------------------------------------------------------------------

/** @type {typeof import('../../src/index.js').PiperPlus | null} */
let PiperPlus = null;

try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
} catch {
  // Module not yet buildable -- callers should check for null return.
}

// ---------------------------------------------------------------------------
// Minimal ort mock (Tensor constructor)
// ---------------------------------------------------------------------------

/**
 * A minimal onnxruntime-web mock that provides only the Tensor constructor
 * needed by PiperPlus._infer().
 *
 * @returns {object} ort-compatible mock
 */
function createOrtMock() {
  return {
    Tensor: class MockTensor {
      /**
       * @param {string} type
       * @param {TypedArray} data
       * @param {number[]} dims
       */
      constructor(type, data, dims) {
        this.type = type;
        this.data = data;
        this.dims = dims;
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Default config
// ---------------------------------------------------------------------------

/**
 * Create a default config object matching a typical 6-language multilingual
 * model. Callers can spread overrides on top.
 *
 * @param {object} [overrides] - Properties to merge (shallow) into the config.
 * @returns {object} config.json-shaped object
 *
 * @example
 * const config = createDefaultConfig({ audio: { sample_rate: 44100 } });
 */
export function createDefaultConfig(overrides = {}) {
  return {
    audio: { sample_rate: 22050 },
    num_speakers: 1,
    num_languages: 6,
    phoneme_id_map: {
      _: [0],
      '^': [1],
      $: [2],
      ' ': [3],
      a: [4],
      i: [5],
      u: [6],
      e: [7],
      o: [8],
      k: [10],
      s: [11],
      t: [12],
      n: [13],
      h: [14],
      N: [15],
      ch: [16],
      w: [17],
      r: [18],
      '@': [19],
      l: [20],
      oU: [21],
    },
    inference: {
      noise_scale: 0.667,
      length_scale: 1.0,
      noise_w: 0.8,
    },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default mock builders
// ---------------------------------------------------------------------------

/**
 * Create a default G2P mock with all methods required by PiperPlus.
 *
 * Returned methods are plain functions (not node:test mocks) so this helper
 * stays self-contained. Tests that need call-tracking can wrap individual
 * methods with `mock.fn()` via the overrides parameter.
 *
 * @param {object} [overrides] - Per-method replacements.
 * @returns {object} G2P mock
 */
function buildG2PMock(overrides = {}) {
  return {
    detectLanguage: overrides.detectLanguage || (() => 'ja'),
    encode: overrides.encode || (() => ({ phonemeIds: [1, 7, 2], prosodyFlat: null })),
    dispose: overrides.dispose || (() => {}),
  };
}

/**
 * Create a default ONNX session mock.
 *
 * By default, `run()` returns a Float32Array of 100 samples (silence).
 *
 * @param {object} [overrides]
 * @param {Function} [overrides.run] - Custom session.run implementation.
 * @param {Function} [overrides.release] - Custom session.release implementation.
 * @returns {object} session mock
 */
function buildSessionMock(overrides = {}) {
  const defaultRun = async () => ({
    output: { data: new Float32Array(100), dims: [1, 100] },
  });
  return {
    run: overrides.run || defaultRun,
    release: overrides.release || (() => {}),
  };
}

// ---------------------------------------------------------------------------
// Main factory
// ---------------------------------------------------------------------------

/**
 * Create an initialized PiperPlus instance for testing.
 *
 * Instead of each test file setting private fields (`_initialized`, `_config`,
 * `_session`, `_phonemizer`, `_ort`) independently, this factory centralises
 * that coupling in one place. When PiperPlus internals change, only this
 * function needs to be updated.
 *
 * Returns `null` if PiperPlus could not be imported (TDD red phase).
 *
 * @param {object} [options]
 * @param {object} [options.config]     - Custom config override (merged with defaults).
 * @param {object} [options.g2p]        - Custom G2P mock (per-method overrides).
 * @param {object} [options.session]    - Custom ONNX session mock (`{ run, release }`).
 * @param {object} [options.ort]        - Custom ort mock. Defaults to a minimal Tensor-only mock.
 * @returns {{ instance: InstanceType<typeof PiperPlus>, mocks: { g2p: object, session: object, config: object, ort: object } } | null}
 *
 * @example
 * // Basic usage -- all defaults
 * const result = createInitializedPiper();
 * if (!result) return; // TDD skip
 * const { instance, mocks } = result;
 * const audio = await instance.synthesize('hello');
 *
 * @example
 * // Custom session.run to capture feeds
 * let capturedFeeds = null;
 * const result = createInitializedPiper({
 *   session: {
 *     run: async (feeds) => {
 *       capturedFeeds = feeds;
 *       return { output: { data: new Float32Array(50), dims: [1, 50] } };
 *     },
 *   },
 * });
 *
 * @example
 * // Custom config with different sample rate
 * const result = createInitializedPiper({
 *   config: { audio: { sample_rate: 44100 } },
 * });
 */
export function createInitializedPiper(options = {}) {
  if (!PiperPlus) {
    return null;
  }

  const config = options.config
    ? createDefaultConfig(options.config)
    : createDefaultConfig();

  const g2p = buildG2PMock(options.g2p);
  const session = buildSessionMock(options.session);
  const ort = options.ort || createOrtMock();

  const instance = new PiperPlus();

  // Centralised private-field wiring -- mirrors what _init() does.
  // This is the ONLY place in the test suite that should touch these fields.
  instance._config = config;
  instance._g2p = g2p;
  instance._session = session;
  instance._ort = ort;
  instance._initialized = true;

  return {
    instance,
    mocks: {
      g2p,
      session,
      config,
      ort,
    },
  };
}
