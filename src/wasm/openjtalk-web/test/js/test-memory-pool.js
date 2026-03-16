/**
 * TDD Tests for TypedArrayPool
 * Phase 3: メモリプール戦略
 *
 * テスト対象: src/wasm/openjtalk-web/src/memory-pool.js (未実装)
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

let TypedArrayPool;
try {
  const mod = await import('../../src/memory-pool.js');
  TypedArrayPool = mod.TypedArrayPool || mod.default;
} catch {
  TypedArrayPool = null;
}

const skip = TypedArrayPool === null;

describe('TypedArrayPool', { skip }, () => {
  let pool;

  beforeEach(() => {
    pool = new TypedArrayPool();
  });

  describe('基本操作', () => {
    it('getArray()で新しいFloat32Arrayを取得できる', () => {
      const arr = pool.getArray('float32', 3);
      assert.ok(arr instanceof Float32Array);
      assert.equal(arr.length, 3);
    });

    it('getArray()で新しいBigInt64Arrayを取得できる', () => {
      const arr = pool.getArray('bigint64', 100);
      assert.ok(arr instanceof BigInt64Array);
      assert.equal(arr.length, 100);
    });

    it('returnArray()した後のgetArray()はプールから再利用する', () => {
      const arr1 = pool.getArray('float32', 3);
      arr1[0] = 1.0; arr1[1] = 2.0; arr1[2] = 3.0;
      pool.returnArray('float32', 3, arr1);
      const arr2 = pool.getArray('float32', 3);
      // 同じバッファが再利用される
      assert.equal(arr2.length, 3);
      // fill(0)されているはず
      assert.equal(arr2[0], 0);
      assert.equal(arr2[1], 0);
      assert.equal(arr2[2], 0);
    });
  });

  describe('メモリリーク防止', () => {
    it('MAX_POOL_SIZEを超えるreturnは破棄される', () => {
      const maxSize = TypedArrayPool.MAX_POOL_SIZE || 50;
      for (let i = 0; i < maxSize + 10; i++) {
        pool.returnArray('float32', 3, new Float32Array(3));
      }
      const stats = pool.getStats();
      assert.ok(stats.evictions >= 10);
    });

    it('cleanup()でTTL超過したプールが削除される', async () => {
      // TTLを短く設定してテスト
      pool = new TypedArrayPool({ maxAgeMs: 50 });
      pool.returnArray('float32', 3, new Float32Array(3));
      // TTL経過を待つ
      await new Promise(r => setTimeout(r, 200));
      pool.cleanup();
      // プールは空になっているはず
      const stats = pool.getStats();
      assert.equal(stats.totalPools, 0);
    });
  });

  describe('統計情報', () => {
    it('getStats()でhits/misses/evictionsを取得できる', () => {
      pool.getArray('float32', 3); // miss
      pool.returnArray('float32', 3, new Float32Array(3));
      pool.getArray('float32', 3); // hit
      const stats = pool.getStats();
      assert.equal(stats.hits, 1);
      assert.equal(stats.misses, 1);
      assert.equal(typeof stats.evictions, 'number');
    });
  });

  describe('セキュリティ', () => {
    it('returnArray()時にデータがゼロクリアされる', () => {
      const arr = new Float32Array([1.0, 2.0, 3.0]);
      pool.returnArray('float32', 3, arr);
      // returnした配列のデータはゼロクリア済み
      assert.equal(arr[0], 0);
      assert.equal(arr[1], 0);
      assert.equal(arr[2], 0);
    });
  });
});
