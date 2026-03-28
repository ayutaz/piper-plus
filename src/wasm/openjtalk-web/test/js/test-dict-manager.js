/**
 * TDD Tests for DictManager (tar.gz ダウンロード + IndexedDB キャッシュ)
 *
 * テスト対象: src/wasm/openjtalk-web/src/dict-manager.js
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';
import {
  DICT_FILES,
  DICT_TAR_GZ_URL,
  VOICE_URL,
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

describe('DictManager', { skip }, () => {
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

  // ---------- 1. 構築 -------------------------------------------------------------

  describe('構築', () => {
    it('デフォルトオプションで構築可能', () => {
      const dm = new DictManager();
      assert.ok(dm, 'DictManager instance should be truthy');
    });

    it('カスタム cachePrefix を設定すると indexedDB.open に渡される', async () => {
      const state = installIndexedDBMock();
      const dm = new DictManager({ cachePrefix: 'my-custom-prefix' });
      await dm.loadDictionary();
      assert.equal(state.lastDbName, 'my-custom-prefix');
    });

    it('cachePrefix 未指定時はデフォルト名で indexedDB.open が呼ばれる', async () => {
      const state = installIndexedDBMock();
      const dm = new DictManager();
      await dm.loadDictionary();
      assert.equal(state.lastDbName, 'piper-plus-dict');
    });
  });

  // ---------- 2. resolveUrls ------------------------------------------------------

  describe('resolveUrls', () => {
    it('デフォルトで GitHub Releases URL と HuggingFace voice URL を返す', () => {
      const dm = new DictManager();
      const { dictUrl, voiceUrl } = dm.resolveUrls();
      assert.ok(dictUrl.includes('github.com/r9y9/open_jtalk'));
      assert.ok(dictUrl.endsWith('.tar.gz'));
      assert.ok(voiceUrl.includes('huggingface.co'));
    });

    it('カスタム dictUrl を渡すと上書きされる', () => {
      const dm = new DictManager();
      const { dictUrl } = dm.resolveUrls({ dictUrl: 'https://example.com/dict.tar.gz' });
      assert.equal(dictUrl, 'https://example.com/dict.tar.gz');
    });

    it('カスタム voiceUrl を渡すと上書きされる', () => {
      const dm = new DictManager();
      const { voiceUrl } = dm.resolveUrls({ voiceUrl: 'https://example.com/voice.htsvoice' });
      assert.equal(voiceUrl, 'https://example.com/voice.htsvoice');
    });
  });

  // ---------- 3. loadDictionary ---------------------------------------------------

  describe('loadDictionary', () => {
    it('tar.gz URL と voice URL の2つだけ fetch される', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      assert.equal(fetched.length, 2, 'Should fetch tar.gz + voice');
      assert.ok(fetched[0].includes('.tar.gz'), 'First fetch is tar.gz');
      assert.ok(fetched[1].includes('htsvoice'), 'Second fetch is voice');
    });

    it('返却される dictFiles に全8ファイルが含まれる', async () => {
      const dm = new DictManager();
      const { dictFiles } = await dm.loadDictionary();
      const keys = new Set(Object.keys(dictFiles));
      assert.deepEqual(keys, new Set(DICT_FILES));
    });

    it('返却される dictFiles の各値が ArrayBuffer である', async () => {
      const dm = new DictManager();
      const { dictFiles } = await dm.loadDictionary();
      for (const file of DICT_FILES) {
        assert.ok(dictFiles[file] instanceof ArrayBuffer, `${file} should be ArrayBuffer`);
        assert.ok(dictFiles[file].byteLength > 0, `${file} should be non-empty`);
      }
    });

    it('voiceData が ArrayBuffer として返却される', async () => {
      const dm = new DictManager();
      const { voiceData } = await dm.loadDictionary();
      assert.ok(voiceData instanceof ArrayBuffer);
      assert.ok(voiceData.byteLength > 0);
    });
  });

  // ---------- 4. isCached / clearCache -------------------------------------------

  describe('isCached / clearCache', () => {
    it('初回は isCached が false', async () => {
      const dm = new DictManager();
      assert.equal(await dm.isCached(), false);
    });

    it('loadDictionary 後に isCached が true', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      assert.equal(await dm.isCached(), true);
    });

    it('clearCache 後に isCached が false に戻る', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      await dm.clearCache();
      assert.equal(await dm.isCached(), false);
    });
  });

  // ---------- 5. キャッシュヒット --------------------------------------------------

  describe('キャッシュ', () => {
    it('2回目の loadDictionary は fetch を呼ばない', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      const firstCount = fetched.length;

      await dm.loadDictionary();
      assert.equal(fetched.length, firstCount, 'No additional fetch on cache hit');
    });

    it('キャッシュから返されたデータが正しい', async () => {
      const dm = new DictManager();
      const first = await dm.loadDictionary();
      const second = await dm.loadDictionary();

      for (const file of DICT_FILES) {
        assert.equal(
          second.dictFiles[file].byteLength,
          first.dictFiles[file].byteLength,
          `${file} size should match`
        );
      }
    });
  });

  // ---------- 6. エラー -----------------------------------------------------------

  describe('エラー', () => {
    it('fetch が 404 の場合にリジェクトされる', async () => {
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

    it('ネットワークエラーの場合に TypeError がスローされる', async () => {
      cleanup();
      installIndexedDBMock();
      installCryptoMock();
      fetched = installFetchMock({ shouldReject: true });

      const dm = new DictManager();
      await assert.rejects(() => dm.loadDictionary(), TypeError);
    });
  });
});
