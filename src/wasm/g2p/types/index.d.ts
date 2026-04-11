// Type definitions for @piper-plus/g2p
// Multilingual G2P (Grapheme-to-Phoneme) for TTS -- eSpeak-ng free, MIT licensed

// ---------------------------------------------------------------------------
// Basic types
// ---------------------------------------------------------------------------

/** Supported language codes. */
export type Language = 'ja' | 'en' | 'zh' | 'ko' | 'es' | 'fr' | 'pt' | 'sv';

/**
 * Prosody features extracted from OpenJTalk full-context labels.
 *
 * These correspond to the A1/A2/A3 accent features used by Piper TTS
 * for duration prediction and naturalness improvement.
 */
export interface ProsodyInfo {
    /** Accent type -- relative position to accent nucleus. */
    a1: number;
    /** Position within accent phrase (1-indexed from start). */
    a2: number;
    /** Position within accent phrase (1-indexed from end). */
    a3: number;
}

/**
 * Result of a phonemize operation.
 *
 * Contains IPA token arrays and optional per-token prosody information.
 * Tokens are returned as IPA strings (no PUA encoding).
 */
export interface PhonemizeResult {
    /** IPA phoneme tokens (e.g. ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]). */
    tokens: string[];
    /**
     * Parallel array of prosody info per token.
     * ProsodyInfo for actual phonemes, null for prosody markers and pauses.
     * Only populated for Japanese; other languages return null for all entries.
     */
    prosody: (ProsodyInfo | null)[];
    /** Language of the phonemized text. */
    language: Language;
}

/**
 * Result of encoding IPA tokens to Piper-compatible phoneme IDs.
 *
 * Includes BOS/EOS/inter-phoneme padding inserted by the encoder.
 */
export interface EncodeResult {
    /** Piper-compatible phoneme ID sequence with BOS/EOS/padding. */
    phonemeIds: number[];
    /**
     * Flattened prosody features aligned to phonemeIds.
     * Each group of 3 values represents [a1, a2, a3] for the corresponding phoneme ID.
     * null when the source PhonemizeResult has no prosody data.
     */
    prosodyFlat: number[] | null;
}

// ---------------------------------------------------------------------------
// G2P (high-level unified API)
// ---------------------------------------------------------------------------

/** Options for G2P.create(). */
export interface G2POptions {
    /** Languages to load. Defaults to all supported languages. */
    languages?: Language[];
    /**
     * Pre-loaded OpenJTalk WASM module instance.
     * When omitted, the module is loaded automatically (requires WASM files).
     */
    openjtalkModule?: any;
    /**
     * Pre-loaded Japanese dictionary data.
     * When provided, skips dictionary download during initialization.
     */
    jaDict?: JaDictData;
    /** Custom dictionaries for pronunciation overrides. */
    customDicts?: CustomDictionary[];
}

/** Options for phonemize and encode methods. */
export interface PhonemizeOptions {
    /** Target language. When omitted, language is auto-detected from text. */
    language?: Language;
}

/**
 * High-level G2P API that orchestrates language detection, phonemization,
 * and encoding across all supported languages.
 *
 * @example
 * ```js
 * const g2p = await G2P.create({ languages: ['ja', 'en'] });
 *
 * const result = g2p.phonemize('Hello, world!');
 * // result.tokens => ["h", "ʌ", "l", "oʊ", ",", " ", "w", "ɜː", "l", "d", "!"]
 *
 * const jaResult = g2p.phonemize('こんにちは');
 * // jaResult.tokens => ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]
 *
 * g2p.dispose();
 * ```
 */
export class G2P {
    /**
     * Create and initialize a G2P instance.
     *
     * Loads the required language modules and, for Japanese, initializes the
     * OpenJTalk WASM module and downloads the dictionary if needed.
     *
     * @param options - Configuration options.
     * @returns Fully initialized G2P instance.
     */
    static create(options?: G2POptions): Promise<G2P>;

