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
  _isSwedishSpecific(code) {
    // å (U+00E5), ä (U+00E4), ö (U+00F6)
    // Å (U+00C5), Ä (U+00C4), Ö (U+00D6)
    return (
      code === 0xe5 ||
      code === 0xe4 ||
      code === 0xf6 ||
      code === 0xc5 ||
      code === 0xc4 ||
      code === 0xd6
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

    // Swedish-specific characters: å (U+00E5), ä (U+00E4), ö (U+00F6)
    if (this._isSwedishSpecific(code)) {
      return this._hasSv
        ? "sv"
        : this.languages.has(this.defaultLatinLanguage)
          ? this.defaultLatinLanguage
          : null;
    }

    // Latin characters
    if (this._isLatin(code)) {
      return this.languages.has(this.defaultLatinLanguage) ? this.defaultLatinLanguage : null;
    }

    // Neutral: whitespace, digits, ASCII punctuation
    return null;
  }

  /**
   * Detect the dominant language of a text string.
   *
   * Counts language-specific characters and returns the language with
   * the highest count. Falls back to the default Latin language if
   * no language-specific characters are found.
   *
   * @param {string} text
   * @returns {string} Detected language code.
   */
  detectLanguage(text) {
    const contextHasKana = this.hasKana(text);
    const counts = {};

    for (const char of text) {
      const lang = this.detectChar(char, contextHasKana);
      if (lang !== null) {
        counts[lang] = (counts[lang] || 0) + 1;
      }
    }

    // Return the language with the most characters
    let bestLang = this.defaultLatinLanguage;
    let bestCount = 0;
    for (const [lang, count] of Object.entries(counts)) {
      if (count > bestCount) {
        bestCount = count;
        bestLang = lang;
      }
    }

    // When all detected characters are Latin, emit a debug hint so
    // that developers know the result is a best-guess default rather
    // than a confident detection.
    const uniqueLangs = Object.keys(counts);
    if (uniqueLangs.length <= 1 && bestLang === this.defaultLatinLanguage && bestCount > 0) {
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

    return segments;
  }
}
