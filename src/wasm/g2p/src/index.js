/**
 * @piper-plus/g2p -- Multilingual G2P (Grapheme-to-Phoneme) entry point.
 *
 * Provides a unified API for converting text to phoneme tokens across
 * 8 languages (JA, EN, ZH, KO, ES, FR, PT, SV) without eSpeak-ng dependency.
 *
 * @module @piper-plus/g2p
 */

import { JapaneseG2P } from './ja/index.js';
import { EnglishG2P } from './en/index.js';
import { ChineseG2P } from './zh/index.js';
import { SpanishG2P } from './es/index.js';
import { FrenchG2P } from './fr/index.js';
import { PortugueseG2P } from './pt/index.js';
import { SwedishG2P } from './sv/index.js';
import { KoreanG2P } from './ko/index.js';
import { UnicodeLanguageDetector } from './detect.js';
import { Encoder } from './encode.js';

// ---- Constants ---------------------------------------------------------------

/** All supported language codes. */
const ALL_LANGUAGES = ['ja', 'en', 'zh', 'ko', 'es', 'fr', 'pt', 'sv'];

/** Map from language code to G2P constructor (for non-JA languages). */
const LANGUAGE_FACTORIES = {
  en: () => new EnglishG2P(),
  zh: () => new ChineseG2P(),
  ko: () => new KoreanG2P(),
  es: () => new SpanishG2P(),
  fr: () => new FrenchG2P(),
  pt: () => new PortugueseG2P(),
  sv: () => new SwedishG2P(),
};

// ---- G2P class ---------------------------------------------------------------

/**
 * Unified G2P (Grapheme-to-Phoneme) class for multilingual text-to-phoneme
 * conversion.
 *
 * Use the async factory `G2P.create(options)` to construct an instance.
 * Japanese requires OpenJTalk WASM + dictionary data; other languages
 * are rule-based and initialise synchronously.
 *
 * @example
 * import { G2P, DictLoader } from '@piper-plus/g2p';
 *
 * const loader = new DictLoader();
 * const jaDict = await loader.loadJaDict();
 * const g2p = await G2P.create({ jaDict });
 *
 * const result = g2p.phonemize('こんにちは');
 * // { tokens: ['k','o','N_n','n','i','ch','i','h','a'], prosody: [...], language: 'ja' }
 */
export class G2P {
  /**
   * @private -- use G2P.create() instead.
   * @param {Map<string, object>} phonemizers  language -> G2P instance
   * @param {UnicodeLanguageDetector} detector  language detector
   */
  constructor(phonemizers, detector) {
    /** @type {Map<string, object>} */
    this._phonemizers = phonemizers;
    /** @type {UnicodeLanguageDetector} */
    this._detector = detector;
    /** @type {boolean} */
    this._disposed = false;
  }

  // ---- Factory ---------------------------------------------------------------

  /**
   * Create and initialise a G2P instance.
   *
   * @param {Object} [options]
   * @param {string[]} [options.languages]        Languages to enable (default: all 8).
   * @param {object}   [options.openjtalkModule]  Pre-loaded OpenJTalk WASM module (DI).
   * @param {import('./dict-loader.js').JaDictData} [options.jaDict]
   *   Japanese dictionary data obtained from `DictLoader.loadJaDict()`.
   * @param {import('./custom-dictionary.js').CustomDictionary[]} [options.customDicts]
   *   Custom dictionary instances to apply before phonemisation.
   * @returns {Promise<G2P>}
   */
  static async create(options = {}) {
    const languages = options.languages
      ? options.languages.filter((l) => ALL_LANGUAGES.includes(l))
      : [...ALL_LANGUAGES];

    if (languages.length === 0) {
      throw new Error(
        `G2P.create(): no valid languages specified. ` +
        `Supported languages: ${ALL_LANGUAGES.join(', ')}`
      );
    }

    const phonemizers = new Map();
    const detector = new UnicodeLanguageDetector(languages);

    // Initialise Japanese (async -- requires WASM + dict)
    if (languages.includes('ja')) {
      const jaG2P = new JapaneseG2P({
        openjtalkModule: options.openjtalkModule,
        jaDict: options.jaDict,
      });
      await jaG2P.initialize();
      phonemizers.set('ja', jaG2P);
    }

    // Initialise rule-based languages (sync)
    for (const lang of languages) {
      if (lang === 'ja') continue;
      const factory = LANGUAGE_FACTORIES[lang];
      if (factory) {
        const g2p = factory();
        // Apply custom dicts if the G2P instance supports it
        if (options.customDicts && typeof g2p.setCustomDicts === 'function') {
          g2p.setCustomDicts(options.customDicts);
        }
        phonemizers.set(lang, g2p);
      }
    }

    return new G2P(phonemizers, detector);
  }

