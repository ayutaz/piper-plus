/**
 * Shared mock utilities for DictManager tests.
 *
 * Creates a real gzipped tar archive containing the 8 OpenJTalk dictionary
 * files so that DictManager's tar.gz download → decompress → extract → cache
 * pipeline can be exercised end-to-end in Node.js tests.
 */

import { gzipSync } from 'node:zlib';

// ---- Constants ----------------------------------------------------------------

export const TAR_ROOT = 'open_jtalk_dic_utf_8-1.11';

export const DICT_FILES = [
  'char.bin',
  'matrix.bin',
  'sys.dic',
  'unk.dic',
  'left-id.def',
  'right-id.def',
  'pos-id.def',
  'rewrite.def',
];

export const DICT_SHA256 =
  'fe6ba0e43542cef98339abdffd903e062008ea170b04e7e2a35da805902f382a';

export const DICT_TAR_GZ_URL =
  'https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz';

export const VOICE_URL =
  'https://huggingface.co/ayousanz/piper-plus-base/resolve/main/voice/mei_normal.htsvoice';

// ---- Tar builder --------------------------------------------------------------

function createTarEntry(filename, data) {
  const header = new Uint8Array(512);
  const enc = new TextEncoder();

  // Filename (0-99)
  header.set(enc.encode(filename).subarray(0, 100));

  // Mode (100-107)
  header.set(enc.encode('0000644'), 100);
  header[107] = 0;

  // UID / GID (108-123)
  header.set(enc.encode('0000000'), 108);
  header[115] = 0;
  header.set(enc.encode('0000000'), 116);
  header[123] = 0;

  // Size (124-135) — octal
  header.set(enc.encode(data.byteLength.toString(8).padStart(11, '0')), 124);
  header[135] = 0;

  // Mtime (136-147)
  header.set(enc.encode('00000000000'), 136);
  header[147] = 0;

  // Checksum placeholder: 8 spaces (148-155)
  for (let i = 148; i < 156; i++) header[i] = 0x20;

  // Type flag: '0' = regular file
  header[156] = 0x30;

  // UStar magic (257-264)
  header.set(enc.encode('ustar'), 257);
  header[262] = 0;
  header[263] = 0x30;
  header[264] = 0x30;

  // Compute checksum
  let sum = 0;
  for (let i = 0; i < 512; i++) sum += header[i];
  const csStr = sum.toString(8).padStart(6, '0');
  header.set(enc.encode(csStr), 148);
  header[154] = 0;
  header[155] = 0x20;

  // Data padded to 512-byte boundary
  const padded = Math.ceil(data.byteLength / 512) * 512;
  const dataBlock = new Uint8Array(padded);
  dataBlock.set(new Uint8Array(data));

  return { header, dataBlock };
}

/**
 * Build a gzipped tar archive containing the 8 dict files.
 *
 * @param {number} [fileSize=64] Byte size of each mock dict file.
 * @param {number} [fillByte=0xAB] Fill byte for mock data.
 * @returns {ArrayBuffer}
 */
export function createMockTarGz(fileSize = 64, fillByte = 0xAB) {
  const blocks = [];

  for (const name of DICT_FILES) {
    const data = new ArrayBuffer(fileSize);
    new Uint8Array(data).fill(fillByte);
    const entry = createTarEntry(`${TAR_ROOT}/${name}`, data);
    blocks.push(entry.header, entry.dataBlock);
  }

  // End-of-archive marker: two 512-byte zero blocks
  blocks.push(new Uint8Array(1024));

  const total = blocks.reduce((s, b) => s + b.byteLength, 0);
  const tar = new Uint8Array(total);
  let off = 0;
  for (const b of blocks) {
    tar.set(b, off);
    off += b.byteLength;
  }

  const gz = gzipSync(tar);
  // Buffer.buffer may be a shared ArrayBuffer pool slice — copy to isolate.
  return gz.buffer.slice(gz.byteOffset, gz.byteOffset + gz.byteLength);
}

// ---- IndexedDB mock -----------------------------------------------------------

export class MockObjectStore {
  constructor(store) { this._store = store; }

