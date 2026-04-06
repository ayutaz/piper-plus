/**
 * ModelManager — Download and cache ONNX models from HuggingFace.
 *
 * Provides automatic URL resolution for HuggingFace repository names,
 * shortcut aliases, progress tracking during download, and IndexedDB caching.
 */

const DB_NAME = 'piper-plus-models';
const STORE_NAME = 'models';
const DICT_STORE = 'dictionaries';
const DB_VERSION = 2;

const HUGGINGFACE_API_BASE = 'https://huggingface.co/api/models';
const HUGGINGFACE_RESOLVE_BASE = 'https://huggingface.co';

/**
 * Shortcut names that resolve to full HuggingFace repository identifiers.
 */
const MODEL_REGISTRY = {
  'tsukuyomi': 'ayousanz/piper-plus-tsukuyomi-chan',
  'tsukuyomi-chan': 'ayousanz/piper-plus-tsukuyomi-chan',
  'css10': 'ayousanz/piper-plus-css10-ja-6lang',
  'css10-ja': 'ayousanz/piper-plus-css10-ja-6lang',
  'base': 'ayousanz/piper-plus-base',
};

/**
 * Open (or create) the IndexedDB database used for model caching.
 *
 * @returns {Promise<IDBDatabase>}
 */
function openDatabase(dbName) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
      if (!db.objectStoreNames.contains(DICT_STORE)) {
        db.createObjectStore(DICT_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Wrap an IDBRequest in a Promise.
 *
 * @param {IDBRequest} request
 * @returns {Promise<*>}
 */
function wrapRequest(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Fetch a URL with progress tracking via ReadableStream.
 *
 * @param {string} url
 * @param {Function} [onProgress] - ({loaded, total, percentage}) => void
 * @returns {Promise<ArrayBuffer>}
 */
async function fetchWithProgress(url, onProgress) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
  }

  // If no progress callback or no readable body, fall back to simple arrayBuffer().
  if (!onProgress || !response.body) {
    return response.arrayBuffer();
  }

  const contentLength = response.headers.get('Content-Length');
  const total = contentLength ? parseInt(contentLength, 10) : 0;

  const reader = response.body.getReader();
  const chunks = [];
  let loaded = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    chunks.push(value);
    loaded += value.byteLength;

    const percentage = total > 0 ? Math.round((loaded / total) * 100) : 0;
    onProgress({ loaded, total, percentage });
  }

  // Merge all chunks into a single ArrayBuffer.
  const merged = new Uint8Array(loaded);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }

  return merged.buffer;
}

/**
 * Query the HuggingFace API for repository metadata and resolve the ONNX
 * model filename and its companion config filename from the siblings list.
 *
 * Config resolution order:
 *   1. Sidecar: `{onnxFilename}.json` (e.g. `model.onnx.json`)
 *   2. Fallback: `config.json`
 *
 * @param {string} repoName - e.g. "ayousanz/piper-plus-css10-ja-6lang"
 * @returns {Promise<{onnxFilename: string, configFilename: string}>}
 */
async function resolveModelFiles(repoName) {
  const apiUrl = `${HUGGINGFACE_API_BASE}/${repoName}`;
  const response = await fetch(apiUrl);
  if (!response.ok) {
    throw new Error(
      `Failed to query HuggingFace API for "${repoName}": ${response.status} ${response.statusText}`
    );
  }

  const metadata = await response.json();
  const siblings = metadata.siblings || [];
  const filenames = siblings.map((s) => s.rfilename);
  const onnxFiles = filenames.filter((name) => name.endsWith('.onnx'));

  if (onnxFiles.length === 0) {
    throw new Error(`No .onnx file found in repository "${repoName}"`);
  }

  // If multiple ONNX files exist, prefer one with "fp16" in the name.
  const fp16File = onnxFiles.find((name) => name.includes('fp16'));
  const onnxFilename = fp16File || onnxFiles[0];

  // Resolve config: prefer sidecar {onnx}.json, fall back to config.json.
  const sidecarConfig = `${onnxFilename}.json`;
  let configFilename;
  if (filenames.includes(sidecarConfig)) {
    configFilename = sidecarConfig;
  } else if (filenames.includes('config.json')) {
    configFilename = 'config.json';
  } else {
    throw new Error(
      `No config file found in repository "${repoName}"; expected "${sidecarConfig}" or "config.json"`
    );
  }

  return { onnxFilename, configFilename };
}

export class ModelManager {
  /**
   * @param {Object} [options]
   * @param {string} [options.cachePrefix='piper-plus-models'] - IndexedDB database name
   * @param {boolean} [options.verifyOnCacheHit=false] - Re-verify SHA-256 on cache retrieval
   */
  constructor(options = {}) {
    this._dbName = options.cachePrefix || DB_NAME;
    this._db = null;
    this._verifyOnCacheHit = options.verifyOnCacheHit || false;
  }

