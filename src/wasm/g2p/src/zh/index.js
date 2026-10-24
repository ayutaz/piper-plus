/**
 * ChineseG2P -- Chinese (Mandarin) G2P for @piper-plus/g2p.
 *
 * Three modes, tried in this order:
 *
 * - `wasm`: a WASM phonemizer passed in (`wasmPhonemizer`) does the work.
 *   On failure the class falls back to the next available mode and records
 *   the error in `lastError`.
 * - `dictionary`: the pinyin dictionaries (Issue #829). The same steps as the
 *   Rust `ChinesePhonemizer` and the Python training-side G2P: longest phrase
 *   match, tone sandhi, pinyin -> IPA (see `./pinyin.js`). Enabled by
 *   `await initialize()` (loads the dictionaries bundled with the package),
 *   by the `pinyinDict` option, or by `G2P.create()` when `zh` is enabled.
 * - `fallback`: no dictionary loaded -- every character is passed through as
 *   a token. This is what `new ChineseG2P()` does until `initialize()` has
 *   finished, so the synchronous API keeps working without the 2.7 MB of
 *   dictionary data.
 *
 * English inside Chinese text is read as Mandarin pinyin by
 * `phonemizeEmbeddedEnglish()` (ZH-EN loanword dictionary, Issue #384);
 * `G2P` calls it for English segments next to Chinese ones.
 */

import {
  PinyinDictionary,
  createPinyinDictionary,
  isPinyinDictionaryLoaded,
  loadPinyinDictionary,
} from "./pinyin-dict.js";
import { phonemizeChinese } from "./pinyin.js";
import { phonemizeEmbeddedEnglish } from "./loanword.js";

export { PinyinDictionary, createPinyinDictionary, isPinyinDictionaryLoaded, loadPinyinDictionary };

export class ChineseG2P {
  /**
   * @param {object} [options]
   * @param {Record<string, number[]>} [options.phonemeIdMap]
   *   Mapping from character/phoneme string to array of phoneme IDs.
   *   Typically loaded from the model's config.json `phoneme_id_map`.
   * @param {object} [options.wasmPhonemizer]
   *   Optional WASM phonemizer instance with a `.phonemize(text, lang)` method.
   * @param {PinyinDictionary | { single: unknown, phrases: unknown }} [options.pinyinDict]
   *   Pinyin dictionaries to use (see `createPinyinDictionary`). Without
   *   it, the class stays in `fallback` mode until `initialize()`.
   */
  constructor(options = {}) {
    this.phonemeIdMap = options.phonemeIdMap || null;
    this._wasmPhonemizer = options.wasmPhonemizer || null;
    /** @private @type {PinyinDictionary|null} */
    this._pinyinDict = options.pinyinDict ? createPinyinDictionary(options.pinyinDict) : null;
    /** @private ZH-EN dispatch toggle for the dictionary mode (default on, as in Rust). */
    this._zhEnDispatch = true;
    /** @private */
    this._lastError = null;
  }

  /**
   * Load the pinyin dictionaries bundled with the package (once per process,
   * shared by all instances) and switch to `dictionary` mode. Does nothing
   * when a dictionary is already set.
   *
   * @returns {Promise<this>}
   */
  async initialize() {
    if (!this._pinyinDict) {
      this._pinyinDict = await loadPinyinDictionary();
    }
    return this;
  }

  /**
   * Set or replace the pinyin dictionaries (switches to `dictionary` mode
   * unless a WASM phonemizer is attached; `null` returns to `fallback`).
   *
   * @param {PinyinDictionary | { single: unknown, phrases: unknown } | null} pinyinDict
   */
  setPinyinDictionary(pinyinDict) {
    this._pinyinDict = pinyinDict ? createPinyinDictionary(pinyinDict) : null;
  }

  /**
   * The last error encountered during WASM phonemization, or null if
   * the most recent call succeeded (or WASM was never attempted).
   * @type {string|null}
   */
  get lastError() {
    return this._lastError;
  }

  /**
   * Current operation mode: 'wasm' if a WASM phonemizer is available,
   * 'dictionary' if the pinyin dictionaries are set, 'fallback' otherwise.
   * @type {'wasm'|'dictionary'|'fallback'}
   */
  get mode() {
    if (this._wasmPhonemizer) {
      return "wasm";
    }
    if (this._pinyinDict) {
      return "dictionary";
    }
    return "fallback";
  }

  /**
   * Set or replace the phoneme ID map.
   * @param {Record<string, number[]>} phonemeIdMap
   */
  setPhonemeIdMap(phonemeIdMap) {
    this.phonemeIdMap = phonemeIdMap;
  }

  /**
   * Set or replace the WASM phonemizer instance.
   * @param {object|null} wasmPhonemizer
   */
  setWasmPhonemizer(wasmPhonemizer) {
    this._wasmPhonemizer = wasmPhonemizer || null;
    this._lastError = null;
  }

