/**
 * ModelManager — Download and cache ONNX models from HuggingFace.
 *
 * Provides automatic URL resolution for HuggingFace repository names,
 * shortcut aliases, progress tracking during download, and IndexedDB caching.
 */

const DB_NAME = 'piper-plus-models';
const STORE_NAME = 'models';
const DB_VERSION = 1;

const HUGGINGFACE_API_BASE = 'https://huggingface.co/api/models';
const HUGGINGFACE_RESOLVE_BASE = 'https://huggingface.co';

/**
 * Shortcut names that resolve to full HuggingFace repository identifiers.
 */
const MODEL_REGISTRY = {
  'tsukuyomi': 'ayousanz/piper-plus-tsukuyomi-chan',
  'tsukuyomi-chan': 'ayousanz/piper-plus-tsukuyomi-chan',
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
 * Query the HuggingFace API for repository metadata and find the ONNX
 * filename from the siblings list.
 *
 * @param {string} repoName - e.g. "ayousanz/piper-plus-tsukuyomi-chan"
 * @returns {Promise<string>} - The ONNX filename found in the repository
 */
async function resolveOnnxFilename(repoName) {
  const apiUrl = `${HUGGINGFACE_API_BASE}/${repoName}`;
  const response = await fetch(apiUrl);
  if (!response.ok) {
    throw new Error(
      `Failed to query HuggingFace API for "${repoName}": ${response.status} ${response.statusText}`
    );
  }

  const metadata = await response.json();
  const siblings = metadata.siblings || [];
  const onnxFiles = siblings
    .map((s) => s.rfilename)
    .filter((name) => name.endsWith('.onnx'));

  if (onnxFiles.length === 0) {
    throw new Error(`No .onnx file found in repository "${repoName}"`);
  }

  // If multiple ONNX files exist, prefer one with "fp16" in the name.
  const fp16File = onnxFiles.find((name) => name.includes('fp16'));
  return fp16File || onnxFiles[0];
}

export class ModelManager {
  /**
   * @param {Object} [options]
   * @param {string} [options.cachePrefix='piper-plus-models'] - IndexedDB database name
   */
  constructor(options = {}) {
    this._dbName = options.cachePrefix || DB_NAME;
    this._db = null;
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
   * Resolve a model identifier to concrete URLs for the ONNX model and its
   * companion config JSON.
   *
   * Accepted formats:
   *   - Registry shortcut: "tsukuyomi"
   *   - HuggingFace repo:  "ayousanz/piper-plus-tsukuyomi-chan"
   *   - Direct URL:        "https://example.com/model.onnx"
   *
   * @param {string} modelNameOrUrl
   * @returns {Promise<{modelUrl: string, configUrl: string, cacheKey: string}>}
   */
  async _resolveUrls(modelNameOrUrl) {
    // Direct URL.
    if (/^https?:\/\//i.test(modelNameOrUrl)) {
      const modelUrl = modelNameOrUrl;
      const configUrl = modelUrl + '.json';
      return { modelUrl, configUrl, cacheKey: modelUrl };
    }

    // Registry shortcut.
    const repoName = MODEL_REGISTRY[modelNameOrUrl] || modelNameOrUrl;

    // Resolve the ONNX filename from the HuggingFace API.
    const onnxFilename = await resolveOnnxFilename(repoName);

    const modelUrl = `${HUGGINGFACE_RESOLVE_BASE}/${repoName}/resolve/main/${onnxFilename}`;
    const configUrl = `${HUGGINGFACE_RESOLVE_BASE}/${repoName}/resolve/main/${onnxFilename}.json`;

    return { modelUrl, configUrl, cacheKey: repoName };
  }

  /**
   * Resolve a model identifier to concrete URLs.
   *
   * This is the public entry point that delegates to {@link _resolveUrls}.
   *
   * @param {string} modelNameOrUrl - Registry shortcut, HuggingFace repo, or direct URL
   * @returns {Promise<{modelUrl: string, configUrl: string, cacheKey: string}>}
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
    const { modelUrl, configUrl, cacheKey } = await this._resolveUrls(modelNameOrUrl);

    // Try the cache first.
    const cached = await this.getFromCache(cacheKey);
    if (cached) {
      return cached;
    }

    // Download config (small, no progress tracking needed).
    const configResponse = await fetch(configUrl);
    if (!configResponse.ok) {
      throw new Error(
        `Failed to fetch model config from ${configUrl}: ${configResponse.status} ${configResponse.statusText}`
      );
    }
    const config = await configResponse.json();

    // Download model with progress tracking.
    const modelData = await fetchWithProgress(modelUrl, onProgress);

    // Store in cache.
    const db = await this._getDb();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    await wrapRequest(
      store.put(
        { modelData, config, timestamp: Date.now() },
        cacheKey,
      )
    );

    return { modelData, config };
  }

  /**
   * Retrieve a model from the IndexedDB cache.
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
    return { modelData: entry.modelData, config: entry.config };
  }

  /**
   * Remove all cached models.
   *
   * @returns {Promise<void>}
   */
  async clearCache() {
    const db = await this._getDb();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    await wrapRequest(store.clear());
  }
}
