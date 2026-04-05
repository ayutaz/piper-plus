/**
 * ChineseG2P -- Chinese G2P for @piper-plus/g2p.
 *
 * Two operational modes:
 *   1. **WASM path** (browser): calls `wasmPhonemizer.phonemize(text, 'zh')`
 *      for full pinyin-to-IPA conversion with tone sandhi.
 *   2. **Fallback path** (Node.js / no WASM): character-level tokenization
 *      where each character becomes its own token.
 *
 * The WASM phonemizer is injected via the constructor options so that this
 * module has no hard dependency on wasm-bindgen or onnxruntime-web.
 */

export class ChineseG2P {
    /**
     * @param {object} [options]
     * @param {Record<string, number[]>} [options.phonemeIdMap]
     *   Mapping from character/phoneme string to array of phoneme IDs.
     *   Typically loaded from the model's config.json `phoneme_id_map`.
     * @param {object} [options.wasmPhonemizer]
     *   A WASM phonemizer instance with a `phonemize(text, lang)` method.
     *   When provided, phonemization uses the Rust WASM pipeline.
     */
    constructor(options = {}) {
        this.phonemeIdMap = options.phonemeIdMap || null;
        /** @private */
        this._wasmPhonemizer = options.wasmPhonemizer || null;
    }

    /** @returns {'zh'} */
    get languageCode() {
        return 'zh';
    }

    /**
     * Set or replace the phoneme ID map.
     * @param {Record<string, number[]>} phonemeIdMap
     */
    setPhonemeIdMap(phonemeIdMap) {
        this.phonemeIdMap = phonemeIdMap;
    }

    /**
     * Whether the WASM phonemizer is loaded and available.
     * @returns {boolean}
     */
    get isWasmInitialized() {
        return this._wasmPhonemizer !== null;
    }

    /**
     * Convert Chinese text to phoneme tokens.
     *
     * Uses the WASM pipeline when available, otherwise falls back to
     * character-level tokenization.
     *
     * @param {string} text - Input Chinese text.
     * @returns {{ tokens: string[], prosody: (null|object)[] }}
     */
    phonemize(text) {
        if (this._wasmPhonemizer) {
            return this._wasmPhonemizerPath(text);
        }
        return this._fallbackPhonemize(text);
    }

    /**
     * Convert Chinese text to phoneme tokens with prosody.
     * Alias for phonemize() -- prosody info depends on the active backend.
     *
     * @param {string} text - Input Chinese text.
     * @returns {{ tokens: string[], prosody: (null|object)[] }}
     */
    phonemizeWithProsody(text) {
        return this.phonemize(text);
    }

    // ---- Private helpers ----

    /**
     * WASM-backed phonemization path.
     * @private
     * @param {string} text
     * @returns {{ tokens: string[], prosody: (null|object)[] }}
     */
    _wasmPhonemizerPath(text) {
        const result = this._wasmPhonemizer.phonemize(text, 'zh');
        return {
            tokens: result.tokens || [],
            prosody: result.prosody || [],
        };
    }

    /**
     * Fallback character-level tokenization for CJK text.
     *
     * Each character becomes its own token. Whitespace is preserved as ' '.
     * This provides basic functionality when WASM is not available.
     *
     * @private
     * @param {string} text
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    _fallbackPhonemize(text) {
        if (!text) {
            return { tokens: [], prosody: [] };
        }

        const tokens = [];
        for (const char of text) {
            if (char.trim() === '') {
                tokens.push(' ');
            } else {
                tokens.push(char);
            }
        }

        const prosody = new Array(tokens.length).fill(null);
        return { tokens, prosody };
    }
}
