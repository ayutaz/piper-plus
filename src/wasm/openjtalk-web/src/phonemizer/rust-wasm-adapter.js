/**
 * Adapter wrapping Rust WASM WasmPhonemizer behind PhonemizerInterface.
 * @module piper-plus/phonemizer/rust-wasm-adapter
 */

export class RustWasmAdapter {
  /**
   * @param {object} wasm - Rust WASM WasmPhonemizer instance
   * @param {string[]} languages - supported language codes
   * @param {string} [japaneseDictionaryStatus] - outcome of the optional
   *   external Japanese dictionary load. One of `"not-requested"`,
   *   `"unsupported"`, `"loaded"`, `"failed"`.
   */
  constructor(wasm, languages, japaneseDictionaryStatus = "not-requested") {
    /** @private */
    this._wasm = wasm;
    /** @private */
    this._languages = languages;
    /** @private */
    this._disposed = false;
    /** @private */
    this._japaneseDictionaryStatus = japaneseDictionaryStatus;
  }

  /**
   * Outcome of the optional external Japanese dictionary load.
   *
   * A failed load is not an error: rejecting would be caught upstream and
   * drop Japanese *and* Chinese from the WASM path together. The phonemizer
   * stays on its passthrough fallback instead, which produces character-level
   * tokens without complaining -- so callers that requested a dictionary need
   * a way to find out it never applied.
   *
   * @returns {"not-requested"|"unsupported"|"loaded"|"failed"}
   */
  get japaneseDictionaryStatus() {
    return this._japaneseDictionaryStatus;
  }

  /**
   * Create a RustWasmAdapter from a model config JSON string.
   * @param {string} configJson - model config JSON
   * @param {object} [options]
   * @param {string} [options.wasmUrl] - URL to the WASM module
   * @param {function} [options.wasmLoader] - DI loader returning { WasmPhonemizer }
   * @returns {Promise<RustWasmAdapter>}
   */
  /**
   * @param {string} configJson - model config JSON
   * @param {object} [options]
   * @param {string} [options.wasmUrl] - URL to the WASM module
   * @param {function} [options.wasmLoader] - DI loader returning { WasmPhonemizer }
   * @param {string} [options.zhDictBaseUrl] - Base URL for Chinese pinyin dictionaries.
   *   Defaults to `../../assets/` relative to the WASM module.
   * @param {{url: string, sha256?: string}} [options.jaDict] - External Japanese
   *   dictionary to install after construction. Opt-in and without a default
   *   URL: builds that bundle NAIST-JDIC must not have their Japanese output
   *   changed implicitly, and the blob is ~55 MB. Only meaningful for the
   *   `ja-external` / `multilingual-external` variants; on other builds the
   *   option is reported as `"unsupported"` via `japaneseDictionaryStatus`.
   * @returns {Promise<RustWasmAdapter>}
   */
  static async create(configJson, options = {}) {
    let wasmModule;
    if (options.wasmLoader) {
      wasmModule = await options.wasmLoader();
    } else {
      const url = options.wasmUrl;
      if (!url) {
        throw new Error("Either wasmUrl or wasmLoader must be provided");
      }
      wasmModule = await import(url);
      await wasmModule.default(); // init() — load WASM binary
    }
    const wasm = new wasmModule.WasmPhonemizer(configJson);

    // Load Chinese pinyin dictionaries if setChineseDictionary is available
    if (typeof wasm.setChineseDictionary === "function") {
      try {
        const dictBase = options.zhDictBaseUrl || new URL("../../assets/", import.meta.url).href;
        const [singleResp, phraseResp] = await Promise.all([
          fetch(new URL("pinyin_single.json", dictBase)),
          fetch(new URL("pinyin_phrases.json", dictBase)),
        ]);
        if (singleResp.ok && phraseResp.ok) {
          const singleBytes = new Uint8Array(await singleResp.arrayBuffer());
          const phraseBytes = new Uint8Array(await phraseResp.arrayBuffer());
          wasm.setChineseDictionary(singleBytes, phraseBytes);
        } else {
          console.warn(
            "[piper-plus] Chinese pinyin dictionaries not found, zh will use passthrough"
          );
        }
      } catch (e) {
        console.warn("[piper-plus] Failed to load Chinese dictionaries:", e.message);
      }
    }

    // Load the external Japanese dictionary, but only when the caller asked
    // for it. Unlike the Chinese branch above there is deliberately no
    // default URL: `setJapaneseDictionary` swaps out the entire Japanese
    // phonemizer, so a build that bundles NAIST-JDIC must never have its
    // output changed by an implicit download. The blob is also ~55 MB, which
    // is not something to fetch on a guess.
    const japaneseDictionaryStatus = options.jaDict
      ? await loadJapaneseDictionary(wasm, options.jaDict)
      : "not-requested";

    const languages =
      typeof wasm.getSupportedLanguages === "function"
        ? Array.from(wasm.getSupportedLanguages())
        : ["ja", "en", "zh", "ko", "es", "fr", "pt", "sv"];
    return new RustWasmAdapter(wasm, languages, japaneseDictionaryStatus);
  }

