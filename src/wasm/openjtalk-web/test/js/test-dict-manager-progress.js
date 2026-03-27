/**
 * TDD Tests for DictManager onProgress callback
 *
 * テスト対象: src/wasm/openjtalk-web/src/dict-manager.js
 * onProgress コールバックの詳細な振る舞いを検証する。
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';

// ---- Mock: IndexedDB -----------------------------------------------------------

class MockObjectStore {
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
  Promise.resolve().then(() => {
    if (req.onsuccess) req.onsuccess();
  });
  return req;
}

class MockIDBDatabase {
  constructor() {
    this._stores = new Map();
    this.objectStoreNames = { contains: (n) => this._stores.has(n) };
  }

  _ensureStore(name) {
    if (!this._stores.has(name)) this._stores.set(name, new Map());
    return this._stores.get(name);
  }

  createObjectStore(name, _opts) {
    this._ensureStore(name);
  }

  transaction(storeName, _mode) {
    const store = this._ensureStore(storeName);
    return { objectStore: () => new MockObjectStore(store) };
  }
}

let _mockDB;

function installIndexedDBMock() {
  _mockDB = new MockIDBDatabase();
  globalThis.indexedDB = {
    open(name, version) {
      const req = { result: null, onsuccess: null, onerror: null, onupgradeneeded: null };
      Promise.resolve().then(() => {
        if (req.onupgradeneeded) {
          req.onupgradeneeded({ target: { result: _mockDB } });
        }
        req.result = _mockDB;
        if (req.onsuccess) req.onsuccess();
      });
      return req;
    },
  };
}

// ---- Mock: fetch ---------------------------------------------------------------

/**
 * Install a global fetch mock that returns ArrayBuffers of a given size.
 * The mock has no Content-Length header and no readable body, so
 * fetchWithProgress falls back to response.arrayBuffer() and fires
 * a single onProgress(byteLength, byteLength) per file.
 *
 * @returns {string[]} Array that collects fetched URLs.
 */
function installFetchMock() {
  const fetched = [];
  globalThis.fetch = async (url) => {
    fetched.push(url);
    const body = new ArrayBuffer(64);
    return {
      ok: true,
      headers: { get: () => null },
      body: null,
      arrayBuffer: async () => body,
    };
  };
  return fetched;
}

// ---- Import SUT ----------------------------------------------------------------

let DictManager;
try {
  const mod = await import('../../src/dict-manager.js');
  DictManager = mod.DictManager || mod.default;
} catch {
  DictManager = null;
}

const skip = DictManager === null;

// ---- Constants -----------------------------------------------------------------

