/**
 * DictManager -- OpenJTalk dictionary dynamic download + IndexedDB cache.
 *
 * Downloads individual dictionary files from HuggingFace (or a custom URL)
 * and caches them in IndexedDB so that subsequent loads are instant.
 *
 * Usage:
 *   const dm = new DictManager();
 *   const { dictFiles, voiceData } = await dm.loadDictionary({
 *     onProgress: ({ phase, file, loaded, total, overallPercent }) => { ... }
 *   });
 */

// ---- Constants ----------------------------------------------------------------

const DICT_FILES = [
  'char.bin',
  'matrix.bin',
  'sys.dic',
  'unk.dic',
  'left-id.def',
  'right-id.def',
  'pos-id.def',
  'rewrite.def',
];

const VOICE_KEY = 'voice/mei_normal.htsvoice';

const DEFAULT_DICT_BASE_URL =
  'https://huggingface.co/ayousanz/piper-plus-base/resolve/main/dict';
const DEFAULT_VOICE_URL =
  'https://huggingface.co/ayousanz/piper-plus-base/resolve/main/voice/mei_normal.htsvoice';

const DB_NAME = 'piper-plus-dict';
const STORE_NAME = 'files';
const DB_VERSION = 1;

// ---- IndexedDB helpers --------------------------------------------------------

/**
 * Open (or create) the IndexedDB database used for dictionary caching.
 *
 * @param {string} dbName
 * @returns {Promise<IDBDatabase>}
 */
function openDB(dbName) {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(dbName, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'key' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
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

// ---- Fetch with progress ------------------------------------------------------

/**
 * Fetch a URL as an ArrayBuffer while reporting byte-level progress.
 *
 * Falls back to a plain `response.arrayBuffer()` when the response has no
 * `Content-Length` header (e.g. some CDN edge cases).
 *
 * @param {string} url
 * @param {(loaded: number, total: number) => void} [onProgress]
 * @returns {Promise<ArrayBuffer>}
 */
async function fetchWithProgress(url, onProgress) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
  }

  const contentLength = response.headers.get('Content-Length');
  if (!contentLength || !response.body) {
    // No Content-Length or no readable body -- fall back to simple fetch.
    const buffer = await response.arrayBuffer();
    if (onProgress) onProgress(buffer.byteLength, buffer.byteLength);
    return buffer;
  }

  const total = parseInt(contentLength, 10);
  const reader = response.body.getReader();
  const chunks = [];
  let loaded = 0;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.byteLength;
    if (onProgress) onProgress(loaded, total);
  }

  // Merge chunks into a single ArrayBuffer.
  const merged = new Uint8Array(loaded);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }

  return merged.buffer;
}

// ---- DictManager --------------------------------------------------------------

export class DictManager {
  /**
   * @param {Object} [options]
   * @param {string} [options.cachePrefix='piper-plus-dict'] - IndexedDB database name.
   */
  constructor(options = {}) {
    this._dbName = options.cachePrefix || DB_NAME;
    /** @type {IDBDatabase|null} */
    this._db = null;
  }

  // ---- Public API -------------------------------------------------------------

