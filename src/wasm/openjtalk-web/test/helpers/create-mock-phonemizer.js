/**
 * テスト用モック Phonemizer を生成する。
 * SimpleUnifiedPhonemizer の公開インターフェースを再現し、
 * 呼び出し履歴をキャプチャする。
 */

/**
 * Default stub implementations matching SimpleUnifiedPhonemizer behaviour.
 * Each returns a deterministic value suitable for snapshot-free assertions.
 */
const DEFAULT_STUBS = {
  /** @param {string} _text */
  detectLanguage: (_text) => 'ja',

  /**
   * @param {string} _text
   * @param {string|null} _lang
   * @returns {Promise<string>}
   */
  textToPhonemes: async (_text, _lang) => ({
    phonemeIds: [1, 0, 4, 0, 2],
    prosodyFeatures: null,
  }),

  /**
   * @param {string|Array} _phonemeStr
   * @param {string} _language
   * @returns {Array<string>}
   */
  extractPhonemes: (_phonemeStr, _language) => ['^', 'k', 'o', 'N', '$'],

  /** @param {string} _language */
  getPhonemeIdMap: (_language) => null,

  /** @param {Object} _phonemeIdMap */
  setPhonemeIdMap: (_phonemeIdMap) => {},

  /** @param {Object} _config */
  initialize: async (_config) => {},

  dispose: () => {},
};

/**
 * Tracked method names whose call arguments are recorded in `phonemizer.calls`.
 * @type {ReadonlyArray<string>}
 */
const TRACKED_METHODS = Object.keys(DEFAULT_STUBS);

/**
 * Create a fresh call-tracking map.
 * @returns {Record<string, Array<Array<*>>>}
 */
function createCallsMap() {
  /** @type {Record<string, Array<Array<*>>>} */
  const calls = {};
  for (const name of TRACKED_METHODS) {
    calls[name] = [];
  }
  return calls;
}

/**
 * Wrap a stub function so that every invocation is recorded.
 *
 * @param {string} methodName - Name used as key in the calls map.
 * @param {Function} impl     - The actual (or overridden) implementation.
 * @param {Record<string, Array<Array<*>>>} calls - Shared calls map.
 * @returns {Function} Wrapped function that records arguments before delegating.
 */
function wrapWithTracking(methodName, impl, calls) {
  return function (...args) {
    calls[methodName].push(args);
    return impl.apply(this, args);
  };
}

/**
 * Create a mock phonemizer that mirrors the SimpleUnifiedPhonemizer public API.
 *
 * Every public method is tracked -- call arguments are pushed to
 * `phonemizer.calls.<methodName>` as arrays so tests can assert on
 * invocation count and parameter values.
 *
 * @param {Object} [options={}] - Per-method overrides. Each key is a method
 *   name from SimpleUnifiedPhonemizer; the value is a replacement function.
 *   Methods not listed fall back to sensible defaults (e.g. `detectLanguage`
 *   returns `'ja'`).
 *
 * @returns {{
 *   initialized: boolean,
 *   phonemeIdMap: Object|null,
 *   calls: Record<string, Array<Array<*>>>,
 *   detectLanguage: Function,
 *   textToPhonemes: Function,
 *   extractPhonemes: Function,
 *   getPhonemeIdMap: Function,
 *   setPhonemeIdMap: Function,
 *   initialize: Function,
 *   dispose: Function,
 *   reset: Function,
 * }}
 *
 * @example
 * // Basic usage with defaults
 * const phonemizer = createMockPhonemizer();
 * const lang = phonemizer.detectLanguage('hello');
 * assert.strictEqual(lang, 'ja');
 * assert.strictEqual(phonemizer.calls.detectLanguage.length, 1);
 *
 * @example
 * // Override specific methods
 * const phonemizer = createMockPhonemizer({
 *   detectLanguage: () => 'en',
 *   textToPhonemes: async (text, lang) => 'h eh l ow',
 * });
 *
 * @example
 * // Simulate errors
 * const phonemizer = createMockPhonemizer({
 *   textToPhonemes: async () => { throw new Error('phonemize failed'); },
 * });
 */
export function createMockPhonemizer(options = {}) {
  const calls = createCallsMap();

  const phonemizer = {
    /** @type {boolean} Mirrors SimpleUnifiedPhonemizer.initialized */
    initialized: false,

    /** @type {Object|null} Mirrors SimpleUnifiedPhonemizer.phonemeIdMap */
    phonemeIdMap: null,

    /**
     * Call-tracking map.
     * Keys are method names; values are arrays of argument-arrays.
     * @type {Record<string, Array<Array<*>>>}
     */
    calls,

    /**
     * Reset all call tracking histories.
     * Useful between sub-tests when reusing the same mock instance.
     */
    reset() {
      for (const name of TRACKED_METHODS) {
        calls[name] = [];
      }
      phonemizer.initialized = false;
      phonemizer.phonemeIdMap = null;
    },
  };

  // Wire up each method: use the caller-supplied override or the default stub,
  // then wrap with call tracking.
  for (const name of TRACKED_METHODS) {
    const impl = options[name] || DEFAULT_STUBS[name];
    phonemizer[name] = wrapWithTracking(name, impl, calls);
  }

  // initialize / setPhonemeIdMap have side-effects on instance state.
  // Wrap them so the mock's own `initialized` and `phonemeIdMap` stay in sync.
  const userInitialize = options.initialize;
  const originalInitialize = phonemizer.initialize;
  phonemizer.initialize = async function (...args) {
    const result = await originalInitialize.apply(this, args);
    // Only flip initialized when the user did not supply a custom impl
    // (a custom impl is responsible for its own semantics).
    if (!userInitialize) {
      phonemizer.initialized = true;
    }
    return result;
  };

  const userSetMap = options.setPhonemeIdMap;
  const originalSetMap = phonemizer.setPhonemeIdMap;
  phonemizer.setPhonemeIdMap = function (...args) {
    const result = originalSetMap.apply(this, args);
    if (!userSetMap) {
      phonemizer.phonemeIdMap = args[0];
    }
    return result;
  };

  const userDispose = options.dispose;
  const originalDispose = phonemizer.dispose;
  phonemizer.dispose = function (...args) {
    const result = originalDispose.apply(this, args);
    if (!userDispose) {
      phonemizer.initialized = false;
    }
    return result;
  };

  return phonemizer;
}
