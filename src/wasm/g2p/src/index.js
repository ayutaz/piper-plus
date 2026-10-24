/**
 * @piper-plus/g2p -- Multilingual G2P (Grapheme-to-Phoneme) entry point.
 *
 * Provides a unified API for converting text to phoneme tokens across
 * 8 languages (JA, EN, ZH, KO, ES, FR, PT, SV) without eSpeak-ng dependency.
 *
 * @module @piper-plus/g2p
 */

import { JapaneseG2P } from "./ja/index.js";
import { EnglishG2P } from "./en/index.js";
import { ChineseG2P, createPinyinDictionary, loadPinyinDictionary } from "./zh/index.js";
import { SpanishG2P } from "./es/index.js";
import { FrenchG2P } from "./fr/index.js";
import { EuropeanPortugueseG2P, PortugueseG2P } from "./pt/index.js";
import { SwedishG2P } from "./sv/index.js";
import { KoreanG2P } from "./ko/index.js";
import { UnicodeLanguageDetector, normalizeCjkPunctuationForLatin } from "./detect.js";
import { Encoder } from "./encode.js";
import { mapToken } from "./pua-map.js";

// ---- Constants ---------------------------------------------------------------

/** All supported language codes. */
const ALL_LANGUAGES = ["ja", "en", "zh", "ko", "es", "fr", "pt", "pt-PT", "sv"];

/** Map from language code to G2P constructor (for languages other than JA and ZH). */
const LANGUAGE_FACTORIES = {
  en: (options) => new EnglishG2P({ cmuDict: options.cmuDict }),
  ko: () => new KoreanG2P(),
  es: () => new SpanishG2P(),
  fr: () => new FrenchG2P(),
  pt: () => new PortugueseG2P(),
  "pt-PT": () => new EuropeanPortugueseG2P(),
  sv: () => new SwedishG2P(),
};

/**
 * Latin-script languages. Their text goes through
 * `normalizeCjkPunctuationForLatin` before it reaches their G2P, which would
 * otherwise delete CJK punctuation and join the words around it (Issue #823,
 * docs/spec/cjk-punctuation-contract.toml).
 */
const LATIN_SEGMENT_LANGUAGES = new Set(["en", "es", "fr", "pt", "pt-PT", "sv"]);

/**
 * Tokens stripped from a Japanese segment inside Chinese text: BOS/EOS and the
 * question-marker EOS forms, spelled and PUA (Rust
 * `MultilingualPhonemizer::is_boundary_token`). Other languages strip only
 * `^` and `$`; there `?` is an ordinary phoneme.
 */
const JA_BOUNDARY_TOKENS = new Set([
  "^",
  "$",
  "?",
  ...["?!", "?.", "?~"].flatMap((t) => [t, mapToken(t)]),
]);

// ---- G2P class ---------------------------------------------------------------

