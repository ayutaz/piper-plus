/**
 * RustWasmAdapter.create() behaviour tests.
 *
 * Nothing in the repository imported `rust-wasm-adapter.js` before this file,
 * so everything past the `await import(url)` on the WASM path — including the
 * Chinese dictionary auto-load — had never executed under test. The
 * `options.wasmLoader` dependency-injection hook makes that reachable without
 * a real WASM build.
 *
 * The Japanese assertions here are a **regression guard for a hard
 * constraint**: the bundled-dictionary (`multilingual`) build must keep
 * producing exactly the Japanese it produces today. `setJapaneseDictionary`
 * replaces the whole Japanese phonemizer, so it must never fire on its own.
 *
 * Run: node --test test/js/test-rust-wasm-adapter.js
 */

import { strict as assert } from "node:assert";
import { describe, it, afterEach } from "node:test";

import { RustWasmAdapter } from "../../src/phonemizer/rust-wasm-adapter.js";
import { installSafeFetch } from "../helpers/safe-mock-fetch.js";

const CONFIG_JSON = JSON.stringify({
  audio: { sample_rate: 22050 },
  espeak: { voice: "ja" },
});

/**
 * Build a mock WASM module whose phonemizer exposes exactly the requested
 * dictionary setters. Which setters exist is the whole point: the adapter is
 * expected to branch on their presence.
 *
 * @param {{ chinese?: boolean, japanese?: boolean, english?: boolean | Function,
 *   languages?: string[] }} opts - `english` may be a replacement setter.
 */
function createMockWasmModule({
  chinese = false,
  japanese = false,
  english = false,
  languages,
} = {}) {
  const calls = { chinese: [], japanese: [], english: [] };

  class WasmPhonemizer {
    constructor(configJson) {
      this.configJson = configJson;
    }

    getSupportedLanguages() {
      return languages ?? ["ja", "en", "zh"];
    }

    free() {}
  }

  if (chinese) {
    WasmPhonemizer.prototype.setChineseDictionary = function (single, phrases) {
      calls.chinese.push([single, phrases]);
    };
  }
  if (japanese) {
    WasmPhonemizer.prototype.setJapaneseDictionary = function (bytes) {
      calls.japanese.push(bytes);
    };
  }
  if (english) {
    WasmPhonemizer.prototype.setEnglishDictionary =
      typeof english === "function"
        ? english
        : function (bytes) {
            calls.english.push(bytes);
          };
  }

  return { module: { WasmPhonemizer }, calls };
}

/** Route table that answers the ZH pinyin dictionaries with real bytes. */
function zhRoutes() {
  return {
    "*pinyin_single.json": { ok: true, arrayBuffer: () => new Uint8Array([1, 2, 3]).buffer },
    "*pinyin_phrases.json": { ok: true, arrayBuffer: () => new Uint8Array([4, 5]).buffer },
  };
}

let activeFetch = null;

afterEach(() => {
  if (activeFetch) {
    activeFetch.restore();
    activeFetch = null;
  }
});

describe("RustWasmAdapter.create() — DI 経路", () => {
  it("wasmLoader を渡すと dynamic import せずに解決する", async () => {
    activeFetch = installSafeFetch({});
    const { module } = createMockWasmModule();

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
    });

    assert.ok(adapter, "create() should resolve with an adapter");
    assert.equal(activeFetch.calls.length, 0, "no network access without dictionaries");
  });

  it("supportedLanguages が getSupportedLanguages() 由来である", async () => {
    activeFetch = installSafeFetch({});
    const { module } = createMockWasmModule({ languages: ["ja", "sv"] });

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
    });

    assert.deepEqual(adapter.supportedLanguages, ["ja", "sv"]);
  });
});

describe("RustWasmAdapter.create() — ZH 辞書の自動ロード (現状の挙動を pin)", () => {
  it("setChineseDictionary があれば 1 回だけ Uint8Array 2 本で呼ばれる", async () => {
    activeFetch = installSafeFetch(zhRoutes());
    const { module, calls } = createMockWasmModule({ chinese: true });

    await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      zhDictBaseUrl: "https://example.test/assets/",
    });

    assert.equal(calls.chinese.length, 1, "setChineseDictionary should be called once");
    const [single, phrases] = calls.chinese[0];
    assert.ok(single instanceof Uint8Array, "single dict should be a Uint8Array");
    assert.ok(phrases instanceof Uint8Array, "phrase dict should be a Uint8Array");
  });

  it("setChineseDictionary が無ければ fetch が 1 回も起きない", async () => {
    activeFetch = installSafeFetch(zhRoutes());
    const { module, calls } = createMockWasmModule({ chinese: false });

    await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      zhDictBaseUrl: "https://example.test/assets/",
    });

    assert.equal(calls.chinese.length, 0);
    assert.equal(activeFetch.calls.length, 0, "no dictionary fetch without the setter");
  });

  it("ZH 辞書の取得に失敗しても create() は解決する", async () => {
    activeFetch = installSafeFetch({});
    const { module, calls } = createMockWasmModule({ chinese: true });

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      zhDictBaseUrl: "https://example.test/assets/",
    });

    assert.ok(adapter, "a missing dictionary must not reject create()");
    assert.equal(calls.chinese.length, 0, "setter must not run with unusable bytes");
  });
});

