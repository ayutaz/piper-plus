/**
 * DictLoader -- OpenJTalk dictionary download + IndexedDB cache for G2P.
 *
 * Derived from @piper-plus/piper-plus DictManager, stripped down to
 * dictionary-only loading (no onnxruntime-web dependency).
 *
 * Downloads the dictionary archive from GitHub Releases, verifies the
 * SHA-256 hash, extracts individual files in the browser, and caches
 * them in IndexedDB for instant subsequent loads.
 *
 * Usage:
 *   import { DictLoader } from './dict-loader.js';
 *
 *   const loader = new DictLoader();
 *   const { dictFiles } = await loader.loadJaDict({
 *     onProgress: ({ loaded, total }) => { ... }
 *   });
 *
 * @module dict-loader
 */

// ---- Constants ----------------------------------------------------------------

/**
 * Default dictionary archive URL (GitHub Releases).
 * Shared across Rust, C#, C++, and npm implementations.
 */
const DICT_TAR_GZ_URL =
  'https://github.com/ayutaz/piper-plus/releases/download/dict-v1.0.0/open_jtalk_dic_utf_8-1.11.tar.gz';

/** SHA-256 of the default tar.gz archive. */
const DICT_SHA256 =
  'fe6ba0e43542cef98339abdffd903e062008ea170b04e7e2a35da805902f382a';

/** Root directory inside the tar archive. */
const TAR_ROOT_DIR = 'open_jtalk_dic_utf_8-1.11';

/** The 8 MeCab dictionary files required by OpenJTalk. */
const DICT_FILES = [
  'char.bin',
  'matrix.bin',
  'sys.dic',
  'unk.dic',
  'left-id.def',
  'pos-id.def',
  'rewrite.def',
  'right-id.def',
];

const DEFAULT_DB_NAME = 'piper-g2p-dict';
const STORE_NAME = 'files';
const DB_VERSION = 1;

// ---- IndexedDB helpers --------------------------------------------------------

/**
 * Open (or create) the IndexedDB database.
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
 * Content-Length header.
 *
 * @param {string} url
 * @param {((progress: { loaded: number, total: number }) => void)|null} onProgress
 * @returns {Promise<ArrayBuffer>}
 */
async function fetchWithProgress(url, onProgress) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
  }

  const contentLength = response.headers.get('Content-Length');
  if (!contentLength || !response.body) {
    const buffer = await response.arrayBuffer();
    if (onProgress) onProgress({ loaded: buffer.byteLength, total: buffer.byteLength });
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
    if (onProgress) onProgress({ loaded, total });
  }

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
  if (!globalThis.crypto?.subtle?.digest) {
    throw new Error(
      'Web Crypto API (crypto.subtle) is not available. ' +
      'A secure context (HTTPS) is required for SHA-256 verification.'
    );
  }
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
 * @param {((progress: { loaded: number, total: number }) => void)|null} onProgress
 * @returns {Promise<Record<string, ArrayBuffer>>} filename -> ArrayBuffer
 */
async function downloadAndExtractDict(tarGzUrl, onProgress) {
  const isDefaultUrl = tarGzUrl === DICT_TAR_GZ_URL;

  // 1. Download tar.gz
  const compressedData = await fetchWithProgress(tarGzUrl, onProgress);

  // 2. Verify SHA-256 (only for the default archive; custom URLs may differ)
  if (isDefaultUrl) {
    const valid = await verifySha256(compressedData, DICT_SHA256);
    if (!valid) {
      throw new Error(
        'Dictionary archive SHA-256 verification failed. ' +
        'The downloaded file may be corrupted or tampered with.'
      );
    }
  }

  // 3. Decompress gzip
  const tarData = await decompressGzip(compressedData);

  // 4. Parse tar and extract required files
  const allFiles = parseTar(tarData);
  const dictFiles = {};

  // Auto-detect tar root directory by looking for the first required file
  let rootDir = isDefaultUrl ? TAR_ROOT_DIR : '';
  if (!isDefaultUrl) {
    const firstFile = DICT_FILES[0];
    for (const key of allFiles.keys()) {
      if (key.endsWith('/' + firstFile)) {
        rootDir = key.slice(0, -(firstFile.length + 1));
        break;
      } else if (key === firstFile) {
        rootDir = '';
        break;
      }
    }
  }

  for (const filename of DICT_FILES) {
    const tarPath = rootDir ? `${rootDir}/${filename}` : filename;
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

// ---- DictLoader ---------------------------------------------------------------

/**
 * Dictionary loader for @piper-plus/g2p.
 *
 * Downloads OpenJTalk MeCab dictionary files from GitHub Releases, verifies
 * the SHA-256 hash, and caches them in IndexedDB.
 *
 * No dependency on onnxruntime-web.
 *
 * @example
 * const loader = new DictLoader();
 * const { dictFiles } = await loader.loadJaDict();
 * // dictFiles['sys.dic'] -> ArrayBuffer
 */
export class DictLoader {
  /**
   * @param {Object} [options]
   * @param {string} [options.cachePrefix='piper-g2p-dict'] - IndexedDB database name.
   */
  constructor(options = {}) {
    this._dbName = options.cachePrefix || DEFAULT_DB_NAME;
    /** @type {IDBDatabase|null} */
    this._db = null;
  }

  // ---- Public API -------------------------------------------------------------

  /**
   * Download (or retrieve from cache) Japanese dictionary files.
   *
   * On the first call the full tar.gz is downloaded from GitHub Releases,
   * its SHA-256 is verified, and the 8 individual dictionary files are cached
   * in IndexedDB. Subsequent calls return instantly from the cache.
   *
   * @param {Object} [options]
   * @param {string} [options.dictUrl]       - Custom tar.gz URL (default: GitHub Releases).
   * @param {(progress: { loaded: number, total: number }) => void} [options.onProgress]
   *   Progress callback. Called with `{ loaded, total }` (bytes) during download.
   * @returns {Promise<JaDictData>}
   *
   * @typedef {Object} JaDictData
   * @property {Record<string, ArrayBuffer>} dictFiles - The 8 MeCab dictionary files.
   */
  async loadJaDict(options = {}) {
    const dictUrl = options.dictUrl || DICT_TAR_GZ_URL;
    const onProgress = options.onProgress || null;

    const db = await this._openDB();

    // ---- Dictionary files ---------------------------------------------------

    /** @type {Record<string, ArrayBuffer>} */
    let dictFiles = {};
    const allCached = await this._allDictFilesCached(db);

    if (allCached) {
      for (const filename of DICT_FILES) {
        dictFiles[filename] = await this._getFromCache(db, `dict/${filename}`);
      }
      if (onProgress) {
        onProgress({ loaded: 1, total: 1 });
      }
    } else {
      dictFiles = await downloadAndExtractDict(dictUrl, onProgress);

      // Cache individual extracted files
      for (const filename of DICT_FILES) {
        await this._putToCache(db, `dict/${filename}`, dictFiles[filename]);
      }
    }

    return { dictFiles };
  }

  /**
   * Check whether all dictionary files are already cached in IndexedDB.
   *
   * @returns {Promise<boolean>}
   */
  async isCached() {
    try {
      const db = await this._openDB();
      return await this._allDictFilesCached(db);
    } catch {
      return false;
    }
  }

  /**
   * Remove all cached dictionary data from IndexedDB.
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
   * Retrieve an ArrayBuffer from the cache, or null if missing.
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
    await wrapRequest(store.put({ key, data, storedAt: Date.now() }));
  }
}
