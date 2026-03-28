/**
 * DictManager -- OpenJTalk dictionary download + IndexedDB cache.
 *
 * Downloads the dictionary archive from the same GitHub Release used by
 * Rust / C# / C++ implementations, extracts individual files in the browser,
 * verifies the SHA-256 hash, and caches them in IndexedDB.
 *
 * Usage:
 *   const dm = new DictManager();
 *   const { dictFiles, voiceData } = await dm.loadDictionary({
 *     onProgress: ({ phase, file, loaded, total, overallPercent }) => { ... }
 *   });
 */

// ---- Constants ----------------------------------------------------------------

/**
 * The same GitHub Release URL that Rust, C#, and C++ use.
 * @see src/rust/piper-core/src/dictionary_manager.rs
 * @see src/csharp/PiperPlus.Core/Config/DictionaryManager.cs
 */
const DICT_TAR_GZ_URL =
  'https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz';

/** SHA-256 of the tar.gz archive (same hash used by Rust / C#). */
const DICT_SHA256 =
  'fe6ba0e43542cef98339abdffd903e062008ea170b04e7e2a35da805902f382a';

/** Root directory inside the tar archive. */
const TAR_ROOT_DIR = 'open_jtalk_dic_utf_8-1.11';

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

// ---- SHA-256 verification -----------------------------------------------------

/**
 * Verify the SHA-256 hash of an ArrayBuffer using the Web Crypto API.
 *
 * @param {ArrayBuffer} buffer
 * @param {string} expectedHex - lowercase hex SHA-256 hash
 * @returns {Promise<boolean>}
 */
async function verifySha256(buffer, expectedHex) {
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = new Uint8Array(hashBuffer);
  let hex = '';
  for (let i = 0; i < hashArray.length; i++) {
    hex += hashArray[i].toString(16).padStart(2, '0');
  }
  return hex === expectedHex;
}

// ---- Tar extraction -----------------------------------------------------------

/**
 * Decompress a gzip buffer using the DecompressionStream API.
 *
 * @param {ArrayBuffer} compressedBuffer
 * @returns {Promise<ArrayBuffer>}
 */
async function decompressGzip(compressedBuffer) {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error(
      'DecompressionStream API is not available. ' +
      'Please use a modern browser (Chrome 80+, Firefox 113+, Safari 16.4+).'
    );
  }
  const stream = new Blob([compressedBuffer]).stream();
  const decompressed = stream.pipeThrough(new DecompressionStream('gzip'));
  return new Response(decompressed).arrayBuffer();
}

/**
 * Parse a POSIX tar archive and extract files as a Map of name -> ArrayBuffer.
 *
 * @param {ArrayBuffer} tarBuffer - Uncompressed tar data
 * @returns {Map<string, ArrayBuffer>}
 */
function parseTar(tarBuffer) {
  const files = new Map();
  const view = new Uint8Array(tarBuffer);
  let offset = 0;

  while (offset + 512 <= view.length) {
    const header = view.subarray(offset, offset + 512);
    offset += 512;

    // End-of-archive: zero block
    if (header.every((b) => b === 0)) break;

    // Filename (bytes 0-99)
    let name = '';
    for (let i = 0; i < 100 && header[i] !== 0; i++) {
      name += String.fromCharCode(header[i]);
    }

    // UStar prefix (bytes 345-499)
    let prefix = '';
    for (let i = 345; i < 500 && header[i] !== 0; i++) {
      prefix += String.fromCharCode(header[i]);
    }
    if (prefix) {
      name = prefix + '/' + name;
    }

    // File size (octal, bytes 124-135)
    let sizeStr = '';
    for (let i = 124; i < 136 && header[i] !== 0; i++) {
      sizeStr += String.fromCharCode(header[i]);
    }
    const size = parseInt(sizeStr.trim(), 8) || 0;

    // Type flag (byte 156): '0' or NUL = regular file
    const typeFlag = header[156];

    if (size > 0) {
      const paddedSize = Math.ceil(size / 512) * 512;
      if (typeFlag === 0x30 || typeFlag === 0) {
        files.set(name, tarBuffer.slice(offset, offset + size));
      }
      offset += paddedSize;
    }
  }

  return files;
}

/**
 * Download the tar.gz archive, verify its SHA-256 hash, decompress and
 * extract the required dictionary files.
 *
 * @param {string} tarGzUrl
 * @param {(loaded: number, total: number) => void} [onProgress]
 * @returns {Promise<Object<string, ArrayBuffer>>} filename -> ArrayBuffer
 */