    /**
     * Convert text to IPA phoneme tokens.
     *
     * Language is auto-detected from text when not specified in options.
     *
     * @param text - Input text to phonemize.
     * @param options - Optional language specification.
     * @returns Phonemize result with IPA tokens and language.
     * @throws {Error} If the instance has been disposed via `dispose()`.
     * @throws {Error} If the detected/specified language was not initialised in `G2P.create()`.
     */
    phonemize(text: string, options?: PhonemizeOptions): PhonemizeResult;

    /**
     * Convert text to IPA phoneme tokens with prosody features.
     *
     * For Japanese, returns A1/A2/A3 accent features per token.
     * For other languages, prosody entries are null.
     *
     * @param text - Input text to phonemize.
     * @param options - Optional language specification.
     * @returns Phonemize result with IPA tokens, prosody info, and language.
     * @throws {Error} If the instance has been disposed via `dispose()`.
     * @throws {Error} If the detected/specified language was not initialised in `G2P.create()`.
     */
    phonemizeWithProsody(text: string, options?: PhonemizeOptions): PhonemizeResult;

    /**
     * Convert text to Piper-compatible phoneme IDs.
     *
     * Combines phonemization and encoding in a single call:
     * phonemize -> PUA mapping -> ID lookup -> BOS/EOS/padding insertion.
     *
     * @param text - Input text.
     * @param phonemeIdMap - Phoneme-to-ID mapping from Piper model config.
     * @param options - Optional language specification.
     * @returns Encoded phoneme IDs and optional flattened prosody features.
     * @throws {Error} If the instance has been disposed via `dispose()`.
     * @throws {Error} If the detected/specified language was not initialised in `G2P.create()`.
     */
    encode(text: string, phonemeIdMap: Record<string, number[]>, options?: PhonemizeOptions): EncodeResult;

    /**
     * Detect the language of the given text using Unicode script analysis.
     *
     * Detection priority: JA (Hiragana/Katakana) > ZH (CJK without Kana) >
     * language-specific scripts > EN (default fallback).
     *
     * @param text - Text to analyze.
     * @returns Detected language code.
     * @throws {Error} If the instance has been disposed via `dispose()`.
     */
    detectLanguage(text: string): Language;

    /**
     * Segment text into language-homogeneous chunks.
     *
     * Splits mixed-language text (e.g. "Hello, こんにちは") into segments
     * with consistent language labels.
     *
     * @param text - Mixed-language text to segment.
     * @returns Array of segments with language and text.
     * @throws {Error} If the instance has been disposed via `dispose()`.
     */
    segmentText(text: string): Array<{ language: Language; text: string }>;

    /**
     * Release all resources held by this instance.
     *
     * Disposes OpenJTalk WASM module and per-language G2P instances.
     * The instance must not be used after calling dispose().
     */
    dispose(): void;
}

// ---------------------------------------------------------------------------
// DictLoader
// ---------------------------------------------------------------------------

/**
 * Japanese dictionary data loaded by DictLoader.
 *
 * Contains the 8 MeCab dictionary files required by OpenJTalk.
 */
export interface JaDictData {
    /**
     * MeCab dictionary files keyed by filename.
     * Required files: char.bin, matrix.bin, sys.dic, unk.dic,
     * left-id.def, pos-id.def, rewrite.def, right-id.def.
     */
    dictFiles: Record<string, ArrayBuffer>;
}

/** Options for DictLoader.loadJaDict(). */
export interface DictLoadOptions {
    /**
     * Custom tar.gz URL for the dictionary archive.
     * Defaults to the official GitHub Releases URL.
     */
    dictUrl?: string;
    /**
     * Progress callback invoked during download.
     * Called with `{ loaded, total }` in bytes.
     */
    onProgress?: (info: { loaded: number; total: number }) => void;
}

/**
 * Dictionary loader for Japanese G2P.
 *
 * Downloads OpenJTalk MeCab dictionary files from GitHub Releases, verifies
 * the SHA-256 hash, and caches them in IndexedDB for instant subsequent loads.
 *
 * @example
 * ```js
 * const loader = new DictLoader();
 * const { dictFiles } = await loader.loadJaDict({
 *   onProgress: ({ loaded, total }) => console.log(`${loaded}/${total}`),
 * });
 * ```
 */
