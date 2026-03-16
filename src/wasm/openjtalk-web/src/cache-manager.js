/**
 * CacheManager — IndexedDB-backed cache with version management and eviction.
 *
 * Works with both real IndexedDB and the lightweight MockIndexedDB used in tests.
 */

const STORE_NAME = 'cache';
const IOS_QUOTA = 50 * 1024 * 1024; // 50 MB

const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };

export class CacheManager {
  /**
   * @param {{ dbFactory: () => object }} options
   */
  constructor({ dbFactory } = {}) {
    this._db = dbFactory();
  }

  // ---------------------------------------------------------------------------
  // Internal helpers that wrap the mock/real IDB request objects in Promises.
  // ---------------------------------------------------------------------------

  _store(mode = 'readonly') {
    const tx = this._db.transaction(STORE_NAME, mode);
    return tx.objectStore();
  }

  _wrap(request) {
    // MockIndexedDB sets `result` synchronously (if present at all), so we can
    // resolve immediately.  For real IDB we fall back to onsuccess / onerror.
    return new Promise((resolve, reject) => {
      if (!request) {
        resolve(undefined);
        return;
      }
      // The mock returns plain objects with `result` (for get/count/getAll) or
      // without it (for put/delete).  Use `'result' in request` to distinguish
      // from the case where result is genuinely `undefined` (get miss).
      if ('result' in request) {
        resolve(request.result);
        return;
      }
      // put / delete in the mock have no `result` key — just resolve.
      if (request.onsuccess === null && request.onerror === null) {
        resolve(undefined);
        return;
      }
      // Fallback for real IDB (onsuccess / onerror pattern)
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Store data under `key` with metadata.
   *
   * @param {string} key
   * @param {ArrayBuffer} data
   * @param {{ version: string, priority?: string }} meta
   */
  async set(key, data, { version, priority = 'medium' } = {}) {
    const byteLength = data && data.byteLength ? data.byteLength : 0;

    // Check quota BEFORE writing.
    const usage = await this.getUsage();
    // When overwriting, subtract the old entry's size.
    const existing = await this.get(key);
    const existingSize = existing && existing.data && existing.data.byteLength
      ? existing.data.byteLength : 0;
    const projectedUsed = usage.used - existingSize + byteLength;

    if (projectedUsed > IOS_QUOTA) {
      // Attempt eviction of low-priority items first.
      await this._evict(projectedUsed - IOS_QUOTA);

      // Re-check after eviction.
      const usageAfter = await this.getUsage();
      const existingAfter = await this.get(key);
      const existingSizeAfter = existingAfter && existingAfter.data && existingAfter.data.byteLength
        ? existingAfter.data.byteLength : 0;
      const projectedAfter = usageAfter.used - existingSizeAfter + byteLength;

      if (projectedAfter > IOS_QUOTA) {
        throw new Error(`Cache quota exceeded: cannot store ${byteLength} bytes (storage limit ${IOS_QUOTA})`);
      }
    }

    const store = this._store('readwrite');
    const record = {
      key,
      data,
      version,
      priority,
      storedAt: Date.now(),
    };
    await this._wrap(store.put(record));
  }

  /**
   * Retrieve a cached entry. Returns `{ version, data, ... }` or `null`.
   */
  async get(key) {
    const store = this._store('readonly');
    const result = await this._wrap(store.get(key));
    return result || null;
  }

  /**
   * Remove a single key.
   */
  async delete(key) {
    const store = this._store('readwrite');
    await this._wrap(store.delete(key));
  }

  /**
   * Returns `true` if `key` exists and its stored version matches `version`.
   */
  async isValid(key, version) {
    const entry = await this.get(key);
    if (!entry) return false;
    return entry.version === version;
  }

  /**
   * Returns `{ used, quota }` where `used` is the sum of all stored
   * ArrayBuffer byte lengths.
   */
  async getUsage() {
    const store = this._store('readonly');
    const all = await this._wrap(store.getAll());
    let used = 0;
    for (const entry of all) {
      if (entry.data && entry.data.byteLength) {
        used += entry.data.byteLength;
      }
    }
    return { used, quota: IOS_QUOTA };
  }

  /**
   * Remove all cached entries.
   */
  async clear() {
    const keys = await this.getKeys();
    for (const key of keys) {
      await this.delete(key);
    }
  }

  /**
   * Return an array of all stored keys.
   */
  async getKeys() {
    const store = this._store('readonly');
    const all = await this._wrap(store.getAll());
    return all.map((entry) => entry.key);
  }

  /**
   * If the cache contains `key` at the given `version`, return cached data.
   * Otherwise call `fetcherFn()`, cache the result, and return it.
   */
  async getOrFetch(key, version, fetcherFn) {
    const valid = await this.isValid(key, version);
    if (valid) {
      const entry = await this.get(key);
      return entry.data;
    }
    const data = await fetcherFn();
    await this.set(key, data, { version });
    return data;
  }

  // ---------------------------------------------------------------------------
  // Eviction
  // ---------------------------------------------------------------------------

  /**
   * Try to free at least `bytesNeeded` by evicting low-priority entries first,
   * then medium. High-priority entries are never evicted.
   */
  async _evict(bytesNeeded) {
    const store = this._store('readonly');
    const all = await this._wrap(store.getAll());

    // Sort: low priority first, then medium. High is never evicted.
    const evictable = all
      .filter((e) => (e.priority || 'medium') !== 'high')
      .sort((a, b) => {
        const pa = PRIORITY_ORDER[a.priority || 'medium'] || 1;
        const pb = PRIORITY_ORDER[b.priority || 'medium'] || 1;
        if (pa !== pb) return pb - pa; // higher numeric = lower priority = evict first
        return (a.storedAt || 0) - (b.storedAt || 0); // oldest first within same priority
      });

    let freed = 0;
    for (const entry of evictable) {
      if (freed >= bytesNeeded) break;
      await this.delete(entry.key);
      freed += entry.data && entry.data.byteLength ? entry.data.byteLength : 0;
    }
  }
}