  /**
   * Lazily open the IndexedDB database, returning the cached handle on
   * subsequent calls.
   *
   * @returns {Promise<IDBDatabase>}
   */
  async _getDb() {
    if (!this._db) {
      this._db = await openDatabase(this._dbName);
    }
    return this._db;
  }

  /**
   * Compute the SHA-256 hex digest of an ArrayBuffer.
   *
   * Returns null when crypto.subtle is unavailable (e.g. insecure HTTP
   * context) so callers can degrade gracefully.
   *
   * @param {ArrayBuffer} arrayBuffer
   * @returns {Promise<string|null>} - Lowercase hex string, or null
   */
  async _computeSha256(arrayBuffer) {
    if (typeof globalThis.crypto === 'undefined' ||
        !globalThis.crypto.subtle ||
        typeof globalThis.crypto.subtle.digest !== 'function') {
      return null;
    }
    try {
      const hashBuffer = await globalThis.crypto.subtle.digest('SHA-256', arrayBuffer);
      const hashArray = new Uint8Array(hashBuffer);
      return Array.from(hashArray).map(b => b.toString(16).padStart(2, '0')).join('');
    } catch {
      return null;
    }
  }

  /**
   * Resolve a model identifier to concrete URLs for the ONNX model and its
   * companion config JSON.
   *
   * Accepted formats:
   *   - Registry shortcut: "css10"
   *   - HuggingFace repo:  "ayousanz/piper-plus-css10-ja-6lang"
   *   - Direct URL:        "https://example.com/model.onnx"
   *
   * @param {string} modelNameOrUrl
   * @returns {Promise<{modelUrl: string, configUrl: string, configFallbackUrl: string|null, cacheKey: string}>}
   */
  async _resolveUrls(modelNameOrUrl) {
    // Direct URL.
    if (/^https?:\/\//i.test(modelNameOrUrl)) {
      const modelUrl = modelNameOrUrl;
      const configUrl = modelUrl + '.json';
      // Fallback: config.json in the same directory as the model.
      const lastSlash = modelUrl.lastIndexOf('/');
      const configFallbackUrl = lastSlash >= 0
        ? modelUrl.substring(0, lastSlash + 1) + 'config.json'
        : null;
      return { modelUrl, configUrl, configFallbackUrl, cacheKey: modelUrl };
    }

    // Registry shortcut.
    const repoName = MODEL_REGISTRY[modelNameOrUrl] || modelNameOrUrl;

    // Resolve ONNX and config filenames from the HuggingFace API.
    const { onnxFilename, configFilename } = await resolveModelFiles(repoName);

    const modelUrl = `${HUGGINGFACE_RESOLVE_BASE}/${repoName}/resolve/main/${onnxFilename}`;
    const configUrl = `${HUGGINGFACE_RESOLVE_BASE}/${repoName}/resolve/main/${configFilename}`;

    return { modelUrl, configUrl, configFallbackUrl: null, cacheKey: repoName };
  }

  /**
   * Resolve a model identifier to concrete URLs.
   *
   * This is the public entry point that delegates to {@link _resolveUrls}.
   *
   * @param {string} modelNameOrUrl - Registry shortcut, HuggingFace repo, or direct URL
   * @returns {Promise<{modelUrl: string, configUrl: string, configFallbackUrl: string|null, cacheKey: string}>}
   */
  async resolveUrls(modelNameOrUrl) {
    return this._resolveUrls(modelNameOrUrl);
  }

