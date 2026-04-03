/**
 * Japanese phoneme extraction from OpenJTalk full-context labels.
 *
 * Replicates the Python phonemize_japanese() logic with prosody info:
 * - Kurihara-method prosody markers: [, ], #
 * - pau → _ conversion
 * - Context-dependent N variants (N_m, N_n, N_ng, N_uvular)
 * - PUA mapping matching token_mapper.py FIXED_PUA_MAPPING
 * - A1/A2/A3 prosody features extraction (ProsodyInfo)
 *
 * Based on: src/wasm/openjtalk-web/src/japanese_phoneme_extract.js
 */

// PUA mapping - must match token_mapper.py FIXED_PUA_MAPPING exactly
const PUA_MAP = {
    'a:': '\ue000', 'i:': '\ue001', 'u:': '\ue002', 'e:': '\ue003', 'o:': '\ue004',
    'cl': '\ue005',
    'ky': '\ue006', 'kw': '\ue007', 'gy': '\ue008', 'gw': '\ue009',
    'sh': '\ue00a', 'ch': '\ue00e', 'ts': '\ue00f',
    'ny': '\ue00b', 'hy': '\ue00c', 'my': '\ue00d',
    'ry': '\ue010', 'ty': '\ue011', 'dy': '\ue012',
    'by': '\ue013', 'py': '\ue014',
    'N_m': '\ue019', 'N_n': '\ue01a', 'N_ng': '\ue01b', 'N_uvular': '\ue01c'
};

// Regex patterns matching the Python implementation
const RE_PHONEME = /-([^+]+)\+/;
const RE_A1 = /\/A:([\d-]+)\+/;
const RE_A2 = /\+([0-9]+)\+/;
const RE_A3 = /\+([0-9]+)\//;

// Tokens to skip when looking ahead for N-variant rules
const SKIP_TOKENS = new Set(['_', '#', '[', ']', '^', '$', '?', '?!', '?.', '?~']);

/**
 * @typedef {Object} ProsodyInfo
 * @property {number} a1 - Accent type (relative position to accent nucleus)
 * @property {number} a2 - Position within accent phrase (1-indexed from start)
 * @property {number} a3 - Position within accent phrase (1-indexed from end)
 */

/**
 * Apply context-dependent N phoneme rules.
 * Matches _apply_n_phoneme_rules() in japanese.py
 *
 * @param {string[]} tokens - Array of phoneme tokens
 * @returns {string[]} Tokens with N replaced by N_m/N_n/N_ng/N_uvular
 */
export function applyNPhonemeRules(tokens) {
    const result = [];
    for (let i = 0; i < tokens.length; i++) {
        if (tokens[i] !== 'N') {
            result.push(tokens[i]);
            continue;
        }

        // Look ahead to find next actual phoneme
        let nextPhoneme = null;
        for (let j = i + 1; j < tokens.length; j++) {
            if (!SKIP_TOKENS.has(tokens[j])) {
                nextPhoneme = tokens[j];
                break;
            }
        }

        if (nextPhoneme === null) {
            result.push('N_uvular');
        } else if (['m', 'my', 'b', 'by', 'p', 'py'].includes(nextPhoneme)) {
            result.push('N_m');
        } else if (['n', 'ny', 't', 'ty', 'd', 'dy', 'ts', 'ch'].includes(nextPhoneme)) {
            result.push('N_n');
        } else if (['k', 'ky', 'kw', 'g', 'gy', 'gw'].includes(nextPhoneme)) {
            result.push('N_ng');
        } else {
            result.push('N_uvular');
        }
    }
    return result;
}

/**
 * Map multi-character tokens to PUA single codepoints.
 * Matches map_sequence() in token_mapper.py
 *
 * @param {string[]} tokens - Array of phoneme tokens
 * @returns {string[]} Tokens with multi-char sequences replaced by PUA codepoints
 */
export function mapToPUA(tokens) {
    return tokens.map(t => PUA_MAP[t] || t);
}

/**
 * Extract phonemes and prosody info from OpenJTalk full-context labels.
 * Extends phonemize_japanese() from japanese.py to also return A1/A2/A3
 * prosody features for each token.
 *
 * @param {string} labels - Full-context labels (newline-separated)
 * @returns {{ tokens: string[], prosody: (ProsodyInfo | null)[] }}
 *   tokens: PUA-mapped phoneme token array
 *   prosody: parallel array; ProsodyInfo for phonemes, null for markers/BOS/EOS/pause
 */
export function extractPhonemesFromLabels(labels) {
    const lines = labels.split('\n').filter(line => line.trim());
    const tokens = [];
    /** @type {(ProsodyInfo | null)[]} */
    const prosody = [];

    for (let idx = 0; idx < lines.length; idx++) {
        const line = lines[idx];
        const mPh = line.match(RE_PHONEME);
        if (!mPh) continue;
        const phoneme = mPh[1];

        // Beginning / end silence handling
        if (phoneme === 'sil') {
            if (idx === 0) {
                tokens.push('^');
                prosody.push(null);
            } else if (idx === lines.length - 1) {
                tokens.push('$');
                prosody.push(null);
            }
            continue;
        }

        // Short pause -> _
        if (phoneme === 'pau') {
            tokens.push('_');
            prosody.push(null);
            continue;
        }

        // Extract A1/A2/A3 for prosody
        const mA1 = line.match(RE_A1);
        const mA2 = line.match(RE_A2);
        const mA3 = line.match(RE_A3);

        let a1 = null;
        let a2 = null;
        let a3 = null;
        if (mA1 && mA2 && mA3) {
            a1 = parseInt(mA1[1], 10);
            a2 = parseInt(mA2[1], 10);
            a3 = parseInt(mA3[1], 10);
        }

        // Add phoneme token with prosody info
        tokens.push(phoneme);
        prosody.push(a1 !== null ? { a1, a2, a3 } : null);

        // Prosody markers (derived from A1/A2/A3)
        if (a1 === null) continue;

        // Look-ahead for a2_next
        let a2Next = -1;
        if (idx < lines.length - 1) {
            const mA2Next = lines[idx + 1].match(RE_A2);
            if (mA2Next) a2Next = parseInt(mA2Next[1], 10);
        }

        // Insert accent nucleus mark "]"
        if (a1 === 0 && a2Next === a2 + 1) {
            tokens.push(']');
            prosody.push(null);
        }

        // Insert accent phrase boundary "#"
        if (a2 === a3 && a2Next === 1) {
            tokens.push('#');
            prosody.push(null);
        }

        // Insert rising mark "["
        if (a2 === 1 && a2Next === 2) {
            tokens.push('[');
            prosody.push(null);
        }
    }

    // Apply N phoneme rules (prosody stays aligned because N->N_variant is 1:1)
    const withNVariants = applyNPhonemeRules(tokens);

    // Map to PUA codepoints (prosody stays aligned because PUA is 1:1)
    const puaMapped = mapToPUA(withNVariants);

    return { tokens: puaMapped, prosody };
}

export { PUA_MAP };
