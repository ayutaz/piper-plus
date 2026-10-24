/**
 * The bundled CMU Pronouncing Dictionary (cmudict 0.7b), loaded on demand.
 *
 * `data/cmudict_data.json` (~3.7 MB, ~123k words) is a byte copy of the
 * canonical `src/rust/piper-plus-g2p/data/cmudict_data.json` that the Rust,
 * C++, Go and Swift runtimes read (gate: `scripts/check_cmudict_mirrors.py`).
 * It maps lowercase words to ARPAbet strings: `{"hello": "HH AH0 L OW1"}`.
 *
 * Nothing is read when the package is imported. The dictionary is loaded
 *
 * - asynchronously by {@link loadCmuDict}, a dynamic JSON module import that
 *   works in browsers, bundlers and Node (`G2P.create()` and
 *   `EnglishG2P.initialize()` call it), or
 * - synchronously by {@link getCmuDictSync} where the file system can be read
 *   synchronously (Node, through `process.getBuiltinModule`), so an
 *   uninitialised `EnglishG2P` keeps working there.
 *
 * Both share one cache, so the 3.7 MB are parsed at most once per realm.
 *
 * @module @piper-plus/g2p/en/cmudict
 */

/** @type {Map<string, string>|null} */
let cache = null;
/** @type {Promise<Map<string, string>>|null} */
let pending = null;

/**
 * Path of the bundled file relative to this module. Kept in a variable so
 * bundlers do not mistake `new URL(..., import.meta.url)` for an asset to
 * copy; the dynamic import in loadCmuDict() is what they bundle.
 */
const DICT_PATH = "../../data/cmudict_data.json";

/**
 * Turn the parsed JSON object into a Map. A Map has no prototype keys, so a
 * word like "constructor" or "toString" is never read from Object.prototype.
 *
 * @param {unknown} data
 * @returns {Map<string, string>}
 */
export function toCmuDictMap(data) {
  if (data instanceof Map) {
    return data;
  }
  if (!data || typeof data !== "object") {
    throw new TypeError("CMU dictionary must be an object mapping words to ARPAbet strings");
  }
  const map = new Map();
  for (const [word, arpa] of Object.entries(data)) {
    if (typeof arpa === "string") {
      map.set(word, arpa);
    }
  }
  return map;
}

/**
 * Load the bundled CMU dictionary. Resolves to the same Map on every call.
 *
 * @returns {Promise<Map<string, string>>}
 */
export function loadCmuDict() {
  if (cache) {
    return Promise.resolve(cache);
  }
  if (!pending) {
    pending = import("../../data/cmudict_data.json", { with: { type: "json" } }).then(
      (mod) => {
        cache ??= toCmuDictMap(mod.default);
        return cache;
      },
      (error) => {
        pending = null;
        throw error;
      }
    );
  }
  return pending;
}

/**
 * The CMU dictionary if it can be had synchronously: already loaded, or
 * readable from the package files right now (Node). Otherwise null.
 *
 * @returns {Map<string, string>|null}
 */
export function getCmuDictSync() {
  if (cache) {
    return cache;
  }
  const getBuiltin = globalThis.process?.getBuiltinModule;
  if (typeof getBuiltin !== "function") {
    return null;
  }
  let url;
  try {
    url = new URL(DICT_PATH, import.meta.url);
  } catch {
    return null;
  }
  const fs = getBuiltin.call(globalThis.process, "node:fs");
  if (url.protocol !== "file:" || !fs || typeof fs.readFileSync !== "function") {
    return null;
  }
  cache = toCmuDictMap(JSON.parse(fs.readFileSync(url, "utf8")));
  return cache;
}

/**
 * Whether the bundled dictionary has been loaded in this realm.
 *
 * @returns {boolean}
 */
export function isCmuDictLoaded() {
  return cache !== null;
}
