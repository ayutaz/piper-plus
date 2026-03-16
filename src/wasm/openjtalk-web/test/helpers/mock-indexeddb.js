/**
 * Lightweight MockIndexedDB for Node.js tests.
 * Tagged with _mock flag for CacheManager._wrap() compatibility.
 */
export class MockIndexedDB {
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
