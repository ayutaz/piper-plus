/**
 * FrenchG2P -- character-based French G2P for @piper-plus/g2p.
 *
 * Each character in the input text is lowercased and looked up in
 * the phoneme_id_map. Characters not found in the map are passed
 * through as-is (except spaces, which are looked up separately).
 * No external dependencies required.
 */

export class FrenchG2P {
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
     * Convert French text to phoneme tokens.
     *
     * Text is lowercased and each character is looked up in the
     * phoneme_id_map. Characters not found are passed through unchanged.
     *
     * @param {string} text - Input French text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemize(text) {
        const tokens = [];
        const lower = text.toLowerCase();

        for (const char of lower) {
            if (this.phonemeIdMap && this.phonemeIdMap[char]) {
                tokens.push(char);
            } else if (char === ' ' && this.phonemeIdMap && this.phonemeIdMap[' ']) {
                tokens.push(' ');
            } else {
                // Unknown character -- pass through
                tokens.push(char);
            }
        }

        const prosody = new Array(tokens.length).fill(null);
        return { tokens, prosody };
    }

    /**
     * Convert French text to phoneme tokens with prosody.
     * French G2P does not provide prosody information, so prosody
     * is always an array of nulls matching the token count.
     *
     * @param {string} text - Input French text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemizeWithProsody(text) {
        return this.phonemize(text);
    }
}
