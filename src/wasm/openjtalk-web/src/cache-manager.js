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
   * Async factory for real IndexedDB usage.
   * Handles indexedDB.open() and onupgradeneeded.
   */
  static async create({ dbName = 'piper-cache', dbVersion = 1, storeName = 'cache' } = {}) {
    const db = await new Promise((resolve, reject) => {
      const req = indexedDB.open(dbName, dbVersion);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(storeName)) {
          db.createObjectStore(storeName, { keyPath: 'key' });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return new CacheManager({ dbFactory: () => db });
  }

  /**
   * @param {{ dbFactory: () => object }} options
   */
  constructor({ dbFactory } = {}) {
    if (typeof dbFactory !== 'function') {
      throw new TypeError('CacheManager requires a dbFactory function');
    }
    this._db = dbFactory();
    if (!this._db || typeof this._db.transaction !== 'function') {
      throw new TypeError('dbFactory must return an object with a transaction() method');
    }
    this._inflight = new Map();
  }

  // ---------------------------------------------------------------------------
  // Internal helpers that wrap the mock/real IDB request objects in Promises.
  // ---------------------------------------------------------------------------

  _store(mode = 'readonly') {
    const tx = this._db.transaction(STORE_NAME, mode);
    return tx.objectStore(STORE_NAME);
  }

  /**
   * Wrap an IDB request (or mock request) into a Promise.
   *
   * Mock requests are plain objects with a `_mock` flag set by MockIndexedDB.
   * Real IDBRequest objects have addEventListener / onsuccess / onerror and
   * must wait for the success/error event before reading `.result`.
   */
  _wrap(request) {
    return new Promise((resolve, reject) => {
      if (!request) {
        resolve(undefined);
        return;
      }

      // Mock requests are tagged with `_mock: true` and can be resolved
      // synchronously because the underlying Map operations are instant.
      if (request._mock) {
        resolve(request.result);
        return;
      }

      // Real IDBRequest — wait for completion via events.
      if (typeof request.addEventListener === 'function') {
        request.addEventListener('success', () => resolve(request.result));
        request.addEventListener('error', () => reject(request.error));
        return;
      }

      // Legacy fallback: onsuccess / onerror property assignment.
      // This path is kept for older IDB shims that expose settable onsuccess/onerror
      // but lack addEventListener.  If neither mechanism is available the promise
      // would hang forever, so we reject early.
      if (typeof request.onsuccess === 'undefined'
          && !('onsuccess' in request)
          && typeof Object.getOwnPropertyDescriptor(
               Object.getPrototypeOf(request) || request, 'onsuccess'
             ) === 'undefined') {
        reject(new TypeError(
          'IDB request object has no supported completion mechanism (_mock, addEventListener, or settable onsuccess)'
        ));
        return;
      }
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
   *
   * @param {string} key
   * @param {string} version
   * @param {function(): Promise<ArrayBuffer>} fetcherFn
   * @param {{ priority?: string }} options
   */
  async getOrFetch(key, version, fetcherFn, { priority = 'medium' } = {}) {
    const entry = await this.get(key);
    if (entry && entry.version === version) {
      return entry.data;
    }

    // Inflight deduplication: if another caller is already fetching the same
    // key+version, return the existing promise instead of issuing a second fetch.
    const inflightKey = `${key}@${version}`;
    if (this._inflight.has(inflightKey)) {
      return this._inflight.get(inflightKey);
    }

    const promise = fetcherFn()
      .then(async (data) => {
        await this.set(key, data, { version, priority });
        return data;
      })
      .finally(() => {
        this._inflight.delete(inflightKey);
      });

    this._inflight.set(inflightKey, promise);
    return promise;
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