export class DictLoader {
    /**
     * @param options - Configuration options.
     * @param options.cachePrefix - IndexedDB database name. Default: 'piper-g2p-dict'.
     */
    constructor(options?: { cachePrefix?: string });

    /**
     * Download (or retrieve from cache) Japanese dictionary files.
     *
     * On the first call the full tar.gz is downloaded, its SHA-256 is verified,
     * and individual dictionary files are cached in IndexedDB. Subsequent calls
     * return instantly from the cache.
     *
     * @param options - Download options.
     * @returns Dictionary data with MeCab files.
     */
    loadJaDict(options?: DictLoadOptions): Promise<JaDictData>;

    /**
     * Check whether all dictionary files are already cached in IndexedDB.
     *
     * @returns true if all 8 MeCab dictionary files are in the cache.
     */
    isCached(): Promise<boolean>;

    /**
     * Remove all cached dictionary data from IndexedDB.
     */
    clearCache(): Promise<void>;

    /**
     * Close the IndexedDB connection and release resources.
     *
     * Safe to call multiple times. After calling `destroy()`, subsequent
     * operations (e.g. `loadJaDict()`) will re-open the database connection
     * as needed.
     */
    destroy(): void;
}

// ---------------------------------------------------------------------------
// Per-language G2P classes
// ---------------------------------------------------------------------------

/**
 * Japanese G2P using OpenJTalk WASM.
 *
 * Provides high-quality Japanese phonemization with prosody features,
 * context-dependent N variants (N_m, N_n, N_ng, N_uvular), and
 * Kurihara-method prosody markers.
 *
 * @example
 * ```js
 * import { JapaneseG2P } from '@piper-plus/g2p/ja';
 * import { DictLoader } from '@piper-plus/g2p/dict';
 *
 * const loader = new DictLoader();
 * const jaDict = await loader.loadJaDict();
 * const ja = new JapaneseG2P({ jaDict });
 * await ja.initialize();
 *
 * const result = ja.phonemize('こんにちは');
 * // result.tokens => ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]
 * ```
 */
export class JapaneseG2P {
    /**
     * @param options - Configuration options.
     * @param options.openjtalkModule - Pre-loaded OpenJTalk WASM module.
     * @param options.jaDict - Pre-loaded dictionary data from DictLoader.
     */
    constructor(options?: { openjtalkModule?: any; jaDict?: JaDictData });

    /**
     * Initialize the OpenJTalk WASM module and load dictionaries.
     *
     * Must be called before phonemize(). No-op if already initialized.
     *
     * @param options - Reserved for future use.
     */
    initialize(options?: {}): Promise<void>;

    /**
     * Convert Japanese text to IPA phoneme tokens.
     *
     * @param text - Japanese text to phonemize.
     * @returns Phonemize result with IPA tokens (no PUA, no BOS/EOS).
     */
    phonemize(text: string): PhonemizeResult;

    /**
     * Convert Japanese text to IPA phoneme tokens with A1/A2/A3 prosody features.
     *
     * @param text - Japanese text to phonemize.
     * @returns Phonemize result with IPA tokens and per-token ProsodyInfo.
     */
    phonemizeWithProsody(text: string): PhonemizeResult;

    /** Whether the OpenJTalk module has been initialized and is ready to use. */
    readonly initialized: boolean;

    /**
     * Release the OpenJTalk WASM module resources.
     * The instance must not be used after calling dispose().
     */
    dispose(): void;
}

/**
 * English G2P using rule-based CMU-style conversion.
 *
 * Converts English text to IPA phoneme sequences with stress markers.
 * Function word stress reduction (97 words) is applied automatically.
 * No external dependencies required.
 *
 * @example
 * ```js
 * import { EnglishG2P } from '@piper-plus/g2p/en';
 *
 * const en = new EnglishG2P();
 * const result = en.phonemize('Hello, world!');
 * // result.tokens => ["h", "ʌ", "l", "oʊ", ...]
 * ```
 */
