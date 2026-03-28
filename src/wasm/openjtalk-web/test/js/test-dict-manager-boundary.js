/**
 * TDD Tests for DictManager -- 境界値・エラーケース
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

describe('DictManager 境界値・エラーケース', { skip }, () => {
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

  it('空の cachePrefix でデフォルト値が使用される', async () => {
    const state = installIndexedDBMock();
    const dm = new DictManager({ cachePrefix: '' });
    await dm.loadDictionary();
    assert.equal(state.lastDbName, 'piper-plus-dict');
  });

  it('ネットワークエラーで TypeError がスローされる', async () => {
    cleanup();
    installIndexedDBMock();
    installCryptoMock();
    fetched = installFetchMock({ shouldReject: true });

    const dm = new DictManager();
    await assert.rejects(() => dm.loadDictionary(), TypeError);
  });

  it('tar.gz が 404 の場合にエラー', async () => {
    cleanup();
    installIndexedDBMock();
    installCryptoMock();
    fetched = installFetchMock({ shouldFail: true });

    const dm = new DictManager();
    await assert.rejects(
      () => dm.loadDictionary(),
      (err) => err.message.includes('404')
    );
  });

  it('SHA-256 不一致の場合にエラー', async () => {
    cleanup();
    installIndexedDBMock();
    // Monkey-patch digest to return wrong hash (all zeros)
    globalThis.crypto.subtle.digest = async () => new Uint8Array(32).buffer;
    fetched = installFetchMock();

    const dm = new DictManager();
    await assert.rejects(
      () => dm.loadDictionary(),
      (err) => err.message.includes('SHA-256')
    );
  });

  it('大きな辞書ファイルのダウンロード', async () => {
    cleanup();
    installIndexedDBMock();
    installCryptoMock();
    fetched = installFetchMock({ dictFileSize: 10240 });

    const dm = new DictManager();
    const { dictFiles } = await dm.loadDictionary();

    for (const file of DICT_FILES) {
      assert.equal(dictFiles[file].byteLength, 10240, `${file} should be 10240 bytes`);
    }
  });

  it('indexedDB 利用不可の場合', async () => {
    delete globalThis.indexedDB;
    const dm = new DictManager();
    await assert.rejects(() => dm.loadDictionary());
  });

  it('同時に loadDictionary を2回呼んだ場合', async () => {
    const dm = new DictManager();
    const [result1, result2] = await Promise.all([
      dm.loadDictionary(),
      dm.loadDictionary(),
    ]);

    assert.ok(result1.dictFiles);
    assert.ok(result2.dictFiles);

    for (const file of DICT_FILES) {
      assert.ok(result1.dictFiles[file] instanceof ArrayBuffer);
      assert.ok(result2.dictFiles[file] instanceof ArrayBuffer);
    }
  });

  it('カスタム dictUrl を指定した場合', async () => {
    const dm = new DictManager();
    await dm.loadDictionary({
      dictUrl: 'https://example.com/custom-dict.tar.gz',
    });

    assert.ok(
      fetched[0] === 'https://example.com/custom-dict.tar.gz',
      'Custom dict URL should be used'
    );
  });

  it('カスタム voiceUrl を指定した場合', async () => {
    const dm = new DictManager();
    await dm.loadDictionary({
      voiceUrl: 'https://example.com/custom-voice.htsvoice',
    });

    const voiceFetch = fetched.find((u) => u.includes('custom-voice'));
    assert.ok(voiceFetch, 'Custom voice URL should be used');
  });
});