  /**
   * Toggle ZH-EN code-switching dispatch (TICKET-04 W3, Issue #384).
   *
   * With a WASM phonemizer attached, the value is forwarded to its
   * `setZhEnDispatch(enabled)` (the WASM side owns the default). In
   * `dictionary` mode it decides whether `G2P` reads English next to Chinese
   * with the loanword dictionary (default on) or with the English G2P. In
   * `fallback` mode it has no effect and `isZhEnDispatchEnabled()` returns
   * `null`.
   *
   * @param {boolean} enabled
   */
  setZhEnDispatch(enabled) {
    this._zhEnDispatch = Boolean(enabled);
    if (this._wasmPhonemizer && typeof this._wasmPhonemizer.setZhEnDispatch === "function") {
      this._wasmPhonemizer.setZhEnDispatch(Boolean(enabled));
    }
  }

  /**
   * Whether ZH-EN code-switching dispatch is enabled: the WASM phonemizer's
   * value when one is attached (`null` if it does not support the API), the
   * toggle of the `dictionary` mode otherwise, and `null` in `fallback` mode
   * -- *not* `true`/`false` -- so callers can distinguish "not configured"
   * from "explicitly off".
   *
   * @returns {boolean|null}
   */
  isZhEnDispatchEnabled() {
    if (this._wasmPhonemizer) {
      if (typeof this._wasmPhonemizer.isZhEnDispatchEnabled === "function") {
        return Boolean(this._wasmPhonemizer.isZhEnDispatchEnabled());
      }
      return null;
    }
    if (this._pinyinDict) {
      return this._zhEnDispatch;
    }
    return null;
  }

  /**
   * Convert Chinese text to phoneme tokens.
   *
   * When a WASM phonemizer is available, it is tried first.
   * On failure, falls back to the dictionary (or character-level passthrough
   * without one) and stores the error reason in `lastError`.
   *
   * @param {string} text - Input Chinese text.
   * @returns {{ tokens: string[], prosody: null[] }}
   */
  phonemize(text) {
    const { tokens } = this._phonemize(text);
    return { tokens, prosody: new Array(tokens.length).fill(null) };
  }

  /**
   * Convert Chinese text to phoneme tokens with prosody.
   *
   * In `dictionary` mode each syllable's tokens carry a1 = tone (after tone
   * sandhi), a2 = position in the run of Chinese characters, a3 = run length
   * (as the Rust and Python G2P); spaces are {0,0,0}, letters and digits
   * {0,0,1}, punctuation null. The other modes give {0,0,0} to every token.
   *
   * @param {string} text - Input Chinese text.
   * @returns {{ tokens: string[], prosody: ({ a1: number, a2: number, a3: number }|null)[] }}
   */
  phonemizeWithProsody(text) {
    return this._phonemize(text);
  }

  /**
   * Read English embedded in Chinese text as Mandarin pinyin with the bundled
   * ZH-EN loanword dictionary: case-sensitive loanwords, then uppercase
   * acronyms, then letter by letter. Other characters (digits, punctuation,
   * spaces) are dropped. Works in every mode.
   *
   * @param {string} text
   * @returns {{ tokens: string[], prosody: null[] }}
   */
  phonemizeEmbeddedEnglish(text) {
    const { tokens } = phonemizeEmbeddedEnglish(text);
    return { tokens, prosody: new Array(tokens.length).fill(null) };
  }

  /**
   * `phonemizeEmbeddedEnglish()` with prosody: a1 = tone, a2 = a3 = 1.
   *
   * @param {string} text
   * @returns {{ tokens: string[], prosody: { a1: number, a2: number, a3: number }[] }}
   */
  phonemizeEmbeddedEnglishWithProsody(text) {
    return phonemizeEmbeddedEnglish(text);
  }

  /**
   * @private
   * @param {string} text
   * @returns {{ tokens: string[], prosody: ({ a1: number, a2: number, a3: number }|null)[] }}
   */
  _phonemize(text) {
    if (!text || typeof text !== "string") {
      return { tokens: [], prosody: [] };
    }
    if (this._wasmPhonemizer) {
      try {
        const result = this._wasmPhonemizer.phonemize(text, "zh");
        this._lastError = null;
        const tokens = result.tokens || [];
        return { tokens, prosody: tokens.map(() => ({ a1: 0, a2: 0, a3: 0 })) };
      } catch (e) {
        this._lastError = `WASM phonemize failed: ${e.message || e}`;
      }
    }
    if (this._pinyinDict) {
      return phonemizeChinese(text, this._pinyinDict);
    }
    return this._fallbackPhonemize(text);
  }

  /**
   * @private
   * Character-level passthrough fallback.
   * @param {string} text
   * @returns {{ tokens: string[], prosody: { a1: number, a2: number, a3: number }[] }}
   */
  _fallbackPhonemize(text) {
    const tokens = Array.from(text);
    return { tokens, prosody: tokens.map(() => ({ a1: 0, a2: 0, a3: 0 })) };
  }
}