  /**
   * Download (or retrieve from cache) dictionary files and the HTS voice file.
   *
   * @param {Object} [options]
   * @param {string} [options.dictUrl]    - Base URL for dictionary files.
   * @param {string} [options.voiceUrl]   - URL for the HTS voice file.
   * @param {Function} [options.onProgress] - Progress callback.
   *   Called with `{ phase, file, loaded, total, overallPercent }`.
   *   - phase: 'dict' | 'voice'
   *   - file: current filename (only during 'dict' phase)
   *   - loaded / total: bytes for the current file
   *   - overallPercent: 0-100 across all files
   * @returns {Promise<{dictFiles: Object<string,ArrayBuffer>, voiceData: ArrayBuffer}>}
   */
  async loadDictionary(options = {}) {
    const dictBaseUrl = options.dictUrl || DEFAULT_DICT_BASE_URL;
    const voiceUrl = options.voiceUrl || DEFAULT_VOICE_URL;
    const onProgress = options.onProgress || null;

    const db = await this._openDB();

    // Total number of items to track (dict files + voice).
    const totalItems = DICT_FILES.length + 1;
    let completedItems = 0;

    // ---- Dictionary files ---------------------------------------------------

    /** @type {Object<string,ArrayBuffer>} */
    const dictFiles = {};

    for (const filename of DICT_FILES) {
      const cacheKey = `dict/${filename}`;
      const cached = await this._getFromCache(db, cacheKey);

      if (cached) {
        dictFiles[filename] = cached;
        completedItems++;
        if (onProgress) {
          onProgress({
            phase: 'dict',
            file: filename,
            loaded: cached.byteLength,
            total: cached.byteLength,
            overallPercent: Math.round((completedItems / totalItems) * 100),
          });
        }
        continue;
      }

      // Not cached -- download.
      const url = `${dictBaseUrl}/${filename}`;
      const data = await fetchWithProgress(url, (loaded, total) => {
        if (onProgress) {
          onProgress({
            phase: 'dict',
            file: filename,
            loaded,
            total,
            overallPercent: Math.round(
              ((completedItems + loaded / Math.max(total, 1)) / totalItems) * 100
            ),
          });
        }
      });

      // Cache the downloaded file.
      await this._putToCache(db, cacheKey, data);

      dictFiles[filename] = data;
      completedItems++;
    }

    // ---- Voice file ---------------------------------------------------------

    let voiceData;
    const cachedVoice = await this._getFromCache(db, VOICE_KEY);

    if (cachedVoice) {
      voiceData = cachedVoice;
      completedItems++;
      if (onProgress) {
        onProgress({
          phase: 'voice',
          file: VOICE_KEY,
          loaded: cachedVoice.byteLength,
          total: cachedVoice.byteLength,
          overallPercent: 100,
        });
      }
    } else {
      voiceData = await fetchWithProgress(voiceUrl, (loaded, total) => {
        if (onProgress) {
          onProgress({
            phase: 'voice',
            file: VOICE_KEY,
            loaded,
            total,
            overallPercent: Math.round(
              ((completedItems + loaded / Math.max(total, 1)) / totalItems) * 100
            ),
          });
        }
      });

      await this._putToCache(db, VOICE_KEY, voiceData);
      completedItems++;
    }

    return { dictFiles, voiceData };
  }

  /**
   * Check whether all dictionary files and the voice file are already cached.
   *
   * @returns {Promise<boolean>}
   */
  async isCached() {
    try {
      const db = await this._openDB();
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);

      // Check every dict file key.
      for (const filename of DICT_FILES) {
        const result = await wrapRequest(store.get(`dict/${filename}`));
        if (!result || !result.data) return false;
      }

      // Check voice key.
      const voiceResult = await wrapRequest(store.get(VOICE_KEY));
      if (!voiceResult || !voiceResult.data) return false;

      return true;
    } catch {
      return false;
    }
  }

  /**
   * Remove all cached dictionary and voice data.
   *
   * @returns {Promise<void>}
   */
  async clearCache() {
    const db = await this._openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    await wrapRequest(store.clear());
  }

  // ---- Private helpers ------------------------------------------------------

  /**
   * Lazily open (and cache) the IndexedDB connection.
   *
   * @returns {Promise<IDBDatabase>}
   */
  async _openDB() {
    if (this._db) return this._db;
    this._db = await openDB(this._dbName);
    return this._db;
  }

  /**
   * Retrieve an ArrayBuffer from the cache, or `null` if missing.
   *
   * @param {IDBDatabase} db
   * @param {string} key
   * @returns {Promise<ArrayBuffer|null>}
   */
  async _getFromCache(db, key) {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const result = await wrapRequest(store.get(key));
    if (result && result.data) return result.data;
    return null;
  }

  /**
   * Store an ArrayBuffer in the cache.
   *
   * @param {IDBDatabase} db
   * @param {string} key
   * @param {ArrayBuffer} data
   * @returns {Promise<void>}
   */
  async _putToCache(db, key, data) {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    await wrapRequest(
      store.put({ key, data, storedAt: Date.now() })
    );
  }
}
