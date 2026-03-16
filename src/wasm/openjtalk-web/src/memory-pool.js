/**
 * TypedArrayPool — reusable typed-array memory pool.
 * Phase 3: メモリプール戦略
 */

const TYPE_CTORS = {
  float32: Float32Array,
  float64: Float64Array,
  int8: Int8Array,
  int16: Int16Array,
  int32: Int32Array,
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  bigint64: BigInt64Array,
  biguint64: BigUint64Array,
};

const BIGINT_TYPES = new Set(['bigint64', 'biguint64']);

export class TypedArrayPool {
  static MAX_POOL_SIZE = 50;

  /** @param {{ maxAgeMs?: number }} opts */
  constructor({ maxAgeMs = 60_000 } = {}) {
    this._maxAgeMs = maxAgeMs;
    /** @type {Map<string, Array<{ array: TypedArray, ts: number }>>} */
    this._buckets = new Map();
    this._hits = 0;
    this._misses = 0;
    this._evictions = 0;
  }

  /**
   * Return a typed array of the requested type and length.
   * Reuses a pooled buffer when available.
   */
  getArray(type, length) {
    const key = `${type}:${length}`;
    const bucket = this._buckets.get(key);
    if (bucket && bucket.length > 0) {
      this._hits++;
      return bucket.pop().array;
    }
    this._misses++;
    const Ctor = TYPE_CTORS[type];
    if (!Ctor) {
      throw new Error(`Unknown typed-array type: ${type}`);
    }
    return new Ctor(length);
  }

  /**
   * Return an array to the pool for future reuse.
   * The array is zero-cleared before storing.
   */
  returnArray(type, length, array) {
    const Ctor = TYPE_CTORS[type];
    if (!Ctor) throw new Error(`Unknown typed-array type: ${type}`);
    if (!(array instanceof Ctor)) throw new TypeError(`Expected ${Ctor.name} but got ${array.constructor.name}`);
    if (array.length !== length) throw new RangeError(`Expected length ${length} but got ${array.length}`);

    // Zero-clear — BigInt arrays need 0n
    if (BIGINT_TYPES.has(type)) {
      array.fill(0n);
    } else {
      array.fill(0);
    }

    const key = `${type}:${length}`;
    let bucket = this._buckets.get(key);
    if (!bucket) {
      bucket = [];
      this._buckets.set(key, bucket);
    }

    // Evict oldest entry if the pool-wide total exceeds MAX_POOL_SIZE
    if (this._totalEntries() >= TypedArrayPool.MAX_POOL_SIZE) {
      this._evictOldest();
    }

    bucket.push({ array, ts: Date.now() });
  }

  /** Remove all pool entries older than maxAgeMs. */
  cleanup() {
    const now = Date.now();
    for (const [key, bucket] of this._buckets) {
      const kept = bucket.filter(e => (now - e.ts) < this._maxAgeMs);
      if (kept.length === 0) {
        this._buckets.delete(key);
      } else {
        this._buckets.set(key, kept);
      }
    }
  }

  /** Return pool statistics. */
  getStats() {
    let totalPools = 0;
    for (const bucket of this._buckets.values()) {
      if (bucket.length > 0) totalPools++;
    }
    return {
      hits: this._hits,
      misses: this._misses,
      evictions: this._evictions,
      totalPools,
    };
  }

  // --- internal helpers ---

  _totalEntries() {
    let n = 0;
    for (const b of this._buckets.values()) n += b.length;
    return n;
  }

  _evictOldest() {
    let oldestTs = Infinity;
    let oldestKey = null;
    let oldestIdx = -1;

    for (const [key, bucket] of this._buckets) {
      for (let i = 0; i < bucket.length; i++) {
        if (bucket[i].ts < oldestTs) {
          oldestTs = bucket[i].ts;
          oldestKey = key;
          oldestIdx = i;
        }
      }
    }

    if (oldestKey !== null) {
      const bucket = this._buckets.get(oldestKey);
      bucket.splice(oldestIdx, 1);
      if (bucket.length === 0) this._buckets.delete(oldestKey);
      this._evictions++;
    }
  }
}
