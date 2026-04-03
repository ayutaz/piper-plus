/**
 * ChineseG2P -- character-based Chinese G2P for @piper-plus/g2p.
 *
 * Each character in the input text is looked up in the phoneme_id_map.
 * Characters not found in the map are passed through as-is.
 * No external dependencies required.
 */

export class ChineseG2P {
    /**
     * @param {object} [options]
     * @param {Record<string, number[]>} [options.phonemeIdMap]
     *   Mapping from character/phoneme string to array of phoneme IDs.
     *   Typically loaded from the model's config.json `phoneme_id_map`.
     */
    constructor(options = {}) {
        this.phonemeIdMap = options.phonemeIdMap || null;
    }

    /**
     * Set or replace the phoneme ID map.
     * @param {Record<string, number[]>} phonemeIdMap
     */
    setPhonemeIdMap(phonemeIdMap) {
        this.phonemeIdMap = phonemeIdMap;
    }

    /**
     * Convert Chinese text to phoneme tokens.
     *
     * Each character is looked up directly in the phoneme_id_map.
     * Characters not found in the map are passed through unchanged.
     *
     * @param {string} text - Input Chinese text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemize(text) {
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

    /**
     * Convert Chinese text to phoneme tokens with prosody.
     * Chinese G2P does not provide prosody information, so prosody
     * is always an array of nulls matching the token count.
     *
     * @param {string} text - Input Chinese text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemizeWithProsody(text) {
        return this.phonemize(text);
    }
}