export class EnglishG2P {
    constructor(options?: {});

    /**
     * Convert English text to IPA phoneme tokens.
     *
     * @param text - English text to phonemize.
     * @returns Phonemize result with IPA tokens and stress markers.
     */
    phonemize(text: string): PhonemizeResult;

    /**
     * Convert English text to IPA phoneme tokens with prosody features.
     *
     * Returns ProsodyInfo(a1=0, a2=stress_level, a3=word_phoneme_count)
     * for each phoneme token.
     *
     * @param text - English text to phonemize.
     * @returns Phonemize result with IPA tokens and prosody info.
     */
    phonemizeWithProsody(text: string): PhonemizeResult;
}

/**
 * Chinese G2P using pinyin-based phonemization.
 *
 * Converts Chinese text to phoneme sequences based on pinyin decomposition.
 * No external dependencies required.
 *
 * @example
 * ```js
 * import { ChineseG2P } from '@piper-plus/g2p/zh';
 *
 * const zh = new ChineseG2P();
 * const result = zh.phonemize('你好世界');
 * ```
 */
export class ChineseG2P {
    /**
     * @param options - Configuration options.
     * @param options.phonemeIdMap - Phoneme-to-ID mapping for character-based fallback.
     */
    constructor(options?: { phonemeIdMap?: Record<string, number[]> });

    /**
     * Convert Chinese text to phoneme tokens.
     *
     * @param text - Chinese text to phonemize.
     * @returns Phonemize result with phoneme tokens.
     */
    phonemize(text: string): PhonemizeResult;

    /**
     * Convert Chinese text to phoneme tokens with prosody features.
     *
     * @param text - Chinese text to phonemize.
     * @returns Phonemize result with phoneme tokens (prosody entries are null).
     */
    phonemizeWithProsody(text: string): PhonemizeResult;
}

/**
 * Spanish G2P using rule-based phonemization.
 *
 * Converts Spanish text to IPA phoneme sequences.
 * No external dependencies required.
 */
export class SpanishG2P {
    /**
     * @param options - Configuration options.
     * @param options.phonemeIdMap - Phoneme-to-ID mapping for character-based fallback.
     */
    constructor(options?: { phonemeIdMap?: Record<string, number[]> });

    /**
     * Convert Spanish text to phoneme tokens.
     *
     * @param text - Spanish text to phonemize.
     * @returns Phonemize result with phoneme tokens.
     */
    phonemize(text: string): PhonemizeResult;

    /**
     * Convert Spanish text to phoneme tokens with prosody features.
     *
     * @param text - Spanish text to phonemize.
     * @returns Phonemize result with phoneme tokens (prosody entries are null).
     */
    phonemizeWithProsody(text: string): PhonemizeResult;
}

/**
 * French G2P using rule-based phonemization.
 *
 * Converts French text to IPA phoneme sequences.
 * No external dependencies required.
 */
export class FrenchG2P {
    /**
     * @param options - Configuration options.
     * @param options.phonemeIdMap - Phoneme-to-ID mapping for character-based fallback.
     */
    constructor(options?: { phonemeIdMap?: Record<string, number[]> });

    /**
     * Convert French text to phoneme tokens.
     *
     * @param text - French text to phonemize.
     * @returns Phonemize result with phoneme tokens.
     */
    phonemize(text: string): PhonemizeResult;

    /**
     * Convert French text to phoneme tokens with prosody features.
     *
     * @param text - French text to phonemize.
     * @returns Phonemize result with phoneme tokens (prosody entries are null).
     */
    phonemizeWithProsody(text: string): PhonemizeResult;
}

/**
 * Portuguese G2P using rule-based phonemization.
 *
 * Converts Portuguese text to IPA phoneme sequences.
 * No external dependencies required.
 */
export class PortugueseG2P {
    /**
     * @param options - Configuration options.
     * @param options.phonemeIdMap - Phoneme-to-ID mapping for character-based fallback.
     */
    constructor(options?: { phonemeIdMap?: Record<string, number[]> });