  // ---- Public API ------------------------------------------------------------

  /**
   * Convert text to phoneme tokens.
   *
   * If `options.language` is provided, that language's G2P is used directly.
   * Otherwise the language is auto-detected from Unicode character ranges.
   *
   * The `prosody` array contains `null` for every token (no prosody extraction).
   * Use `phonemizeWithProsody()` to obtain A1/A2/A3 values for Japanese.
   *
   * @param {string} text  Input text.
   * @param {Object} [options]
   * @param {string} [options.language]  Force a specific language code.
   * @returns {{ tokens: string[], prosody: null[], language: string }}
   */
  phonemize(text, options = {}) {
    this._ensureNotDisposed();
    const language = this._resolveLanguage(text, options);
    const g2p = this._getPhonemizerOrThrow(language);

    const result = g2p.phonemize(text);
    return {
      tokens: result.tokens,
      prosody: new Array(result.tokens.length).fill(null),
      language,
    };
  }

  /**
   * Convert text to phoneme tokens with prosody information.
   *
   * For Japanese, each phoneme token carries `{ a1, a2, a3 }` prosody data
   * extracted from OpenJTalk full-context labels. Structural markers
   * (BOS/EOS/pause/accent markers) have `null` prosody.
   *
   * For other languages, the G2P module's `phonemizeWithProsody()` is called
   * if available; otherwise falls back to `phonemize()` with null prosody.
   *
   * @param {string} text  Input text.
   * @param {Object} [options]
   * @param {string} [options.language]  Force a specific language code.
   * @returns {{ tokens: string[], prosody: (ProsodyInfo|null)[], language: string }}
   *
   * @typedef {Object} ProsodyInfo
   * @property {number} a1
   * @property {number} a2
   * @property {number} a3
   */
  phonemizeWithProsody(text, options = {}) {
    this._ensureNotDisposed();
    const language = this._resolveLanguage(text, options);
    const g2p = this._getPhonemizerOrThrow(language);

    if (typeof g2p.phonemizeWithProsody === 'function') {
      const result = g2p.phonemizeWithProsody(text);
      return {
        tokens: result.tokens,
        prosody: result.prosody,
        language,
      };
    }

    // Fallback: no prosody support for this language
    const result = g2p.phonemize(text);
    return {
      tokens: result.tokens,
      prosody: new Array(result.tokens.length).fill(null),
      language,
    };
  }

  /**
   * Phonemize text and encode to Piper-compatible phoneme IDs in one step.
   *
   * Internally calls `phonemizeWithProsody()` then `Encoder.encode()` to
   * produce BOS/PAD/EOS-wrapped ID sequences ready for ONNX inference.
   *
   * @param {string} text  Input text.
   * @param {Record<string, number[]>} phonemeIdMap
   *   Phoneme-to-ID mapping from the Piper model's config.json.
   * @param {Object} [options]
   * @param {string} [options.language]  Force a specific language code.
   * @returns {{ phonemeIds: number[], prosodyFlat: number[]|null }}
   */
  encode(text, phonemeIdMap, options = {}) {
    this._ensureNotDisposed();
    const { tokens, prosody } = this.phonemizeWithProsody(text, options);
    const encoder = new Encoder(phonemeIdMap);
    return encoder.encodeWithProsody(tokens, prosody);
  }