describe("RustWasmAdapter.create() — JA 辞書は自発的に発火しない (ハード制約)", () => {
  it("setJapaneseDictionary があっても呼ばれない", async () => {
    activeFetch = installSafeFetch({});
    const { module, calls } = createMockWasmModule({ japanese: true });

    await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
    });

    assert.equal(
      calls.japanese.length,
      0,
      "setJapaneseDictionary replaces the entire Japanese phonemizer; firing it " +
        "unasked would change the output of the bundled-dictionary build."
    );
  });

  it("JA 辞書を取りに行く fetch が 1 回も起きない", async () => {
    activeFetch = installSafeFetch({});
    const { module } = createMockWasmModule({ japanese: true, chinese: true });

    await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      zhDictBaseUrl: "https://example.test/assets/",
    });

    const japaneseish = activeFetch.calls
      .map(({ url }) => url)
      .filter((url) => /jdic|naist|japanese|\bja\b/i.test(url));

    assert.deepEqual(japaneseish, [], "no Japanese dictionary should be fetched");
  });
});

describe("RustWasmAdapter.create() — JA 外部辞書の opt-in 投入", () => {
  const JA_URL = "https://example.test/dict/naist-jdic.bin";
  const JA_BYTES = new Uint8Array([9, 8, 7, 6]);

  /** SHA-256 of JA_BYTES, computed at test time so the fixture cannot drift. */
  async function jaSha256() {
    const digest = await crypto.subtle.digest("SHA-256", JA_BYTES);
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  function jaRoutes() {
    return { [JA_URL]: { ok: true, arrayBuffer: () => JA_BYTES.buffer } };
  }

  it("jaDict.url を渡すと setJapaneseDictionary が 1 回だけ呼ばれる", async () => {
    activeFetch = installSafeFetch(jaRoutes());
    const { module, calls } = createMockWasmModule({ japanese: true });

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      jaDict: { url: JA_URL },
    });

    assert.equal(calls.japanese.length, 1);
    assert.ok(calls.japanese[0] instanceof Uint8Array);
    assert.equal(adapter.japaneseDictionaryStatus, "loaded");
  });

  it("sha256 が一致しなければ setJapaneseDictionary を呼ばない", async () => {
    activeFetch = installSafeFetch(jaRoutes());
    const { module, calls } = createMockWasmModule({ japanese: true });

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      jaDict: { url: JA_URL, sha256: "0".repeat(64) },
    });

    assert.equal(calls.japanese.length, 0, "unverified bytes must never reach the setter");
    assert.equal(adapter.japaneseDictionaryStatus, "failed");
  });

  it("sha256 が一致すれば投入される", async () => {
    activeFetch = installSafeFetch(jaRoutes());
    const { module, calls } = createMockWasmModule({ japanese: true });

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      jaDict: { url: JA_URL, sha256: await jaSha256() },
    });

    assert.equal(calls.japanese.length, 1);
    assert.equal(adapter.japaneseDictionaryStatus, "loaded");
  });

  it("取得に失敗しても create() は reject せず、言語リストも変わらない", async () => {
    activeFetch = installSafeFetch({});
    const { module, calls } = createMockWasmModule({ japanese: true });

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      jaDict: { url: JA_URL },
    });

    // Rejecting here would be caught by index.js and drop *both* ja and zh
    // from the WASM path, taking working Chinese down with failed Japanese.
    assert.ok(adapter);
    assert.equal(calls.japanese.length, 0);
    assert.equal(adapter.japaneseDictionaryStatus, "failed");
    assert.deepEqual(adapter.supportedLanguages, ["ja", "en", "zh"]);
  });

  it("setJapaneseDictionary が throw しても create() は解決する", async () => {
    activeFetch = installSafeFetch(jaRoutes());
    const { module } = createMockWasmModule({ japanese: true });
    module.WasmPhonemizer.prototype.setJapaneseDictionary = function () {
      throw new Error("CONFIG_PARSE_ERROR: version mismatch");
    };

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      jaDict: { url: JA_URL },
    });

    assert.ok(adapter);
    assert.equal(adapter.japaneseDictionaryStatus, "failed");
  });

  it("setter を持たないビルドでは fetch せず unsupported を返す", async () => {
    activeFetch = installSafeFetch(jaRoutes());
    const { module } = createMockWasmModule({ japanese: false });

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
      jaDict: { url: JA_URL },
    });

    // The bundled-dictionary build has no setter. Silently ignoring the
    // option left callers unable to tell their dictionary never applied.
    assert.equal(activeFetch.calls.length, 0, "must not download 55 MB it cannot use");
    assert.equal(adapter.japaneseDictionaryStatus, "unsupported");
  });

  it("jaDict を渡さなければ status は not-requested", async () => {
    activeFetch = installSafeFetch({});
    const { module } = createMockWasmModule({ japanese: true });

    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => module,
    });

    assert.equal(adapter.japaneseDictionaryStatus, "not-requested");
  });
});

