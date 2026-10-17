/**
 * Adapter wrapping @piper-plus/g2p G2P behind PhonemizerInterface.
 * @module piper-plus/phonemizer/js-g2p-adapter
 */

import { G2P, PUA_MAP } from "@piper-plus/g2p";

export class JsG2pAdapter {
  /**
   * @param {object} g2p - G2P instance
   * @param {object} phonemeIdMap - phoneme-to-ID mapping from model config
   * @param {string[]} languages - supported language codes
   */
  constructor(g2p, phonemeIdMap, languages) {
    /** @private */
    this._g2p = g2p;
    /** @private */
    this._phonemeIdMap = phonemeIdMap;
    /** @private */
    this._languages = languages;
    /** @private */
    this._disposed = false;
  }

  /**
   * Create a JsG2pAdapter.
   * @param {string[]} languages - language codes to enable
   * @param {object} phonemeIdMap - phoneme-to-ID mapping from model config
   * @param {object} [options] - passed through to G2P.create
   * @returns {Promise<JsG2pAdapter>}
   */
  static async create(languages, phonemeIdMap, options = {}) {
    const g2p = await G2P.create({ languages, ...options });
    return new JsG2pAdapter(g2p, phonemeIdMap, languages);
  }

  /**
   * Encode text into phoneme IDs and optional prosody features.
   * @param {string} text
   * @param {string} language
   * `droppedSymbols` lists tokens missing from the model's phoneme ID map,
   * once each in first-seen order.
   * @returns {{ phonemeIds: number[], prosodyFeatures: number[][]|null, droppedSymbols: string[] }}
   */
  encode(text, language) {
    const result = this._g2p.encode(text, this._phonemeIdMap, { language });

    let prosodyFeatures = null;
    if (result.prosodyFlat && result.prosodyFlat.length > 0) {
      const flat = result.prosodyFlat;
      prosodyFeatures = [];
      for (let i = 0; i < flat.length; i += 3) {
        prosodyFeatures.push([flat[i], flat[i + 1], flat[i + 2]]);
      }
    }

    const encoded = { phonemeIds: result.phonemeIds, prosodyFeatures };
    if (Array.isArray(result.droppedSymbols)) {
      encoded.droppedSymbols = result.droppedSymbols;
      return encoded;
    }
    // The package depends on @piper-plus/g2p by semver range, and encode()
    // results lack droppedSymbols up to 0.4.2. Work them out from the tokens,
    // only when read: synthesize() never needs them.
    let dropped;
    Object.defineProperty(encoded, "droppedSymbols", {
      enumerable: true,
      get: () => (dropped ??= this._findDroppedSymbols(text, language)),
    });
    return encoded;
  }

  /**
   * Tokens the Encoder skips: neither the token nor its PUA form is mapped.
   * @private
   */
  _findDroppedSymbols(text, language) {
    const map = this._phonemeIdMap;
    const { tokens } = this._g2p.phonemizeWithProsody(text, { language });
    const dropped = tokens.filter(
      (token) => !Object.hasOwn(map, token) && !Object.hasOwn(map, PUA_MAP[token] ?? "")
    );
    return [...new Set(dropped)];
  }

  /**
   * Detect language of given text.
   * @param {string} text
   * @returns {string}
   */
  detectLanguage(text) {
    return this._g2p.detectLanguage(text);
  }

  /** @returns {string[]} */
  get supportedLanguages() {
    return this._languages;
  }

  /** Release G2P resources. Safe to call multiple times. */
  dispose() {
    if (this._disposed) {
      return;
    }
    this._disposed = true;
    this._g2p.dispose();
  }
}
