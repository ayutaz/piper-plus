/**
 * UnicodeLanguageDetector -- Unicode range-based language detection
 * for @piper-plus/g2p.
 *
 * Mirrors the Python UnicodeLanguageDetector in
 * src/python/piper_train/phonemize/multilingual.py.
 *
 * Detection priority:
 *   Kana (Hiragana/Katakana) -> 'ja'
 *   Hangul                   -> 'ko' (if supported)
 *   CJK Ideographs           -> 'ja' (if context has kana) or 'zh'
 *   Fullwidth Latin           -> default Latin language
 *   CJK Punctuation          -> 'ja' (if supported)
 *   Latin                    -> default Latin language
 *   Otherwise                -> null (neutral: whitespace, digits, punctuation)
 *
 * Pure JavaScript, no external dependencies.
 */

import svFunctionWordsData from "../data/sv_function_words.json" with { type: "json" };

// ----------------------------------------------------------------------------
// Swedish per-word LID data (Issue #539)
//
// The canonical `sv_function_words.json` is shipped with this package and
// loaded here as a JSON ES module import (the browser/ESM analog of Go's
// `//go:embed` and C#'s embedded resource — the asset travels with the code).
// BOTH the lowercased `function_words` set (46) and the `strong_chars` set
// (å U+00E5 / Å U+00C5) are parsed defensively: any malformed/missing field
// degrades to an EMPTY set, which makes the per-word post-pass a complete
// no-op (graceful degradation, matching the Python/Rust/Go/C++/C# runtimes —
// there is NO hardcoded word/char fallback). Unknown top-level keys (e.g. a
// future `schema_version` bump) are ignored for forward-compatibility.
//
// This LID-discriminative list is intentionally DISTINCT from the
// prosody/stress function-word list in `sv/index.js` — do not sync the two.
function _loadSwedishLidData(data) {
  const functionWords = new Set();
  const strongChars = new Set();
  if (!data || typeof data !== "object") {
    return { functionWords, strongChars };
  }
  // function_words: list[str], lowercased, non-empty entries only.
  if (Array.isArray(data.function_words)) {
    for (const w of data.function_words) {
      if (typeof w === "string" && w) {
        functionWords.add(w.toLowerCase());
      }
    }
  }
  // strong_chars: list[str]; each non-empty string contributes its characters.
  // Iterating per code point mirrors Go's per-rune / C#'s per-char expansion
  // for byte-identical cross-runtime parity (canonically å U+00E5 / Å U+00C5).
  if (Array.isArray(data.strong_chars)) {
    for (const s of data.strong_chars) {
      if (typeof s === "string" && s) {
        for (const ch of s) {
          strongChars.add(ch);
        }
      }
    }
  }
  return { functionWords, strongChars };
}

const { functionWords: SV_FUNCTION_WORDS, strongChars: SV_STRONG_CHARS } =
  _loadSwedishLidData(svFunctionWordsData);

export class UnicodeLanguageDetector {
  /**
   * @param {string[]} [languages=['ja', 'en', 'zh', 'es', 'fr', 'pt', 'sv']]
   *   Language codes supported by this detector.
   * @param {object} [options]
   * @param {string} [options.defaultLatinLanguage='en']
   *   Language code assigned to Latin-script characters.
   */
  constructor(languages = ["ja", "en", "zh", "es", "fr", "pt", "sv"], options = {}) {
    this.languages = new Set(languages);
    this.defaultLatinLanguage = options.defaultLatinLanguage || "en";

    this._hasJa = this.languages.has("ja");
    this._hasZh = this.languages.has("zh");
    this._hasKo = this.languages.has("ko");
    this._hasSv = this.languages.has("sv");

    // Conservative gate for the Swedish per-word post-pass (Issue #539):
    // only enable when Swedish is requested ALONGSIDE >=2 Latin-script
    // languages (a genuine code-switching context), not for a Swedish-only
    // model. Mirrors Python's `_detect_swedish`.
    const latinLangs = new Set();
    for (const lang of this.languages) {
      if (lang === "en" || lang === "es" || lang === "pt" || lang === "fr" || lang === "sv") {
        latinLangs.add(lang);
      }
    }
    /** @private */
    this._detectSwedish = this._hasSv && latinLangs.size >= 2;
  }