    /**
     * Convert Portuguese text to phoneme tokens.
     *
     * @param text - Portuguese text to phonemize.
     * @returns Phonemize result with phoneme tokens.
     */
    phonemize(text: string): PhonemizeResult;

    /**
     * Convert Portuguese text to phoneme tokens with prosody features.
     *
     * @param text - Portuguese text to phonemize.
     * @returns Phonemize result with phoneme tokens (prosody entries are null).
     */
    phonemizeWithProsody(text: string): PhonemizeResult;
}

/**
 * Swedish G2P using rule-based phonemization.
 *
 * Converts Swedish text to IPA phoneme sequences with stress markers.
 * Features: complementary quantity (9 long/short vowel pairs), soft k/g rules,
 * retroflex assimilation (rt/rd/rs/rn/rl), loanword suffix rules, and
 * stress detection with prosody (A1=0, A2=stress, A3=syllable count).
 * No external dependencies required.
 *
 * @example
 * ```js
 * import { SwedishG2P } from '@piper-plus/g2p/sv';
 *
 * const sv = new SwedishG2P();
 * const result = sv.phonemize('Hej, hur m\u00e5r du?');
 * // result.tokens => ["\u02c8", "h", "e\u02d0", "j", ...]
 * ```
 */
export class SwedishG2P {
    constructor(options?: {});

    /**
     * Convert Swedish text to phoneme tokens.
     *
     * @param text - Swedish text to phonemize.
     * @returns Phonemize result with IPA tokens and stress markers.
     */
    phonemize(text: string): PhonemizeResult;

    /**
     * Convert Swedish text to phoneme tokens with prosody features.
     *
     * Returns ProsodyInfo(a1=0, a2=stress_level, a3=word_phoneme_count)
     * for each phoneme token. a2=2 for primary stress markers.
     *
     * @param text - Swedish text to phonemize.
     * @returns Phonemize result with IPA tokens and prosody info.
     */
    phonemizeWithProsody(text: string): PhonemizeResult;
}

/**
 * Korean G2P using Hangul decomposition and IPA mapping.
 *
 * Decomposes Hangul syllables into jamo, maps to IPA phonemes, and applies
 * basic liaison rules (연음법칙). Supports tense consonants, aspirated
 * consonants, and unreleased finals with PUA codepoints.
 * No external dependencies required.
 *
 * @example
 * ```js
 * import { KoreanG2P } from '@piper-plus/g2p/ko';
 *
 * const ko = new KoreanG2P();
 * const result = ko.phonemize('안녕하세요');
 * ```
 */
export class KoreanG2P {
    constructor(options?: {});

    /** Language code for this G2P instance. */
    readonly languageCode: string;

    /**
     * Convert Korean text to phoneme tokens.
     *
     * @param text - Korean text to phonemize.
     * @returns Phonemize result with IPA tokens.
     */
    phonemize(text: string): PhonemizeResult;

    /**
     * Convert Korean text to phoneme tokens with prosody features.
     *
     * Korean prosody: A1=0, A2=0, A3=0 (fixed).
     *
     * @param text - Korean text to phonemize.
     * @returns Phonemize result with IPA tokens and prosody info.
     */
    phonemizeWithProsody(text: string): PhonemizeResult;
}

// ---------------------------------------------------------------------------
// UnicodeLanguageDetector
// ---------------------------------------------------------------------------

/**
 * Language detector using Unicode script-based heuristics.
 *
 * Detects language by analyzing Unicode code points in the text.
 * Detection priority: JA (Hiragana/Katakana) > ZH (CJK without Kana) >
 * language-specific scripts > EN (default fallback).
 *
 * Also supports segmenting mixed-language text into homogeneous chunks
 * for per-segment phonemization.
 *
 * @example
 * ```js
 * import { UnicodeLanguageDetector } from '@piper-plus/g2p/detect';
 *
 * const detector = new UnicodeLanguageDetector(['ja', 'en', 'zh']);
 * detector.detectLanguage('こんにちは'); // => 'ja'
 * detector.detectLanguage('Hello');      // => 'en'
 *
 * detector.segmentText('Hello, こんにちは');
 * // => [{ language: 'en', text: 'Hello, ' }, { language: 'ja', text: 'こんにちは' }]
 * ```
 */