  /**
   * Detect the dominant language of the given text.
   *
   * Uses Unicode character ranges to classify characters:
   * - Kana (Hiragana/Katakana) -> 'ja'
   * - CJK ideographs without Kana context -> 'zh'
   * - Latin characters -> 'en' (default)
   *
   * Note: ES/FR/PT cannot be distinguished from EN by character ranges alone;
   * use `options.language` to specify them explicitly.
   *
   * @param {string} text  Input text.
   * @returns {string}  Language code ('ja'|'en'|'zh'|'ko'|'es'|'fr'|'pt'|'sv').
   */
  detectLanguage(text) {
    this._ensureNotDisposed();
    return this._detector.detectLanguage(text);
  }

  /**
   * Segment mixed-language text into per-language chunks.
   *
   * Each segment contains contiguous characters of the same detected language.
   * Neutral characters (whitespace, digits, punctuation) are absorbed into
   * the preceding segment.
   *
   * @param {string} text  Input text.
   * @returns {Array<{ language: string, text: string }>}
   */
  segmentText(text) {
    this._ensureNotDisposed();
    return this._detector.segmentText(text);
  }

  /**
   * Release resources held by language-specific G2P modules.
   *
   * After calling `dispose()`, all other methods will throw.
   * Primarily needed to free OpenJTalk WASM memory for Japanese.
   */
  dispose() {
    if (this._disposed) return;
    this._disposed = true;
    for (const [, g2p] of this._phonemizers) {
      if (typeof g2p.dispose === 'function') {
        g2p.dispose();
      }
    }
    this._phonemizers.clear();
  }

  // ---- Private helpers -------------------------------------------------------

  /**
   * Resolve the target language from options or auto-detection.
   *
   * @param {string} text
   * @param {{ language?: string }} options
   * @returns {string}
   * @private
   */
  _resolveLanguage(text, options) {
    if (options.language) {
      return options.language;
    }
    return this._detector.detectLanguage(text);
  }

  /**
   * Get the phonemizer for a language, throwing a descriptive error if the
   * language was not initialised.
   *
   * @param {string} language
   * @returns {object}
   * @private
   */
  _getPhonemizerOrThrow(language) {
    const g2p = this._phonemizers.get(language);
    if (!g2p) {
      const available = [...this._phonemizers.keys()];
      throw new Error(
        `G2P: language "${language}" is not initialised. ` +
        `Available languages: [${available.join(', ')}]. ` +
        `Pass the language in G2P.create({ languages: [...] }) to enable it.`
      );
    }
    return g2p;
  }

  /**
   * Guard against use after dispose().
   *
   * @private
   */
  _ensureNotDisposed() {
    if (this._disposed) {
      throw new Error(
        'G2P: instance has been disposed. Create a new instance with G2P.create().'
      );
    }
  }
}

// ---- Re-exports --------------------------------------------------------------

export { JapaneseG2P } from './ja/index.js';
export { EnglishG2P } from './en/index.js';
export { ChineseG2P } from './zh/index.js';
export { SpanishG2P } from './es/index.js';
export { FrenchG2P } from './fr/index.js';
export { PortugueseG2P } from './pt/index.js';
export { SwedishG2P } from './sv/index.js';
export { KoreanG2P } from './ko/index.js';
export { DictLoader } from './dict-loader.js';
export { Encoder } from './encode.js';
export { UnicodeLanguageDetector } from './detect.js';
export { CustomDictionary } from './custom-dictionary.js';
export { PUA_COMPAT_VERSION, checkPuaCompat, PUA_MAP, mapToken, unmapToken } from './pua-map.js';
export { extractPhonemesFromLabels, applyNPhonemeRules, mapToPUA } from './ja/phoneme-extract.js';