async function downloadAndExtractDict(tarGzUrl, onProgress) {
  // 1. Download tar.gz
  const compressedData = await fetchWithProgress(tarGzUrl, onProgress);

  // 2. Verify SHA-256
  const valid = await verifySha256(compressedData, DICT_SHA256);
  if (!valid) {
    throw new Error(
      'Dictionary archive SHA-256 verification failed. ' +
      'The downloaded file may be corrupted or tampered with.'
    );
  }

  // 3. Decompress gzip
  const tarData = await decompressGzip(compressedData);

  // 4. Parse tar and extract required files
  const allFiles = parseTar(tarData);
  const dictFiles = {};

  for (const filename of DICT_FILES) {
    // Files in the tar are prefixed with the root directory name
    const tarPath = `${TAR_ROOT_DIR}/${filename}`;
    const data = allFiles.get(tarPath);
    if (!data) {
      throw new Error(
        `Required dictionary file "${filename}" not found in archive (expected "${tarPath}").`
      );
    }
    dictFiles[filename] = data;
  }

  return dictFiles;
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
   * Resolve dictionary and voice URLs without downloading anything.
   *
   * @param {Object} [options]
   * @param {string} [options.dictUrl]  - Custom tar.gz URL for the dictionary archive.
   * @param {string} [options.voiceUrl] - URL for the HTS voice file.
   * @returns {{ dictUrl: string, voiceUrl: string }}
   */
  resolveUrls(options = {}) {
    const dictUrl = options.dictUrl || DICT_TAR_GZ_URL;
    const voiceUrl = options.voiceUrl || DEFAULT_VOICE_URL;
    return { dictUrl, voiceUrl };
  }

  /**
   * Download (or retrieve from cache) dictionary files and the HTS voice file.
   *
   * On the first call the full tar.gz is downloaded from GitHub Releases,
   * its SHA-256 is verified, and the individual files are cached in IndexedDB.
   * Subsequent calls return instantly from the cache.
   *
   * @param {Object} [options]
   * @param {string} [options.dictUrl]    - Custom tar.gz URL (default: GitHub Releases).
   * @param {string} [options.voiceUrl]   - URL for the HTS voice file.
   * @param {Function} [options.onProgress] - Progress callback.
   *   Called with `{ phase, file, loaded, total, overallPercent }`.
   *   - phase: 'dict' | 'voice'
   *   - file: current filename or archive name
   *   - loaded / total: bytes
   *   - overallPercent: 0-100
   * @returns {Promise<{dictFiles: Object<string,ArrayBuffer>, voiceData: ArrayBuffer}>}
   */
  async loadDictionary(options = {}) {
    const { dictUrl, voiceUrl } = this.resolveUrls(options);
    const onProgress = options.onProgress || null;

    const db = await this._openDB();

    // ---- Dictionary files ---------------------------------------------------

    /** @type {Object<string,ArrayBuffer>} */
    let dictFiles = {};
    const allCached = await this._allDictFilesCached(db);

    if (allCached) {
      // All files in cache — load from IndexedDB
      for (const filename of DICT_FILES) {
        dictFiles[filename] = await this._getFromCache(db, `dict/${filename}`);
      }
      if (onProgress) {
        onProgress({
          phase: 'dict',
          file: 'cache',
          loaded: 1,
          total: 1,
          overallPercent: 50,
        });
      }
    } else {
      // Download tar.gz, verify, extract, and cache
      dictFiles = await downloadAndExtractDict(dictUrl, (loaded, total) => {
        if (onProgress) {
          onProgress({
            phase: 'dict',
            file: 'open_jtalk_dic_utf_8-1.11.tar.gz',
            loaded,
            total,
            overallPercent: Math.round((loaded / Math.max(total, 1)) * 50),
          });
        }
      });

      // Cache individual extracted files
      for (const filename of DICT_FILES) {
        await this._putToCache(db, `dict/${filename}`, dictFiles[filename]);
      }
    }

    // ---- Voice file ---------------------------------------------------------

    let voiceData;
    const cachedVoice = await this._getFromCache(db, VOICE_KEY);

    if (cachedVoice) {
      voiceData = cachedVoice;
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
            overallPercent: 50 + Math.round((loaded / Math.max(total, 1)) * 50),
          });
        }
      });

      await this._putToCache(db, VOICE_KEY, voiceData);
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
      if (!(await this._allDictFilesCached(db))) return false;

      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
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
   * Check whether all 8 dictionary files are present in the cache.
   *
   * @param {IDBDatabase} db
   * @returns {Promise<boolean>}
   */
  async _allDictFilesCached(db) {
    try {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      for (const filename of DICT_FILES) {
        const result = await wrapRequest(store.get(`dict/${filename}`));
        if (!result || !result.data) return false;
      }
      return true;
    } catch {
      return false;
    }
  }

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