  /**
   * Load a model and its config, using the IndexedDB cache when available.
   *
   * @param {string} modelNameOrUrl - Registry shortcut, HuggingFace repo name, or direct URL
   * @param {Object} [options]
   * @param {Function} [options.onProgress] - ({loaded, total, percentage}) => void
   * @returns {Promise<{modelData: ArrayBuffer, config: Object}>}
   */
  async loadModel(modelNameOrUrl, options = {}) {
    const { onProgress } = options;
    const { modelUrl, configUrl, configFallbackUrl, cacheKey } = await this._resolveUrls(modelNameOrUrl);

    // Try the cache first.
    const cached = await this.getFromCache(cacheKey);
    if (cached) {
      return cached;
    }

    // Download config with fallback (small, no progress tracking needed).
    let configResponse = await fetch(configUrl);
    if (configResponse.status === 404 && configFallbackUrl) {
      configResponse = await fetch(configFallbackUrl);
    }
    if (!configResponse.ok) {
      const tried = configFallbackUrl
        ? `${configUrl} and ${configFallbackUrl}`
        : configUrl;
      throw new Error(
        `Failed to fetch model config from ${tried}: ${configResponse.status} ${configResponse.statusText}`
      );
    }
    const config = await configResponse.json();

    // Download model with progress tracking.
    const modelData = await fetchWithProgress(modelUrl, onProgress);

    // Compute SHA-256 integrity hash.
    const sha256 = await this._computeSha256(modelData);

    if (sha256 === null) {
      console.warn('[piper-plus] crypto.subtle unavailable — skipping SHA-256 integrity verification. Serve over HTTPS for full integrity checks.');
    } else if (config.sha256) {
      // Verify against the expected hash in the model config.
      if (sha256 !== config.sha256) {
        throw new Error(
          `SHA-256 mismatch for downloaded model: expected ${config.sha256}, got ${sha256}`
        );
      }
    }

    // Store in cache (include hash for later verification).
    const db = await this._getDb();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    await wrapRequest(
      store.put(
        { modelData, config, timestamp: Date.now(), sha256 },
        cacheKey,
      )
    );

    return { modelData, config };
  }

  /**
   * Retrieve a model from the IndexedDB cache.
   *
   * When {@link _verifyOnCacheHit} is true and a stored SHA-256 hash exists,
   * the hash is recomputed and compared.  A mismatch logs a warning and
   * returns null so that the caller re-downloads the model.
   *
   * @param {string} key - Cache key (repo name or URL)
   * @returns {Promise<{modelData: ArrayBuffer, config: Object}|null>}
   */
  async getFromCache(key) {
    const db = await this._getDb();
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const entry = await wrapRequest(store.get(key));
    if (!entry) {
      return null;
    }

    // Optionally verify integrity of cached data.
    if (this._verifyOnCacheHit && entry.sha256) {
      const currentHash = await this._computeSha256(entry.modelData);
      if (currentHash !== null && currentHash !== entry.sha256) {
        console.warn(
          `[piper-plus] Cached model "${key}" failed SHA-256 integrity check (expected ${entry.sha256}, got ${currentHash}). Re-downloading.`
        );
        return null;
      }
    }

    return { modelData: entry.modelData, config: entry.config };
  }

  // -------------------------------------------------------------------------
  // Dictionary caching (for ja-external / ja-lite WASM variant)
  // -------------------------------------------------------------------------

  /**
   * Retrieve a dictionary from the IndexedDB cache.
   *
   * @param {string} key - Cache key (e.g. 'naist-jdic-v1')
   * @returns {Promise<ArrayBuffer|null>}
   */
  async getDictionaryFromCache(key) {
    const db = await this._getDb();
    const tx = db.transaction(DICT_STORE, 'readonly');
    const store = tx.objectStore(DICT_STORE);
    const entry = await wrapRequest(store.get(key));
    if (!entry) {
      return null;
    }
    return entry.data;
  }

  /**
   * Save a dictionary to the IndexedDB cache.
   *
   * @param {string} key - Cache key (e.g. 'naist-jdic-v1')
   * @param {ArrayBuffer} data - Dictionary binary data
   * @returns {Promise<void>}
   */
  async cacheDictionary(key, data) {
    const db = await this._getDb();
    const tx = db.transaction(DICT_STORE, 'readwrite');
    const store = tx.objectStore(DICT_STORE);
    await wrapRequest(
      store.put(
        { data, timestamp: Date.now() },
        key,
      )
    );
  }

  /**
   * Fetch a dictionary from a URL, cache it in IndexedDB, and return the data.
   * If the dictionary is already cached, returns the cached version.
   *
   * @param {string} url - URL to fetch the dictionary from
   * @param {string} key - Cache key (e.g. 'naist-jdic-v1')
   * @param {Object} [options]
   * @param {Function} [options.onProgress] - ({loaded, total, percentage}) => void
   * @returns {Promise<ArrayBuffer>}
   */
  async fetchAndCacheDictionary(url, key, options = {}) {
    // Try cache first.
    const cached = await this.getDictionaryFromCache(key);
    if (cached) {
      return cached;
    }

    // Fetch from URL.
    const data = await fetchWithProgress(url, options.onProgress);

    // Store in cache.
    await this.cacheDictionary(key, data);

    return data;
  }

  /**
   * Remove all cached models and dictionaries.
   *
   * @returns {Promise<void>}
   */
  async clearCache() {
    const db = await this._getDb();
    const tx = db.transaction([STORE_NAME, DICT_STORE], 'readwrite');
    await wrapRequest(tx.objectStore(STORE_NAME).clear());
    await wrapRequest(tx.objectStore(DICT_STORE).clear());
  }
}