  /**
   * Encode text into phoneme IDs and optional prosody features.
   * @param {string} text
   * @param {string} language
   * @returns {{ phonemeIds: number[], prosodyFeatures: number[][]|null }}
   */
  encode(text, language) {
    const result = this._wasm.phonemize(text, language);
    try {
      const phonemeIds = Array.from(result.phonemeIds);

      let prosodyFeatures = null;
      const flat = result.prosodyFeatures;
      if (flat && flat.length > 0) {
        prosodyFeatures = [];
        for (let i = 0; i < flat.length; i += 3) {
          prosodyFeatures.push([flat[i], flat[i + 1], flat[i + 2]]);
        }
      }

      return { phonemeIds, prosodyFeatures };
    } finally {
      result.free();
    }
  }

  /**
   * Detect language of given text.
   * @param {string} text
   * @returns {string}
   */
  detectLanguage(text) {
    return this._wasm.detectLanguage(text);
  }

  /** @returns {string[]} */
  get supportedLanguages() {
    return this._languages;
  }

  /** Release WASM resources. Safe to call multiple times. */
  dispose() {
    if (this._disposed) {
      return;
    }
    this._disposed = true;
    this._wasm.free();
  }
}

/**
 * Hex-encode a SHA-256 digest of the given bytes.
 *
 * Returns `null` when `crypto.subtle` is unavailable (non-HTTPS origins),
 * matching how ModelManager degrades rather than hard-failing.
 *
 * @param {ArrayBuffer} buffer
 * @returns {Promise<string|null>}
 */
async function sha256Hex(buffer) {
  if (typeof crypto === "undefined" || !crypto.subtle) {
    return null;
  }
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Fetch, verify, and install an external Japanese dictionary.
 *
 * The order matters. `setJapaneseDictionary` takes a raw bincode dump of a
 * `jpreprocess::Dictionary` carrying no magic bytes and no version field, so
 * a blob built against a different jpreprocess release fails with an opaque
 * error. Verification therefore happens before the setter runs, and nothing
 * is retained when either step fails -- a bad blob that got cached would keep
 * breaking Japanese on every later run with no way to self-heal.
 *
 * Never throws: rejecting here is caught upstream in a handler that drops
 * Japanese *and* Chinese from the WASM path at once, so a failed Japanese
 * dictionary would take working Chinese down with it.
 *
 * @param {object} wasm - WasmPhonemizer instance
 * @param {{url: string, sha256?: string}} jaDict
 * @returns {Promise<"unsupported"|"loaded"|"failed">}
 */
async function loadJapaneseDictionary(wasm, jaDict) {
  if (typeof wasm.setJapaneseDictionary !== "function") {
    // A build that bundles the dictionary does not expose the setter at all.
    // Say so instead of downloading tens of megabytes that cannot be used.
    console.warn(
      "[piper-plus] jaDict was provided but this WASM build bundles its own " +
        "Japanese dictionary; the option has no effect."
    );
    return "unsupported";
  }

  try {
    const response = await fetch(jaDict.url);
    if (!response.ok) {
      console.warn(
        `[piper-plus] Japanese dictionary fetch failed (${response.status}); ` +
          "ja will use passthrough."
      );
      return "failed";
    }

    const buffer = await response.arrayBuffer();

    if (jaDict.sha256) {
      const actual = await sha256Hex(buffer);
      if (actual === null) {
        console.warn(
          "[piper-plus] crypto.subtle unavailable -- skipping Japanese " +
            "dictionary integrity check. Serve over HTTPS for full verification."
        );
      } else if (actual !== jaDict.sha256) {
        console.warn(
          `[piper-plus] Japanese dictionary SHA-256 mismatch (expected ` +
            `${jaDict.sha256}, got ${actual}); ja will use passthrough.`
        );
        return "failed";
      }
    }

    wasm.setJapaneseDictionary(new Uint8Array(buffer));
    return "loaded";
  } catch (e) {
    console.warn("[piper-plus] Failed to load Japanese dictionary:", e.message);
    return "failed";
  }
}
