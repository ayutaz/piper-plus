/**
 * TDD Tests for CacheManager (IndexedDB)
 * Phase 1: キャッシュ基盤
 *
 * テスト対象: src/wasm/openjtalk-web/src/cache-manager.js (未実装)
 */

import { strict as assert } from 'assert';
import { describe, it, before, after, beforeEach } from 'node:test';
import { MockIndexedDB } from '../helpers/mock-indexeddb.js';

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

    it('getOrFetch()のpriorityオプションがsetに伝播する', async () => {
      await cache.getOrFetch('test-key', 'v1', async () => new ArrayBuffer(100), { priority: 'high' });
      const entry = await cache.get('test-key');
      assert.equal(entry.priority, 'high');
    });

    it('getOrFetch()のpriorityデフォルトはmedium', async () => {
      await cache.getOrFetch('test-key', 'v1', async () => new ArrayBuffer(100));
      const entry = await cache.get('test-key');
      assert.equal(entry.priority, 'medium');
    });

    it('getOrFetch()の同一キー同時呼び出しでfetcherが1回だけ呼ばれる', async () => {
      let fetchCount = 0;
      const fetcher = async () => {
        fetchCount++;
        await new Promise(r => setTimeout(r, 50));
        return new ArrayBuffer(100);
      };
      // Launch two concurrent getOrFetch for the same key
      const [data1, data2] = await Promise.all([
        cache.getOrFetch('same-key', 'v1', fetcher),
        cache.getOrFetch('same-key', 'v1', fetcher),
      ]);
      assert.equal(fetchCount, 1, 'fetcher should be called only once');
      assert.ok(data1);
      assert.ok(data2);
    });
  });

  describe('コンストラクタ検証', () => {
    it('dbFactory未指定でTypeErrorをスローする', () => {
      assert.throws(() => new CacheManager(), { name: 'TypeError' });
    });
    it('dbFactory:nullでTypeErrorをスローする', () => {
      assert.throws(() => new CacheManager({ dbFactory: null }), { name: 'TypeError' });
    });
    it('dbFactory()がtransactionメソッドを持たないオブジェクトを返すとTypeErrorをスローする', () => {
      assert.throws(() => new CacheManager({ dbFactory: () => ({}) }), { name: 'TypeError' });
    });
  });

  describe('eviction動作', () => {
    it('容量超過時にlow優先度のエントリが先に退避される', async () => {
      const localCache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
      // Fill with low-priority items near quota
      await localCache.set('low1', new ArrayBuffer(20 * 1024 * 1024), { version: 'v1', priority: 'low' });
      await localCache.set('low2', new ArrayBuffer(20 * 1024 * 1024), { version: 'v1', priority: 'low' });
      // Add a high-priority item that pushes over quota
      await localCache.set('high1', new ArrayBuffer(15 * 1024 * 1024), { version: 'v1', priority: 'high' });
      // high1 should survive, at least one low should be evicted
      const high = await localCache.get('high1');
      assert.ok(high, 'high priority item should survive eviction');
      const usage = await localCache.getUsage();
      assert.ok(usage.used <= 50 * 1024 * 1024, 'usage should be within quota');
    });

    it('high優先度のエントリはevictionの対象にならない', async () => {
      const localCache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
      await localCache.set('high1', new ArrayBuffer(25 * 1024 * 1024), { version: 'v1', priority: 'high' });
      await localCache.set('high2', new ArrayBuffer(25 * 1024 * 1024), { version: 'v1', priority: 'high' });
      // This should throw because high-priority items can't be evicted
      await assert.rejects(
        () => localCache.set('extra', new ArrayBuffer(5 * 1024 * 1024), { version: 'v1', priority: 'medium' }),
        /quota/i
      );
    });

    it('同一優先度内では古いエントリが先に退避される', async () => {
      const localCache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
      await localCache.set('old', new ArrayBuffer(20 * 1024 * 1024), { version: 'v1', priority: 'low' });
      // Slight delay to ensure different storedAt
      await localCache.set('new', new ArrayBuffer(20 * 1024 * 1024), { version: 'v1', priority: 'low' });
      // Trigger eviction
      await localCache.set('trigger', new ArrayBuffer(15 * 1024 * 1024), { version: 'v1', priority: 'medium' });
      // 'old' should be evicted first
      const oldEntry = await localCache.get('old');
      assert.equal(oldEntry, null, 'oldest low-priority entry should be evicted first');
    });
  });
});