  get(key) {
    const result = this._store.get(key) ?? undefined;
    return _fakeRequest(result);
  }

  put(val) {
    this._store.set(val.key, val);
    return _fakeRequest(undefined);
  }

  clear() {
    this._store.clear();
    return _fakeRequest(undefined);
  }
}

function _fakeRequest(result) {
  const req = { result, onsuccess: null, onerror: null };
  Promise.resolve().then(() => { if (req.onsuccess) req.onsuccess(); });
  return req;
}

export class MockIDBDatabase {
  constructor() {
    this._stores = new Map();
    this.objectStoreNames = { contains: (n) => this._stores.has(n) };
  }

  _ensureStore(name) {
    if (!this._stores.has(name)) this._stores.set(name, new Map());
    return this._stores.get(name);
  }

  createObjectStore(name) { this._ensureStore(name); }

  transaction(storeName) {
    const store = this._ensureStore(storeName);
    return { objectStore: () => new MockObjectStore(store) };
  }
}

/**
 * Install a global IndexedDB mock.  Returns `{ db, lastDbName }`.
 */
export function installIndexedDBMock() {
  const state = { db: new MockIDBDatabase(), lastDbName: undefined };

  globalThis.indexedDB = {
    open(name) {
      state.lastDbName = name;
      const req = { result: null, onsuccess: null, onerror: null, onupgradeneeded: null };
      Promise.resolve().then(() => {
        if (req.onupgradeneeded) req.onupgradeneeded({ target: { result: state.db } });
        req.result = state.db;
        if (req.onsuccess) req.onsuccess();
      });
      return req;
    },
  };

  return state;
}

// ---- Fetch mock ---------------------------------------------------------------

/**
 * Install a global fetch mock that returns a tar.gz for dict URLs and a
 * plain buffer for voice URLs.
 *
 * @param {Object} [opts]
 * @param {boolean} [opts.shouldFail]   - Return 404 for all fetches.
 * @param {boolean} [opts.shouldReject] - Reject with TypeError.
 * @param {number}  [opts.dictFileSize] - Per-file size inside the tar.
 * @param {number}  [opts.voiceSize]    - Voice buffer size.
 * @returns {string[]} Array that collects fetched URLs.
 */
export function installFetchMock({
  shouldFail = false,
  shouldReject = false,
  dictFileSize = 64,
  voiceSize = 64,
} = {}) {
  const mockTarGz = createMockTarGz(dictFileSize);
  const mockVoice = new ArrayBuffer(voiceSize);
  new Uint8Array(mockVoice).fill(0xCD);

  const fetched = [];

  globalThis.fetch = async (url) => {
    fetched.push(url);
    if (shouldReject) throw new TypeError('Failed to fetch');
    if (shouldFail) return { ok: false, status: 404, statusText: 'Not Found' };

    const body = url.includes('.tar.gz') ? mockTarGz : mockVoice;

    return {
      ok: true,
      headers: { get: (h) => (h === 'Content-Length' ? String(body.byteLength) : null) },
      body: null,
      arrayBuffer: async () => body,
    };
  };

  return fetched;
}

// ---- Crypto mock (SHA-256 always passes) --------------------------------------

let _origDigest;

export function installCryptoMock() {
  // Node.js makes globalThis.crypto a getter-only property, so we
  // monkey-patch crypto.subtle.digest instead of replacing crypto itself.
  _origDigest = globalThis.crypto?.subtle?.digest;
  if (globalThis.crypto?.subtle) {
    globalThis.crypto.subtle.digest = async () => {
      const bytes = new Uint8Array(32);
      for (let i = 0; i < 64; i += 2) {
        bytes[i / 2] = parseInt(DICT_SHA256.substr(i, 2), 16);
      }
      return bytes.buffer;
    };
  }
}

export function restoreCrypto() {
  if (_origDigest && globalThis.crypto?.subtle) {
    globalThis.crypto.subtle.digest = _origDigest;
  }
}

// ---- Cleanup ------------------------------------------------------------------

export function cleanup() {
  delete globalThis.indexedDB;
  delete globalThis.fetch;
  restoreCrypto();
}
