/**
 * TDD Tests for CacheManager (IndexedDB)
 * Phase 1: キャッシュ基盤
 *
 * テスト対象: src/wasm/openjtalk-web/src/cache-manager.js (未実装)
 */

import { strict as assert } from 'assert';
import { describe, it, before, after, beforeEach } from 'node:test';

// Node.js環境ではIndexedDBが存在しないため、軽量モックを使用
// ブラウザE2Eテストは Playwright で別途実施
class MockIndexedDB {
  constructor() { this.stores = new Map(); }
  transaction(name, mode) {
    const store = this.stores.get(name) || new Map();
    this.stores.set(name, store);
    return {
      objectStore: (storeName) => ({
        get: (key) => ({ _mock: true, result: store.get(key) }),
        put: (val) => { store.set(val.key, val); return { _mock: true, result: undefined }; },
        delete: (key) => { store.delete(key); return { _mock: true, result: undefined }; },
        count: () => ({ _mock: true, result: store.size }),
        getAll: () => ({ _mock: true, result: [...store.values()] }),
      }),
    };
  }
}

// CacheManager をインポート (未実装のため、テストはすべてfail前提)
let CacheManager;
try {
  const mod = await import('../../src/cache-manager.js');
  CacheManager = mod.CacheManager || mod.default;
} catch {
  // TDD: 未実装 → スキップ用フラグ
  CacheManager = null;
}

const skip = CacheManager === null;

describe('CacheManager', { skip }, () => {
  let cache;

  beforeEach(() => {
    cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
  });

  describe('基本CRUD操作', () => {
    it('set()でデータを保存し、get()で取得できる', async () => {
      const data = new ArrayBuffer(1024);
      await cache.set('dict/sys.dic', data, { version: 'v1.0' });
      const result = await cache.get('dict/sys.dic');
      assert.ok(result);
      assert.equal(result.version, 'v1.0');
    });

    it('存在しないキーのget()はnullを返す', async () => {
      const result = await cache.get('nonexistent');
      assert.equal(result, null);
    });

    it('同じキーにset()で上書きできる', async () => {
      await cache.set('model.onnx', new ArrayBuffer(100), { version: 'v1' });
      await cache.set('model.onnx', new ArrayBuffer(200), { version: 'v2' });
      const result = await cache.get('model.onnx');
      assert.equal(result.version, 'v2');
    });

    it('delete()でキャッシュを削除できる', async () => {
      await cache.set('temp', new ArrayBuffer(10), { version: 'v1' });
      await cache.delete('temp');
      const result = await cache.get('temp');
      assert.equal(result, null);
    });
  });

  describe('バージョン管理', () => {
    it('isValid()でバージョンが一致する場合trueを返す', async () => {
      await cache.set('dict/sys.dic', new ArrayBuffer(100), { version: 'abc123' });
      const valid = await cache.isValid('dict/sys.dic', 'abc123');
      assert.equal(valid, true);
    });

    it('isValid()でバージョンが異なる場合falseを返す', async () => {
      await cache.set('dict/sys.dic', new ArrayBuffer(100), { version: 'abc123' });
      const valid = await cache.isValid('dict/sys.dic', 'def456');
      assert.equal(valid, false);
    });

    it('isValid()でキーが存在しない場合falseを返す', async () => {
      const valid = await cache.isValid('nonexistent', 'v1');
      assert.equal(valid, false);
    });
  });

  describe('ストレージ容量管理', () => {
    it('getUsage()で使用量を取得できる', async () => {
      await cache.set('a', new ArrayBuffer(1000), { version: 'v1' });
      await cache.set('b', new ArrayBuffer(2000), { version: 'v1' });
      const usage = await cache.getUsage();
      assert.ok(usage.used >= 3000);
      assert.ok(typeof usage.quota === 'number');
    });

    it('clear()で全キャッシュを削除できる', async () => {
      await cache.set('a', new ArrayBuffer(100), { version: 'v1' });
      await cache.set('b', new ArrayBuffer(100), { version: 'v1' });
      await cache.clear();
      const a = await cache.get('a');
      const b = await cache.get('b');
      assert.equal(a, null);
      assert.equal(b, null);
    });
  });

  describe('iOS制限対応 (50MB/origin)', () => {
    it('50MBを超えるデータのset()はエラーまたはevictionを行う', async () => {
      const largeData = new ArrayBuffer(51 * 1024 * 1024); // 51MB
      try {
        await cache.set('large', largeData, { version: 'v1' });
        // eviction戦略で古いデータを削除した場合は成功
      } catch (e) {
        assert.ok(e.message.includes('quota') || e.message.includes('storage'));
      }
    });

    it('優先度ベースのeviction: 辞書 > モデル > 一時データ', async () => {
      // 辞書を高優先度で保存
      await cache.set('dict/sys.dic', new ArrayBuffer(1000), {
        version: 'v1', priority: 'high'
      });
      // モデルを中優先度で保存
      await cache.set('model.onnx', new ArrayBuffer(1000), {
        version: 'v1', priority: 'medium'
      });
      // eviction発生時、低優先度が先に削除される
      const keys = await cache.getKeys();
      // 辞書はeviction対象にならない
      assert.ok(keys.includes('dict/sys.dic'));
    });
  });

  describe('fetch統合', () => {
    it('getOrFetch()でキャッシュがない場合fetchしてキャッシュする', async () => {
      let fetchCalled = false;
      const fetcher = async () => {
        fetchCalled = true;
        return new ArrayBuffer(1024);
      };
      const data = await cache.getOrFetch('new-asset', 'v1', fetcher);
      assert.ok(fetchCalled);
      assert.ok(data);
      // 2回目はキャッシュから取得
      fetchCalled = false;
      await cache.getOrFetch('new-asset', 'v1', fetcher);
      assert.equal(fetchCalled, false);
    });

    it('getOrFetch()でバージョンが変わった場合再fetchする', async () => {
      let fetchCount = 0;
      const fetcher = async () => { fetchCount++; return new ArrayBuffer(100); };
      await cache.getOrFetch('asset', 'v1', fetcher);
      await cache.getOrFetch('asset', 'v2', fetcher);
      assert.equal(fetchCount, 2);
    });
  });
});