export class UnicodeLanguageDetector {
    /**
     * @param languages - Supported language codes. Defaults to all supported languages.
     */
    constructor(languages?: Language[]);

    /**
     * Detect the primary language of the given text.
     *
     * @param text - Text to analyze.
     * @returns Detected language code.
     */
    detectLanguage(text: string): Language;

    /**
     * Segment text into language-homogeneous chunks.
     *
     * Adjacent characters of the same detected language are grouped together.
     *
     * @param text - Mixed-language text to segment.
     * @returns Array of segments, each with a language code and text content.
     */
    segmentText(text: string): Array<{ language: Language; text: string }>;
}

// ---------------------------------------------------------------------------
// Encoder
// ---------------------------------------------------------------------------

/**
 * Encodes IPA phoneme tokens to Piper-compatible phoneme ID sequences.
 *
 * Handles PUA mapping, phoneme-to-ID lookup, and BOS/EOS/inter-phoneme
 * padding insertion required by Piper TTS models.
 *
 * @example
 * ```js
 * import { Encoder } from '@piper-plus/g2p/encode';
 *
 * const encoder = new Encoder(config.phoneme_id_map);
 * const { phonemeIds } = encoder.encode(tokens);
 * const { phonemeIds, prosodyFlat } = encoder.encodeWithProsody(tokens, prosody);
 * ```
 */
export class Encoder {
    /**
     * @param phonemeIdMap - Phoneme-to-ID mapping from Piper model config (config.json).
     */
    constructor(phonemeIdMap: Record<string, number[]>);

    /**
     * Encode IPA tokens to phoneme IDs.
     *
     * Applies PUA mapping for multi-character tokens, looks up IDs from the
     * phoneme_id_map, and inserts BOS/EOS/inter-phoneme padding.
     *
     * @param tokens - IPA phoneme token array from a phonemize() call.
     * @returns Object containing the phoneme ID sequence.
     */
    encode(tokens: string[]): { phonemeIds: number[] };

    /**
     * Encode IPA tokens to phoneme IDs with aligned prosody features.
     *
     * Inserts null/zero prosody entries at padding positions to maintain
     * alignment between phonemeIds and prosody data.
     *
     * @param tokens - IPA phoneme token array.
     * @param prosody - Parallel prosody info array from phonemizeWithProsody().
     * @returns Encoded phoneme IDs and flattened prosody features.
     */
    encodeWithProsody(tokens: string[], prosody: (ProsodyInfo | null)[]): EncodeResult;
}

// ---------------------------------------------------------------------------
// CustomDictionary
// ---------------------------------------------------------------------------

/**
 * Custom dictionary for pronunciation overrides.
 *
 * Supports JSON v1.0/v2.0 format (compatible with Rust/C++ implementations)
 * for user-defined pronunciation rules. Entries are applied as text
 * replacements before phonemization.
 *
 * @example
 * ```js
 * import { CustomDictionary } from '@piper-plus/g2p/custom-dict';
 *
 * // From inline entries
 * const dict = new CustomDictionary({ 'GUI': ['g', 'uː', 'iː'] });
 *
 * // From JSON file
 * const dict = await CustomDictionary.fromJSON('/path/to/dict.json');
 *
 * const { text, replacements } = dict.apply('Open the GUI');
 * ```
 */
export class CustomDictionary {
    /**
     * @param entries - Dictionary entries mapping surface forms to phoneme token arrays.
     */
    constructor(entries?: Record<string, string[]>);

    /**
     * Load a custom dictionary from a JSON file (v1.0 or v2.0 format).
     *
     * Fetches the JSON from the given path or URL and parses entries.
     *
     * @param pathOrUrl - Path or URL to the JSON dictionary file.
     * @returns Loaded CustomDictionary instance.
     */
    static fromJSON(pathOrUrl: string): Promise<CustomDictionary>;

