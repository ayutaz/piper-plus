/**
 * ChineseG2P -- character-based Chinese G2P for @piper-plus/g2p.
 *
 * Each character in the input text is looked up in the phoneme_id_map.
 * Characters not found in the map are passed through as-is.
 * No external dependencies required.
 *
 * Supports optional WASM-backed phonemization: when a `wasmPhonemizer`
 * is provided, it is used as the primary path. On WASM failure, the
 * class falls back to character-level passthrough and records the error
 * in the `lastError` property for caller diagnostics.
 */

export class ChineseG2P {
    /**
     * @param {object} [options]
     * @param {Record<string, number[]>} [options.phonemeIdMap]
     *   Mapping from character/phoneme string to array of phoneme IDs.
     *   Typically loaded from the model's config.json `phoneme_id_map`.
     * @param {object} [options.wasmPhonemizer]
     *   Optional WASM phonemizer instance with a `.phonemize(text, lang)` method.
     */
    constructor(options = {}) {
        this.phonemeIdMap = options.phonemeIdMap || null;
        this._wasmPhonemizer = options.wasmPhonemizer || null;
        /** @private */
        this._lastError = null;
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
     * 'fallback' otherwise.
     * @type {'wasm'|'fallback'}
     */
    get mode() {
        if (this._wasmPhonemizer) return 'wasm';
        return 'fallback';
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
     * Convert Chinese text to phoneme tokens.
     *
     * When a WASM phonemizer is available, it is tried first.
     * On failure, falls back to character-level passthrough and
     * stores the error reason in `lastError`.
     *
     * @param {string} text - Input Chinese text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemize(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }
        if (this._wasmPhonemizer) {
            return this._wasmPhonemizerPath(text);
        }
        return this._fallbackPhonemize(text);
    }

    /**
     * Convert Chinese text to phoneme tokens with prosody.
     * Chinese G2P provides fixed prosody values (a1=0, a2=0, a3=0).
     *
     * @param {string} text - Input Chinese text.
     * @returns {{ tokens: string[], prosody: ({ a1: number, a2: number, a3: number })[] }}
     */
    phonemizeWithProsody(text) {
        const { tokens } = this.phonemize(text);
        const prosody = tokens.map(() => ({ a1: 0, a2: 0, a3: 0 }));
        return { tokens, prosody };
    }

    /**
     * @private
     * Attempt WASM phonemization; fall back to character passthrough on error.
     * @param {string} text
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    _wasmPhonemizerPath(text) {
        try {
            const result = this._wasmPhonemizer.phonemize(text, 'zh');
            this._lastError = null;
            const tokens = result.tokens || [];
            return { tokens, prosody: new Array(tokens.length).fill(null) };
        } catch (e) {
            this._lastError = `WASM phonemize failed: ${e.message || e}`;
            return this._fallbackPhonemize(text);
        }
    }

    /**
     * @private
     * Character-level passthrough fallback.
     * @param {string} text
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    _fallbackPhonemize(text) {
        const tokens = [];

        for (const char of text) {
            if (this.phonemeIdMap && this.phonemeIdMap[char]) {
                // Character found in map -- emit it as a token
                tokens.push(char);
            } else {
                // Unknown character -- pass through
                tokens.push(char);
            }
        }

        const prosody = new Array(tokens.length).fill(null);
        return { tokens, prosody };
    }
}
