/**
 * TDD Tests for DictManager cache lifecycle (isCached / clearCache)
 *
 * テスト対象: src/wasm/openjtalk-web/src/dict-manager.js
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';
import {
  DICT_FILES,
  installIndexedDBMock,
  installFetchMock,
  installCryptoMock,
  cleanup,
  MockIDBDatabase,
} from './helpers/dict-mock.js';

// ---- Import SUT ----------------------------------------------------------------

let DictManager;
try {
  const mod = await import('../../src/dict-manager.js');
  DictManager = mod.DictManager || mod.default;
} catch {
  DictManager = null;
}

const skip = DictManager === null;

// ---- Tests ---------------------------------------------------------------------

describe('DictManager キャッシュライフサイクル', { skip }, () => {
  let fetched;

  beforeEach(() => {
    installIndexedDBMock();
    installCryptoMock();
    fetched = installFetchMock();
  });

  afterEach(() => {
    fetched = [];
    cleanup();
  });

  it('初期状態で isCached は false', async () => {
    const dm = new DictManager();
    assert.equal(await dm.isCached(), false);
  });

  it('loadDictionary 後に isCached は true を返す', async () => {
    const dm = new DictManager();
    await dm.loadDictionary();
    assert.equal(await dm.isCached(), true);
  });

  it('clearCache 後に isCached は false を返す', async () => {
    const dm = new DictManager();
    await dm.loadDictionary();
    await dm.clearCache();
    assert.equal(await dm.isCached(), false);
  });

  it('clearCache 後に再度 loadDictionary すると fetch が実行される', async () => {
    const dm = new DictManager();
    await dm.loadDictionary();
    const countAfterFirst = fetched.length;

    await dm.clearCache();
    await dm.loadDictionary();

    assert.ok(
      fetched.length > countAfterFirst,
      'Additional fetch calls after cache clear'
    );
  });

  it('2回目の loadDictionary はキャッシュを使用する', async () => {
    const dm = new DictManager();
    await dm.loadDictionary();
    const countAfterFirst = fetched.length;

    await dm.loadDictionary();
    assert.equal(fetched.length, countAfterFirst, 'No new fetches on cache hit');
  });

  it('カスタム cachePrefix で独立したキャッシュが作られる', async () => {
    const dbInstances = new Map();
    globalThis.indexedDB = {
      open(name) {
        if (!dbInstances.has(name)) dbInstances.set(name, new MockIDBDatabase());
        const db = dbInstances.get(name);
        const req = { result: null, onsuccess: null, onerror: null, onupgradeneeded: null };
        Promise.resolve().then(() => {
          if (req.onupgradeneeded) req.onupgradeneeded({ target: { result: db } });
          req.result = db;
          if (req.onsuccess) req.onsuccess();
        });
        return req;
      },
    };

    const dmA = new DictManager({ cachePrefix: 'prefix-a' });
    const dmB = new DictManager({ cachePrefix: 'prefix-b' });

    await dmA.loadDictionary();
    assert.equal(await dmB.isCached(), false);
  });

  it('clearCache が他のキャッシュに影響しない', async () => {
    const dbInstances = new Map();
    globalThis.indexedDB = {
      open(name) {
        if (!dbInstances.has(name)) dbInstances.set(name, new MockIDBDatabase());
        const db = dbInstances.get(name);
        const req = { result: null, onsuccess: null, onerror: null, onupgradeneeded: null };
        Promise.resolve().then(() => {
          if (req.onupgradeneeded) req.onupgradeneeded({ target: { result: db } });
          req.result = db;
          if (req.onsuccess) req.onsuccess();
        });
        return req;
      },
    };

    const dmA = new DictManager({ cachePrefix: 'prefix-a' });
    const dmB = new DictManager({ cachePrefix: 'prefix-b' });

    await dmA.loadDictionary();
    await dmB.loadDictionary();
    await dmA.clearCache();

    assert.equal(await dmA.isCached(), false);
    assert.equal(await dmB.isCached(), true);
  });

  it('キャッシュされた辞書ファイルが正しいデータを返す', async () => {
    const dm = new DictManager();
    const first = await dm.loadDictionary();
    const second = await dm.loadDictionary();

    for (const file of DICT_FILES) {
      assert.ok(second.dictFiles[file] instanceof ArrayBuffer, `${file} is ArrayBuffer`);
      assert.equal(
        second.dictFiles[file].byteLength,
        first.dictFiles[file].byteLength,
        `${file} cached size matches`
      );
    }

    assert.ok(second.voiceData instanceof ArrayBuffer);
    assert.equal(second.voiceData.byteLength, first.voiceData.byteLength);
  });
});