describe("RustWasmAdapter.loadEnglishDictionary() — 中国語文中の英語・数字 (#847)", () => {
  const CMU = new Map([
    ["one", "W AH1 N"],
    ["hundred", "HH AH1 N D R AH0 D"],
  ]);

  async function createAdapter(opts) {
    activeFetch = installSafeFetch({});
    const mock = createMockWasmModule(opts);
    const adapter = await RustWasmAdapter.create(CONFIG_JSON, {
      wasmLoader: async () => mock.module,
    });
    return { adapter, calls: mock.calls };
  }

  async function withWarnings(fn) {
    const warnings = [];
    const origWarn = console.warn;
    console.warn = (...args) => warnings.push(args.join(" "));
    try {
      return { result: await fn(), warnings };
    } finally {
      console.warn = origWarn;
    }
  }

  it("create() は CMU 辞書を渡さない (呼び出し側が zh と en のモデルでだけ渡す)", async () => {
    const { calls } = await createAdapter({ english: true });
    assert.equal(calls.english.length, 0);
  });

  it("読み込んだ辞書を JSON の bytes で setEnglishDictionary に 1 回渡す", async () => {
    const { adapter, calls } = await createAdapter({ english: true });

    const { result, warnings } = await withWarnings(() =>
      adapter.loadEnglishDictionary(async () => CMU)
    );

    assert.equal(result, "loaded");
    assert.deepEqual(warnings, []);
    assert.equal(calls.english.length, 1);
    assert.ok(calls.english[0] instanceof Uint8Array, "dictionary must be a Uint8Array");
    assert.deepEqual(JSON.parse(new TextDecoder().decode(calls.english[0])), {
      one: "W AH1 N",
      hundred: "HH AH1 N D R AH0 D",
    });
  });

  it("setter を持たないビルドでは辞書を読まず unsupported を返す", async () => {
    const { adapter } = await createAdapter({ english: false });
    let loaded = 0;

    const { result, warnings } = await withWarnings(() =>
      adapter.loadEnglishDictionary(async () => {
        loaded++;
        return CMU;
      })
    );

    assert.equal(result, "unsupported");
    assert.equal(loaded, 0, "no dictionary work for a build that cannot use it");
    assert.deepEqual(warnings, []);
  });

  it("@piper-plus/g2p に loadCmuDict が無ければ警告して failed を返す", async () => {
    const { adapter, calls } = await createAdapter({ english: true });

    const { result, warnings } = await withWarnings(() => adapter.loadEnglishDictionary(undefined));

    assert.equal(result, "failed");
    assert.equal(calls.english.length, 0);
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /loadCmuDict/);
  });

  it("辞書の読み込みや setter が失敗しても reject せず failed を返す", async () => {
    const failing = await createAdapter({ english: true });
    const loadFailure = await withWarnings(() =>
      failing.adapter.loadEnglishDictionary(async () => {
        throw new Error("network down");
      })
    );
    assert.equal(loadFailure.result, "failed");
    assert.match(loadFailure.warnings.join(" | "), /network down/);

    const rejecting = await createAdapter({
      english: () => {
        throw new Error("Failed to load English dictionary");
      },
    });
    const setterFailure = await withWarnings(() =>
      rejecting.adapter.loadEnglishDictionary(async () => CMU)
    );
    assert.equal(setterFailure.result, "failed");
    assert.match(setterFailure.warnings.join(" | "), /Failed to load English dictionary/);
  });
});
