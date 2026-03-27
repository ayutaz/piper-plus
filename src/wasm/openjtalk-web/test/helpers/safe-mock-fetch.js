/**
 * safe-mock-fetch.js -- テスト用の安全な fetch モック。
 *
 * afterEach での復元を保証し、テスト失敗時にもグローバル状態を汚染しない。
 *
 * Usage:
 *   import { installSafeFetch } from './helpers/safe-mock-fetch.js';
 *
 *   const { restore, calls } = installSafeFetch({
 *     'https://example.com/config.json': {
 *       ok: true,
 *       json: () => ({ num_speakers: 1 }),
 *     },
 *     'https://example.com/model.onnx': {
 *       ok: true,
 *       arrayBuffer: () => new ArrayBuffer(100),
 *     },
 *   });
 *
 *   // ... run test ...
 *
 *   restore(); // call in afterEach -- idempotent, safe to call multiple times
 */

// ---------------------------------------------------------------------------
// Internal: glob-style pattern matching
// ---------------------------------------------------------------------------

/**
 * Convert a glob pattern with `*` wildcards into a RegExp.
 * Each `*` matches one or more non-slash characters (greedy).
 *
 * @param {string} glob - URL pattern, e.g. 'https://huggingface.co/* /resolve/*'
 * @returns {RegExp}
 */
function globToRegExp(glob) {
  // Escape regex-special characters except `*`
  const escaped = glob.replace(/([.+?^${}()|[\]\\])/g, '\\$1');
  // Replace `*` with `.+` (one or more chars, greedy)
  const pattern = escaped.replace(/\*/g, '.+');
  return new RegExp('^' + pattern + '$');
}

/**
 * Test whether a URL matches a route key.
 * - Exact string match is tried first.
 * - If the key contains `*`, glob matching is used.
 *
 * @param {string} routeKey
 * @param {string} url
 * @returns {boolean}
 */
function matchRoute(routeKey, url) {
  if (routeKey === url) return true;
  if (routeKey.includes('*')) {
    return globToRegExp(routeKey).test(url);
  }
  return false;
}

// ---------------------------------------------------------------------------
// Internal: build a Response-like object from a route handler
// ---------------------------------------------------------------------------

/**
 * Build a minimal Response-shaped object from a route handler definition.
 *
 * @param {Object} handler - Route handler with optional ok, status, json, arrayBuffer, text, headers fields.
 * @returns {Object} Response-like object consumable by production code.
 */
function buildResponse(handler) {
  const ok = handler.ok ?? true;
  const status = handler.status ?? (ok ? 200 : 500);
  const statusText = handler.statusText ?? (ok ? 'OK' : 'Error');

  return {
    ok,
    status,
    statusText,
    headers: handler.headers ?? new Map(),
    json: handler.json
      ? () => Promise.resolve(handler.json())
      : () => Promise.reject(new Error('No json handler for this route')),
    arrayBuffer: handler.arrayBuffer
      ? () => Promise.resolve(handler.arrayBuffer())
      : () => Promise.resolve(new ArrayBuffer(0)),
    text: handler.text
      ? () => Promise.resolve(handler.text())
      : () => Promise.resolve(''),
    body: null,
  };
}

/**
 * Build a 404 Not Found response for unmatched URLs.
 *
 * @param {string} url - The unmatched URL (included in statusText for debugging).
 * @returns {Object} Response-like 404 object.
 */
function build404(url) {
  return {
    ok: false,
    status: 404,
    statusText: `Not Found: ${url}`,
    headers: new Map(),
    json: () => Promise.reject(new Error(`404: ${url}`)),
    arrayBuffer: () => Promise.reject(new Error(`404: ${url}`)),
    text: () => Promise.resolve('Not Found'),
    body: null,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

// Install a safe, route-based fetch mock on globalThis.fetch.
//
// The returned restore() function is idempotent -- calling it multiple
// times (e.g. both inside a test and in afterEach) is harmless.
//
// Route matching (insertion order, first match wins):
//   - Exact match:  'https://example.com/file.json'
//   - Glob match:   'https://huggingface.co/STAR/resolve/STAR'
//     (where STAR is *, each matches one or more characters)
//
// Route handler shape:
//   { ok, status, statusText, headers, json, arrayBuffer, text }
//   All fields optional. json/arrayBuffer/text are sync functions.
//
// Error simulation -- _error causes fetch() to reject:
//   { _error: new TypeError('Failed to fetch') }
//
/**
 * @param {Object<string, Object>} routes - URL pattern to handler mapping.
 * @returns {{ restore: () => void, calls: Array<{url: string, options: (Object|undefined)}>, fetchMock: Function }}
 */
export function installSafeFetch(routes = {}) {
  // Snapshot the original -- may be undefined in Node.js without --experimental-fetch
  const original = globalThis.fetch;
  let restored = false;

  /** @type {Array<{ url: string, options: Object|undefined }>} */
  const calls = [];

  // Pre-compute route entries once (preserves insertion order)
  const routeEntries = Object.entries(routes);

  /**
   * The mock fetch function installed on globalThis.
   *
   * @param {string|URL|Request} input
   * @param {Object} [options]
   * @returns {Promise<Object>}
   */
  async function fetchMock(input, options) {
    const url = typeof input === 'string' ? input : String(input);
    calls.push({ url, options });

    for (const [pattern, handler] of routeEntries) {
      if (matchRoute(pattern, url)) {
        // Error simulation: reject the promise
        if (handler._error) {
          throw handler._error;
        }
        return buildResponse(handler);
      }
    }

    // Default: 404 for unmatched URLs
    return build404(url);
  }

  // Install
  globalThis.fetch = fetchMock;

  /**
   * Restore `globalThis.fetch` to its original value.
   * Safe to call multiple times -- only the first call has an effect.
   */
  function restore() {
    if (restored) return;
    restored = true;

    if (original === undefined) {
      delete globalThis.fetch;
    } else {
      globalThis.fetch = original;
    }
  }

  return { fetchMock, restore, calls };
}