/**
 * Unified G2P (Grapheme-to-Phoneme) class for multilingual text-to-phoneme
 * conversion.
 *
 * Use the async factory `G2P.create(options)` to construct an instance.
 * Japanese requires OpenJTalk WASM + dictionary data, and English loads the
 * bundled CMU dictionary; the other languages are rule-based and initialise
 * synchronously.
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
   * @param {UnicodeLanguageDetector|null} [zhDetector]  detector that splits
   *   text given as Chinese (Latin letters -> en when en is enabled)
   */
  constructor(phonemizers, detector, zhDetector = null) {
    /** @type {Map<string, object>} */
    this._phonemizers = phonemizers;
    /** @type {UnicodeLanguageDetector} */
    this._detector = detector;
    /** @type {UnicodeLanguageDetector|null} */
    this._zhDetector = zhDetector;
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
   * @param {Record<string, string>|Map<string, string>} [options.cmuDict]
   *   English pronunciation dictionary (lowercase word -> ARPAbet string) to
   *   use instead of the bundled CMU dictionary. When English is enabled and
   *   this is not given, the bundled `data/cmudict_data.json` (~3.7 MB) is
   *   loaded here; it is not loaded when `languages` leaves English out.
   * @param {import('./zh/pinyin-dict.js').PinyinDictionary | { single: unknown, phrases: unknown }} [options.pinyinDict]
   *   Pinyin dictionaries for Chinese (see `createPinyinDictionary`). When
   *   omitted and `zh` is enabled, the dictionaries bundled with the package
   *   are loaded (about 2.7 MB of JSON, once per process). They are not
   *   loaded when `zh` is not in `languages`.
   * @returns {Promise<G2P>}
   */
  static async create(options = {}) {
    const languages = options.languages
      ? options.languages.filter((l) => ALL_LANGUAGES.includes(l))
      : [...ALL_LANGUAGES];

    if (languages.length === 0) {
      throw new Error(
        `G2P.create(): no valid languages specified. ` +
          `Supported languages: ${ALL_LANGUAGES.join(", ")}`
      );
    }

    const phonemizers = new Map();
    const detector = new UnicodeLanguageDetector(languages);

    // Initialise Japanese (async -- requires WASM + dict)
    if (languages.includes("ja")) {
      const jaG2P = new JapaneseG2P({
        openjtalkModule: options.openjtalkModule,
        jaDict: options.jaDict,
      });
      await jaG2P.initialize();
      phonemizers.set("ja", jaG2P);
    }

    // Initialise Chinese (async -- the pinyin dictionaries are loaded here,
    // and only when zh is enabled; Issue #829)
    let zhDetector = null;
    if (languages.includes("zh")) {
      const pinyinDict = options.pinyinDict
        ? createPinyinDictionary(options.pinyinDict)
        : await loadPinyinDictionary();
      phonemizers.set("zh", new ChineseG2P({ pinyinDict }));
      // Text given as Chinese is split like Rust's MultilingualPhonemizer
      // (default Latin language en): Latin letters go to English when it is
      // enabled, otherwise they stay in the Chinese segment.
      zhDetector = new UnicodeLanguageDetector(languages, {
        defaultLatinLanguage: languages.includes("en") ? "en" : "zh",
      });
    }

    // Initialise the other languages (English loads its CMU dictionary)
    for (const lang of languages) {
      if (lang === "ja" || lang === "zh") {
        continue;
      }
      const factory = LANGUAGE_FACTORIES[lang];
      if (factory) {
        const g2p = factory(options);
        if (typeof g2p.initialize === "function") {
          await g2p.initialize();
        }
        // Apply custom dicts if the G2P instance supports it
        if (options.customDicts && typeof g2p.setCustomDicts === "function") {
          g2p.setCustomDicts(options.customDicts);
        }
        phonemizers.set(lang, g2p);
      }
    }

    return new G2P(phonemizers, detector, zhDetector);
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

    const result =
      language === "zh"
        ? this._phonemizeChineseText(text)
        : g2p.phonemize(this._prepareText(text, language));
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
    if (language === "zh") {
      const result = this._phonemizeChineseText(text);
      return { tokens: result.tokens, prosody: result.prosody, language };
    }
    text = this._prepareText(text, language);

    if (typeof g2p.phonemizeWithProsody === "function") {
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
    if (this._disposed) {
      return;
    }
    this._disposed = true;
    for (const [, g2p] of this._phonemizers) {
      if (typeof g2p.dispose === "function") {
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
   * Phonemize text given as Chinese, as Rust's
   * `MultilingualPhonemizer::phonemize_with_language(text, "zh")` does: split
   * it by script, read Chinese segments with the pinyin dictionaries, read an
   * English segment next to a Chinese one with the ZH-EN loanword dictionary
   * (Issue #384; the ChineseG2P `setZhEnDispatch` toggle), and give every
   * other segment (e.g. digits only, or English away from Chinese) to its own
   * language's G2P.
   *
   * @param {string} text
   * @returns {{ tokens: string[], prosody: (ProsodyInfo|null)[] }}
   * @private
   */
  _phonemizeChineseText(text) {
    const zh = this._getPhonemizerOrThrow("zh");
    if (typeof text !== "string" || !this._zhDetector) {
      return zh.phonemizeWithProsody(text);
    }
    const segments = this._zhDetector.segmentText(text);
    const hasZh = segments.some((s) => s.language === "zh");
    const dispatch = zh.isZhEnDispatchEnabled() === true;

    /** @type {string[]} */
    const tokens = [];
    /** @type {(ProsodyInfo|null)[]} */
    const prosody = [];
    segments.forEach((segment, i) => {
      const lang = segment.language;
      const segText = this._prepareText(segment.text, lang);

      const besideZh = segments[i - 1]?.language === "zh" || segments[i + 1]?.language === "zh";
      if (dispatch && lang === "en" && hasZh && besideZh) {
        const result = zh.phonemizeEmbeddedEnglishWithProsody(segText);
        tokens.push(...result.tokens);
        prosody.push(...result.prosody);
        return;
      }

      const g2p = this._getPhonemizerOrThrow(lang);
      const result =
        typeof g2p.phonemizeWithProsody === "function"
          ? g2p.phonemizeWithProsody(segText)
          : g2p.phonemize(segText);
      result.tokens.forEach((token, j) => {
        const boundary =
          lang === "ja" ? JA_BOUNDARY_TOKENS.has(token) : token === "^" || token === "$";
        if (!boundary) {
          tokens.push(token);
          prosody.push(result.prosody?.[j] ?? null);
        }
      });
    });
    return { tokens, prosody };
  }

  /**
   * Rewrite CJK punctuation as ASCII in text for a Latin-script language
   * (Issue #823). Text for other languages is returned as it is.
   *
   * @param {string} text
   * @param {string} language
   * @returns {string}
   * @private
   */
  _prepareText(text, language) {
    if (typeof text !== "string" || !LATIN_SEGMENT_LANGUAGES.has(language)) {
      return text;
    }
    return normalizeCjkPunctuationForLatin(text);
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
          `Available languages: [${available.join(", ")}]. ` +
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
      throw new Error("G2P: instance has been disposed. Create a new instance with G2P.create().");
    }
  }
}

// ---- Re-exports --------------------------------------------------------------

export { JapaneseG2P } from "./ja/index.js";
export {
  EnglishG2P,
  loadCmuDict,
  isCmuDictLoaded,
  normalizeNumbers,
  normalizeAndTokenize,
} from "./en/index.js";
export {
  ChineseG2P,
  PinyinDictionary,
  createPinyinDictionary,
  isPinyinDictionaryLoaded,
  loadPinyinDictionary,
} from "./zh/index.js";
export { SpanishG2P } from "./es/index.js";
export { FrenchG2P } from "./fr/index.js";
export { EuropeanPortugueseG2P, PortugueseG2P } from "./pt/index.js";
export { SwedishG2P } from "./sv/index.js";
export { KoreanG2P } from "./ko/index.js";
export { DictLoader } from "./dict-loader.js";
export { Encoder } from "./encode.js";
export { UnicodeLanguageDetector, normalizeCjkPunctuationForLatin } from "./detect.js";
export { CustomDictionary } from "./custom-dictionary.js";
export { PUA_COMPAT_VERSION, checkPuaCompat, PUA_MAP, mapToken, unmapToken } from "./pua-map.js";
export { extractPhonemesFromLabels, applyNPhonemeRules, mapToPUA } from "./ja/phoneme-extract.js";

// SSML support — see ./ssml.js for the parser. Mirrors Python/Rust/C#/Go.
export { isSsml, parseSsml, SsmlParser } from "./ssml.js";