  // ------------------------------------------------------------------
  // Unicode range helpers (character code checks, no regex needed)
  // ------------------------------------------------------------------

  /** @private */
  _isKana(code) {
    // Hiragana: U+3040-309F, Katakana: U+30A0-30FF,
    // Katakana Phonetic Extensions: U+31F0-31FF
    return (
      (code >= 0x3040 && code <= 0x309f) ||
      (code >= 0x30a0 && code <= 0x30ff) ||
      (code >= 0x31f0 && code <= 0x31ff)
    );
  }

  /** @private */
  _isCJK(code) {
    // CJK Unified Ideographs: U+4E00-9FFF
    // CJK Extension A: U+3400-4DBF
    // CJK Compatibility Ideographs: U+F900-FAFF
    return (
      (code >= 0x4e00 && code <= 0x9fff) ||
      (code >= 0x3400 && code <= 0x4dbf) ||
      (code >= 0xf900 && code <= 0xfaff)
    );
  }

  /** @private */
  _isHangul(code) {
    // Hangul Syllables: U+AC00-D7AF
    // Hangul Jamo: U+1100-11FF
    // Hangul Compatibility Jamo: U+3130-318F
    return (
      (code >= 0xac00 && code <= 0xd7af) ||
      (code >= 0x1100 && code <= 0x11ff) ||
      (code >= 0x3130 && code <= 0x318f)
    );
  }

  /** @private */
  _isFullwidthLatin(code) {
    // Fullwidth Latin uppercase: U+FF21-FF3A
    // Fullwidth Latin lowercase: U+FF41-FF5A
    return (code >= 0xff21 && code <= 0xff3a) || (code >= 0xff41 && code <= 0xff5a);
  }

  /** @private */
  _isJaPunctuation(code) {
    // CJK Symbols and Punctuation: U+3000-303F
    // Fullwidth digits and symbols: U+FF00-FF20
    // Fullwidth brackets and symbols: U+FF3B-FF40
    // Fullwidth braces onwards: U+FF5B-FFEF
    return (
      (code >= 0x3000 && code <= 0x303f) ||
      (code >= 0xff00 && code <= 0xff20) ||
      (code >= 0xff3b && code <= 0xff40) ||
      (code >= 0xff5b && code <= 0xffef)
    );
  }

