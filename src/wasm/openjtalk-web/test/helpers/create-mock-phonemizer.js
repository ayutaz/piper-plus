/**
 * テスト用モック G2P を生成する。
 * G2P クラスの公開インターフェースを再現し、
 * 呼び出し履歴をキャプチャする。
 */

/**
 * Default stub implementations matching G2P behaviour.
 * Each returns a deterministic value suitable for snapshot-free assertions.
 */
const DEFAULT_STUBS = {
  /** @param {string} _text */
  detectLanguage: (_text) => 'ja',

  /**
   * @param {string} _text
   * @param {Record<string, number[]>} _phonemeIdMap
   * @param {Object} [_options]
   * @returns {{ phonemeIds: number[], prosodyFlat: number[]|null }}
   */
  encode: (_text, _phonemeIdMap, _options) => ({
    phonemeIds: [1, 5, 2],
    prosodyFlat: null,
  }),

  dispose: () => {},
};

/**
 * Tracked method names whose call arguments are recorded in `g2p.calls`.
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
 * Create a mock G2P that mirrors the G2P public API used by PiperPlus.
 *
 * Every public method is tracked -- call arguments are pushed to
 * `g2p.calls.<methodName>` as arrays so tests can assert on
 * invocation count and parameter values.
 *
 * @param {Object} [options={}] - Per-method overrides. Each key is a method
 *   name from G2P; the value is a replacement function.
 *   Methods not listed fall back to sensible defaults.
 *
 * @returns {{
 *   calls: Record<string, Array<Array<*>>>,
 *   detectLanguage: Function,
 *   encode: Function,
 *   dispose: Function,
 *   reset: Function,
 * }}
 *
 * @example
 * // Basic usage with defaults
 * const g2p = createMockG2P();
 * const lang = g2p.detectLanguage('hello');
 * assert.strictEqual(lang, 'ja');
 * assert.strictEqual(g2p.calls.detectLanguage.length, 1);
 *
 * @example
 * // Override specific methods
 * const g2p = createMockG2P({
 *   detectLanguage: () => 'en',
 *   encode: (text, map, opts) => ({ phonemeIds: [1, 10, 2], prosodyFlat: null }),
 * });
 */
export function createMockG2P(options = {}) {
  const calls = createCallsMap();

  const g2p = {
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
    },
  };

  // Wire up each method: use the caller-supplied override or the default stub,
  // then wrap with call tracking.
  for (const name of TRACKED_METHODS) {
    const impl = options[name] || DEFAULT_STUBS[name];
    g2p[name] = wrapWithTracking(name, impl, calls);
  }

  return g2p;
}

/**
 * Alias for backwards compatibility with tests that imported createMockPhonemizer.
 * @deprecated Use createMockG2P instead.
 */
export const createMockPhonemizer = createMockG2P;
