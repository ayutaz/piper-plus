/**
 * Adapter wrapping Rust WASM WasmPhonemizer behind PhonemizerInterface.
 * @module piper-plus/phonemizer/rust-wasm-adapter
 */

export class RustWasmAdapter {
  /**
   * @param {object} wasm - Rust WASM WasmPhonemizer instance
   * @param {string[]} languages - supported language codes
   */
  constructor(wasm, languages) {
    /** @private */
    this._wasm = wasm;
    /** @private */
    this._languages = languages;
    /** @private */
    this._disposed = false;
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
   * @returns {Promise<RustWasmAdapter>}
   */
  static async create(configJson, options = {}) {
    let wasmModule;
    if (options.wasmLoader) {
      wasmModule = await options.wasmLoader();
    } else {
      const url = options.wasmUrl;
      if (!url) throw new Error('Either wasmUrl or wasmLoader must be provided');
      wasmModule = await import(url);
      await wasmModule.default(); // init() — load WASM binary
    }
    const wasm = new wasmModule.WasmPhonemizer(configJson);

    // Load Chinese pinyin dictionaries if setChineseDictionary is available
    if (typeof wasm.setChineseDictionary === 'function') {
      try {
        const dictBase = options.zhDictBaseUrl
          || new URL('../../assets/', import.meta.url).href;
        const [singleResp, phraseResp] = await Promise.all([
          fetch(new URL('pinyin_single.json', dictBase)),
          fetch(new URL('pinyin_phrases.json', dictBase)),
        ]);
        if (singleResp.ok && phraseResp.ok) {
          const singleBytes = new Uint8Array(await singleResp.arrayBuffer());
          const phraseBytes = new Uint8Array(await phraseResp.arrayBuffer());
          wasm.setChineseDictionary(singleBytes, phraseBytes);
        } else {
          console.warn('[piper-plus] Chinese pinyin dictionaries not found, zh will use passthrough');
        }
      } catch (e) {
        console.warn('[piper-plus] Failed to load Chinese dictionaries:', e.message);
      }
    }

    const languages = typeof wasm.getSupportedLanguages === 'function'
      ? Array.from(wasm.getSupportedLanguages())
      : ['ja', 'en', 'zh', 'ko', 'es', 'fr', 'pt', 'sv'];
    return new RustWasmAdapter(wasm, languages);
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
    if (this._disposed) return;
    this._disposed = true;
    this._wasm.free();
  }
}