  /** @private */
  _isLatin(code) {
    // Basic Latin letters: A-Z, a-z
    // Latin Extended: U+00C0-00D6, U+00D8-00F6, U+00F8-00FF
    // (Excludes multiplication sign U+00D7 and division sign U+00F7)
    return (
      (code >= 0x41 && code <= 0x5a) ||
      (code >= 0x61 && code <= 0x7a) ||
      (code >= 0xc0 && code <= 0xd6) ||
      (code >= 0xd8 && code <= 0xf6) ||
      (code >= 0xf8 && code <= 0xff)
    );
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /**
   * Check if text contains any kana characters.
   * @param {string} text
   * @returns {boolean}
   */
  hasKana(text) {
    for (const char of text) {
      if (this._isKana(char.codePointAt(0))) {
        return true;
      }
    }
    return false;
  }

  /**
   * Detect language for a single character.
   *
   * @param {string} ch - Single character.
   * @param {boolean} [contextHasKana=false] - Whether surrounding text
   *   contains kana (used for CJK disambiguation between JA and ZH).
   * @returns {string|null} Language code, or null for neutral characters.
   */
  detectChar(ch, contextHasKana = false) {
    const code = ch.codePointAt(0);

    // Kana -> always Japanese
    if (this._isKana(code)) {
      return this._hasJa ? "ja" : null;
    }

    // Hangul -> Korean
    if (this._isHangul(code)) {
      return this._hasKo ? "ko" : null;
    }

    // CJK ideographs -> JA or ZH depending on context
    if (this._isCJK(code)) {
      if (this._hasJa && this._hasZh) {
        return contextHasKana ? "ja" : "zh";
      }
      if (this._hasJa) {
        return "ja";
      }
      if (this._hasZh) {
        return "zh";
      }
      return null;
    }

    // Fullwidth Latin letters -> treat as Latin, not Japanese
    if (this._isFullwidthLatin(code)) {
      return this.languages.has(this.defaultLatinLanguage) ? this.defaultLatinLanguage : null;
    }

    // Japanese-specific punctuation
    if (this._isJaPunctuation(code)) {
      return this._hasJa ? "ja" : null;
    }

    // Latin characters.
    //
    // NOTE (Issue #539): the Swedish letters å/ä/ö (and their uppercase forms)
    // are deliberately NOT special-cased here — they fall through to the
    // default Latin language, exactly like every other runtime's char-level
    // detection. Returning "sv" per-character would (a) FRAGMENT words such as
    // "för" into f|ö|r, and (b) miss function words like "och"/"jag" that have
    // no special char. Swedish is decided by the conservative word-level
    // post-pass in `_refineLatinSegmentsForSwedish` instead.
    if (this._isLatin(code)) {
      return this.languages.has(this.defaultLatinLanguage) ? this.defaultLatinLanguage : null;
    }

    // Neutral: whitespace, digits, ASCII punctuation
    return null;
  }

  /**
   * Detect the dominant language of a text string.
   *
   * Derived from {@link segmentText} (which runs the Swedish per-word
   * post-pass): the language with the greatest total segment length wins,
   * with ties broken by segment order (first wins). Falls back to the default
   * Latin language when no language-specific segment is produced.
   *
   * NOTE (Issue #539): this is computed from segments rather than a naive
   * per-character tally so it stays CONSISTENT with the word-level Swedish
   * post-pass. Because å/ä/ö no longer return "sv" at char level, a per-char
   * count could never yield "sv"; going through `segmentText` lets Swedish
   * text (e.g. "och jag", "från") detect as sv via the post-pass.
   *
   * @param {string} text
   * @returns {string} Detected language code.
   */
  detectLanguage(text) {
    const segments = this.segmentText(text);

    // No language-specific segment (empty / digits / punctuation only).
    if (segments.length === 0) {
      return this.defaultLatinLanguage;
    }

    // Sum total character length per language, preserving first-seen order so
    // that ties resolve to the earliest segment (matches the previous
    // per-character tally where the first-counted language won a tie).
    const totals = new Map();
    for (const segment of segments) {
      const prev = totals.get(segment.language) || 0;
      totals.set(segment.language, prev + segment.text.length);
    }

    let bestLang = this.defaultLatinLanguage;
    let bestCount = 0;
    for (const [lang, count] of totals) {
      if (count > bestCount) {
        bestCount = count;
        bestLang = lang;
      }
    }

    // When the result is a single default-Latin segment, emit a debug hint so
    // that developers know the result is a best-guess default rather than a
    // confident detection.
    if (totals.size <= 1 && bestLang === this.defaultLatinLanguage && bestCount > 0) {
      console.debug(
        `[g2p/detect] Latin-only text detected -- defaulting to '${bestLang}'. ` +
          "If this text is ES, FR, PT, or SV, pass options.language explicitly."
      );
    }

    return bestLang;
  }

  /**
   * Segment text into consecutive runs of the same language.
   *
   * Neutral characters (whitespace, digits, punctuation) are absorbed
   * into the preceding segment. If the text starts with neutral
   * characters, they are absorbed into the first language segment
   * that follows.
   *
   * @param {string} text
   * @returns {Array<{ language: string, text: string }>}
   */
  segmentText(text) {
    if (!text || !text.trim()) {
      return [];
    }

    const contextHasKana = this.hasKana(text);
    const segments = [];
    let currentLang = null;
    let currentChars = [];

    for (const ch of text) {
      const lang = this.detectChar(ch, contextHasKana);

      if (lang !== null && lang !== currentLang && currentLang !== null) {
        // Language changed -- flush current segment
        segments.push({
          language: currentLang,
          text: currentChars.join(""),
        });
        currentChars = [];
      }

      if (lang !== null) {
        currentLang = lang;
      }
      currentChars.push(ch);
    }

    // Flush remaining characters
    if (currentChars.length > 0 && currentLang !== null) {
      segments.push({
        language: currentLang,
        text: currentChars.join(""),
      });
    }

    // If no language-specific characters were detected (e.g. text is
    // only numbers or punctuation), fall back to the default language
    if (segments.length === 0 && text.trim()) {
      segments.push({
        language: this.defaultLatinLanguage,
        text: text,
      });
    }

    // Conservative Swedish per-word post-pass (Issue #539): re-classify
    // default-Latin segments containing a strong Swedish indicator to "sv".
    if (this._detectSwedish) {
      return this._refineLatinSegmentsForSwedish(segments);
    }

    return segments;
  }

  /**
   * @private
   * Re-classify default-Latin segments as Swedish (conservative, Issue #539).
   *
   * For each segment whose language is the default Latin language, split on
   * whitespace and inspect each word: a word is a STRONG Swedish indicator iff
   * (its lowercased, punctuation-stripped form is in the function-word set) OR
   * (it contains a char in the strong-char set, canonically å/Å). The weak
   * chars ä/ö are deliberately NOT strong on their own (shared with
   * German/Finnish/loanwords), so they never trigger reclassification here. If
   * ANY word in the segment is strong, the WHOLE segment is reclassified to
   * "sv" (segments are not fragmented). Non-default-language segments and the
   * Swedish-default case are passed through unchanged.
   *
   * @param {Array<{ language: string, text: string }>} segments
   * @returns {Array<{ language: string, text: string }>}
   */
  _refineLatinSegmentsForSwedish(segments) {
    const def = this.defaultLatinLanguage;
    if (def === "sv") {
      return segments;
    }

    const result = [];
    for (const segment of segments) {
      if (segment.language !== def) {
        result.push(segment);
        continue;
      }
      let strong = false;
      for (const rawWord of segment.text.split(/\s+/)) {
        // The 5-mark strip set (. , ; : ! ?) is PINNED: all runtimes
        // (Python/C++/C#/Go) strip exactly these ASCII marks, and byte-identical
        // tokenization across runtimes is required for parity. Do not broaden it
        // (no Unicode punctuation, no smart quotes, etc.).
        const word = _stripPinnedMarks(rawWord).toLowerCase();
        if (!word) {
          continue;
        }
        if (SV_FUNCTION_WORDS.has(word)) {
          strong = true;
          break;
        }
        // `word` is already lowercased, so the å/Å strong-char set only needs
        // the lowercase form to match; the uppercase Å entry is kept for
        // cross-runtime parity (the canonical JSON ships both forms).
        let hit = false;
        for (const ch of word) {
          if (SV_STRONG_CHARS.has(ch)) {
            hit = true;
            break;
          }
        }
        if (hit) {
          strong = true;
          break;
        }
      }
      result.push(strong ? { language: "sv", text: segment.text } : segment);
    }
    return result;
  }
}

/**
 * Strip the PINNED 5 leading/trailing ASCII punctuation marks (. , ; : ! ?)
 * from a word. Mirrors Python's `str.strip(".,;:!?")`: only these exact marks
 * are removed, and only from the ends (interior marks are preserved). Pinned
 * for byte-identical cross-runtime tokenization (Issue #539).
 *
 * @param {string} word
 * @returns {string}
 */
function _stripPinnedMarks(word) {
  const marks = new Set([".", ",", ";", ":", "!", "?"]);
  let start = 0;
  let end = word.length;
  while (start < end && marks.has(word[start])) {
    start += 1;
  }
  while (end > start && marks.has(word[end - 1])) {
    end -= 1;
  }
  return word.slice(start, end);
}