const EXPECTED_DICT_FILES = [
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

/** Total items tracked by DictManager: 8 dict files + 1 voice. */
const TOTAL_ITEMS = EXPECTED_DICT_FILES.length + 1;

// ---- Tests ---------------------------------------------------------------------

describe('DictManager onProgress コールバック', { skip }, () => {
  /** @type {string[]} */
  let fetched;

  beforeEach(() => {
    installIndexedDBMock();
    fetched = installFetchMock();
  });

  afterEach(() => {
    fetched = [];
    delete globalThis.indexedDB;
    delete globalThis.fetch;
  });

  // ---------- 1. onProgress が呼び出される -------------------------------------------

  it('onProgress が呼び出される', async () => {
    // Arrange
    const calls = [];
    const dm = new DictManager();

    // Act
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    // Assert
    assert.ok(calls.length > 0, 'onProgress should be invoked at least once');
  });

  // ---------- 2. onProgress に phase が含まれる --------------------------------------

  it('onProgress に phase が含まれる', async () => {
    // Arrange
    const calls = [];
    const dm = new DictManager();

    // Act
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    // Assert
    const phases = new Set(calls.map((c) => c.phase));
    assert.ok(phases.has('dict'), "should include 'dict' phase");
    assert.ok(phases.has('voice'), "should include 'voice' phase");
    for (const call of calls) {
      assert.ok(
        call.phase === 'dict' || call.phase === 'voice',
        `phase should be 'dict' or 'voice', got: '${call.phase}'`
      );
    }
  });

  // ---------- 3. onProgress に file 情報が含まれる -----------------------------------

  it('onProgress に file 情報が含まれる', async () => {
    // Arrange
    const calls = [];
    const dm = new DictManager();

    // Act
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    // Assert
    for (const call of calls) {
      assert.equal(typeof call.file, 'string', 'file should be a string');
      assert.ok(call.file.length > 0, 'file should be non-empty');
    }

    // Dict-phase calls should reference known dict filenames.
    const dictFiles = calls
      .filter((c) => c.phase === 'dict')
      .map((c) => c.file);
    for (const file of dictFiles) {
      assert.ok(
        EXPECTED_DICT_FILES.includes(file),
        `dict-phase file '${file}' should be a known dictionary filename`
      );
    }

    // Voice-phase calls should reference the voice key.
    const voiceFiles = calls
      .filter((c) => c.phase === 'voice')
      .map((c) => c.file);
    for (const file of voiceFiles) {
      assert.equal(file, VOICE_KEY, `voice-phase file should be '${VOICE_KEY}'`);
    }
  });

  // ---------- 4. overallPercent が 0 から始まる --------------------------------------

  it('onProgress の overallPercent が 0 から始まる', async () => {
    // Arrange
    const calls = [];
    const dm = new DictManager();

    // Act
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    // Assert
    assert.ok(calls.length > 0, 'should receive at least one callback');
    const firstPercent = calls[0].overallPercent;
    assert.ok(
      firstPercent >= 0 && firstPercent <= Math.round((1 / TOTAL_ITEMS) * 100),
      `first overallPercent should start near 0, got: ${firstPercent}`
    );
  });

  // ---------- 5. overallPercent が最終的に 100 になる --------------------------------

  it('onProgress の overallPercent が最終的に 100 になる', async () => {
    // Arrange
    const calls = [];
    const dm = new DictManager();

    // Act
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    // Assert
    assert.ok(calls.length > 0, 'should receive at least one callback');
    const lastPercent = calls[calls.length - 1].overallPercent;
    assert.equal(lastPercent, 100, 'last overallPercent should be 100');
  });

  // ---------- 6. 全辞書ファイルに対して呼ばれる --------------------------------------

  it('onProgress が全辞書ファイルに対して呼ばれる', async () => {
    // Arrange
    const calls = [];
    const dm = new DictManager();

    // Act
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    // Assert -- dict phase should cover all 8 files
    const dictFilesReported = new Set(
      calls.filter((c) => c.phase === 'dict').map((c) => c.file)
    );
    assert.equal(
      dictFilesReported.size,
      EXPECTED_DICT_FILES.length,
      `should report progress for all ${EXPECTED_DICT_FILES.length} dict files`
    );
    for (const expected of EXPECTED_DICT_FILES) {
      assert.ok(
        dictFilesReported.has(expected),
        `should report progress for '${expected}'`
      );
    }

    // Assert -- voice phase should be present
    const voiceCalls = calls.filter((c) => c.phase === 'voice');
    assert.ok(voiceCalls.length > 0, 'should report progress for voice file');

    // Assert -- total unique items = 8 dict + 1 voice = 9
    const allFilesReported = new Set(calls.map((c) => c.file));
    assert.equal(
      allFilesReported.size,
      TOTAL_ITEMS,
      `should report progress for all ${TOTAL_ITEMS} items (8 dict + 1 voice)`
    );
  });

  // ---------- 7. onProgress を指定しなくてもエラーにならない --------------------------

  it('onProgress を指定しなくてもエラーにならない', async () => {
    // Arrange
    const dm = new DictManager();

    // Act & Assert -- should not throw
    const result = await dm.loadDictionary();
    assert.ok(result.dictFiles, 'should return dictFiles');
    assert.ok(result.voiceData, 'should return voiceData');
  });

  // ---------- 8. onProgress が null でもエラーにならない ------------------------------

  it('onProgress が null でもエラーにならない', async () => {
    // Arrange
    const dm = new DictManager();

    // Act & Assert -- should not throw
    const result = await dm.loadDictionary({ onProgress: null });
    assert.ok(result.dictFiles, 'should return dictFiles');
    assert.ok(result.voiceData, 'should return voiceData');
  });
});