    /**
     * Apply dictionary entries to the input text.
     *
     * Matches surface forms in the text and records their phoneme replacements.
     *
     * @param text - Input text to process.
     * @returns Object with the (possibly modified) text and a map of replacements applied.
     * @deprecated Use {@link applyToText} instead for cross-language API consistency.
     */
    apply(text: string): { text: string; replacements: Map<string, string[]> };

    /**
     * Apply dictionary entries to the input text.
     *
     * Recommended method name, consistent with Python (`apply_to_text()`)
     * and Rust (`apply_to_text()`).
     *
     * @param text - Input text to process.
     * @returns Object with the (possibly modified) text and a map of replacements applied.
     */
    applyToText(text: string): { text: string; replacements: Map<string, string[]> };
}

// ---------------------------------------------------------------------------
// PUA mapping utilities
// ---------------------------------------------------------------------------

/**
 * PUA (Private Use Area) mapping table.
 *
 * Maps multi-character IPA tokens to single Unicode PUA codepoints for
 * compatibility with Piper TTS phoneme_id_map. Must match
 * token_mapper.py FIXED_PUA_MAPPING exactly.
 *
 * @example
 * ```js
 * PUA_MAP['a:']      // => '\ue000'
 * PUA_MAP['ch']      // => '\ue00e'
 * PUA_MAP['N_uvular'] // => '\ue01c'
 * ```
 */
export const PUA_MAP: Record<string, string>;

/**
 * Map a multi-character IPA token to its PUA single codepoint.
 *
 * Returns the original token unchanged if no PUA mapping exists.
 *
 * @param token - IPA token (e.g. "ch", "N_m", "a:").
 * @returns PUA codepoint or original token.
 */
export function mapToken(token: string): string;

/**
 * Reverse-map a PUA codepoint back to its multi-character IPA token.
 *
 * Returns the original character unchanged if it is not a PUA codepoint.
 *
 * @param puaChar - PUA codepoint character.
 * @returns Original multi-character IPA token or the input character.
 */
export function unmapToken(puaChar: string): string;

// ---------------------------------------------------------------------------
// phoneme-extract utilities (Japanese)
// ---------------------------------------------------------------------------

/**
 * Extract phonemes and prosody info from OpenJTalk full-context labels.
 *
 * Replicates the Python phonemize_japanese() logic:
 * - Kurihara-method prosody markers: `[`, `]`, `#`
 * - `pau` to `_` conversion
 * - Context-dependent N variants (N_m, N_n, N_ng, N_uvular)
 * - PUA mapping for multi-character tokens
 * - A1/A2/A3 prosody feature extraction
 *
 * @param labels - Full-context labels from OpenJTalk (newline-separated).
 * @returns Object with PUA-mapped token array and parallel prosody array.
 */
export function extractPhonemesFromLabels(labels: string): {
    tokens: string[];
    prosody: (ProsodyInfo | null)[];
};

/**
 * Apply context-dependent N phoneme rules.
 *
 * Replaces generic "N" tokens with context-specific variants based on
 * the following phoneme:
 * - N_m: before bilabials (m, my, b, by, p, py)
 * - N_n: before alveolars (n, ny, t, ty, d, dy, ts, ch)
 * - N_ng: before velars (k, ky, kw, g, gy, gw)
 * - N_uvular: word-final or before vowels
 *
 * Matches _apply_n_phoneme_rules() in japanese.py.
 *
 * @param tokens - Array of phoneme tokens potentially containing "N".
 * @returns New array with "N" replaced by contextual variants.
 */
export function applyNPhonemeRules(tokens: string[]): string[];

/**
 * Map multi-character IPA tokens to PUA single codepoints.
 *
 * Applies the PUA_MAP to each token in the array. Single-character tokens
 * and tokens without a PUA mapping are passed through unchanged.
 *
 * Matches map_sequence() in token_mapper.py.
 *
 * @param tokens - Array of phoneme tokens.
 * @returns New array with multi-character tokens replaced by PUA codepoints.
 */
export function mapToPUA(tokens: string[]): string[];
