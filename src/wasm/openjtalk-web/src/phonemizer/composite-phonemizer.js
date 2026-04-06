/**
 * Composite phonemizer that routes to language-specific PhonemizerInterface instances.
 * @module piper-plus/phonemizer/composite-phonemizer
 */

export class CompositePhonemizer {
  /**
   * @param {object} params
   * @param {Map<string, object>} params.phonemizers
   *   Language code to PhonemizerInterface mapping.
   * @param {object} [params.fallback]
   *   Default phonemizer used when language is unknown.
   * @param {object} [params.detector]
   *   Preferred phonemizer for detectLanguage() (typically Rust WASM).
   */
  constructor({ phonemizers, fallback, detector }) {
    /** @private */
    this._phonemizers = phonemizers;
    /** @private */
    this._fallback = fallback || null;
    /** @private */
    this._detector = detector || null;
    /** @private */
    this._disposed = false;
  }

  /**
   * Encode text into phoneme IDs and optional prosody features.
   * Routes to the phonemizer registered for the given or detected language.
   * @param {string} text
   * @param {string} [language]
   * @returns {{ phonemeIds: number[], prosodyFeatures: number[][]|null }}
   */
  encode(text, language) {
    const lang = language || this.detectLanguage(text);
    const phonemizer = this._phonemizers.get(lang) || this._fallback;
    if (!phonemizer) {
      throw new Error(`No phonemizer registered for language "${lang}" and no fallback configured`);
    }
    return phonemizer.encode(text, lang);
  }

  /**
   * Detect language of given text.
   * Prefers the primary detector (first registered phonemizer, typically Rust WASM
   * which supports all languages). Falls back to the fallback phonemizer.
   * @param {string} text
   * @returns {string}
   */
  detectLanguage(text) {
    if (this._detector) {
      return this._detector.detectLanguage(text);
    }
    const first = this._phonemizers.values().next().value;
    if (first) {
      return first.detectLanguage(text);
    }
    if (this._fallback) {
      return this._fallback.detectLanguage(text);
    }
    throw new Error('No phonemizers registered');
  }

  /** @returns {string[]} */
  get supportedLanguages() {
    const langs = new Set();
    for (const [lang] of this._phonemizers) {
      langs.add(lang);
    }
    if (this._fallback) {
      for (const lang of this._fallback.supportedLanguages) {
        langs.add(lang);
      }
    }
    return [...langs];
  }

  /** Release all phonemizer resources. Safe to call multiple times. */
  dispose() {
    if (this._disposed) return;
    this._disposed = true;

    const disposed = new Set();
    for (const phonemizer of this._phonemizers.values()) {
      if (!disposed.has(phonemizer)) {
        disposed.add(phonemizer);
        phonemizer.dispose();
      }
    }
    if (this._fallback && !disposed.has(this._fallback)) {
      this._fallback.dispose();
    }
  }
}
