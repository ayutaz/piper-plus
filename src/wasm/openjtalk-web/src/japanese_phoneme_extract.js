/**
 * Japanese phoneme extraction from OpenJTalk full-context labels.
 *
 * This module replicates the Python phonemize_japanese() logic:
 * - Kurihara-method prosody markers: [, ], #
 * - pau → _ conversion
 * - Context-dependent N variants (N_m, N_n, N_ng, N_uvular)
 * - PUA mapping matching token_mapper.py FIXED_PUA_MAPPING
 */

// PUA mapping - must match token_mapper.py FIXED_PUA_MAPPING exactly
const PUA_MAP = {
    'a:': '\ue000', 'i:': '\ue001', 'u:': '\ue002', 'e:': '\ue003', 'o:': '\ue004',
    'cl': '\ue005',
    'ky': '\ue006', 'kw': '\ue007', 'gy': '\ue008', 'gw': '\ue009',
    'ty': '\ue00a', 'dy': '\ue00b', 'py': '\ue00c', 'by': '\ue00d',
    'ch': '\ue00e', 'ts': '\ue00f', 'sh': '\ue010', 'zy': '\ue011', 'hy': '\ue012',
    'ny': '\ue013', 'my': '\ue014', 'ry': '\ue015',
    'N_m': '\ue019', 'N_n': '\ue01a', 'N_ng': '\ue01b', 'N_uvular': '\ue01c'
};

// Regex patterns matching the Python implementation
const RE_PHONEME = /-([^+]+)\+/;
const RE_A1 = /\/A:([\d-]+)\+/;
const RE_A2 = /\+([0-9]+)\+/;
const RE_A3 = /\+([0-9]+)\//;

// Tokens to skip when looking ahead for N-variant rules
const SKIP_TOKENS = new Set(['_', '#', '[', ']', '^', '$', '?', '?!', '?.', '?~']);

// Long vowel detection: if same vowel appears consecutively, second becomes long vowel
const VOWELS = new Set(['a', 'i', 'u', 'e', 'o']);

/**
 * Apply context-dependent N phoneme rules.
 * Matches _apply_n_phoneme_rules() in japanese.py
 */
function applyNPhonemeRules(tokens) {
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
 */
function mapToPUA(tokens) {
    return tokens.map(t => PUA_MAP[t] || t);
}

/**
 * Extract phonemes from OpenJTalk full-context labels.
 * Replicates phonemize_japanese() from japanese.py.
 *
 * @param {string} labels - Full-context labels (newline-separated)
 * @returns {string[]} Array of phoneme tokens (PUA-mapped)
 */
export function extractPhonemesFromLabels(labels) {
    const lines = labels.split('\n').filter(line => line.trim());
    const tokens = [];

    for (let idx = 0; idx < lines.length; idx++) {
        const line = lines[idx];
        const mPh = line.match(RE_PHONEME);
        if (!mPh) continue;
        const phoneme = mPh[1];

        // Beginning / end silence handling
        if (phoneme === 'sil') {
            if (idx === 0) {
                tokens.push('^');
            } else if (idx === lines.length - 1) {
                tokens.push('$');
            }
            continue;
        }

        // Short pause → _
        if (phoneme === 'pau') {
            tokens.push('_');
            continue;
        }

        // Add phoneme token
        tokens.push(phoneme);

        // Extract A1/A2/A3 for Kurihara prosody markers
        const mA1 = line.match(RE_A1);
        const mA2 = line.match(RE_A2);
        const mA3 = line.match(RE_A3);
        if (!(mA1 && mA2 && mA3)) continue;

        const a1 = parseInt(mA1[1], 10);
        const a2 = parseInt(mA2[1], 10);
        const a3 = parseInt(mA3[1], 10);

        // Look-ahead for a2_next
        let a2Next = -1;
        if (idx < lines.length - 1) {
            const mA2Next = lines[idx + 1].match(RE_A2);
            if (mA2Next) a2Next = parseInt(mA2Next[1], 10);
        }

        // Insert accent nucleus mark "]"
        if (a1 === 0 && a2Next === a2 + 1) {
            tokens.push(']');
        }

        // Insert accent phrase boundary "#"
        if (a2 === a3 && a2Next === 1) {
            tokens.push('#');
        }

        // Insert rising mark "["
        if (a2 === 1 && a2Next === 2) {
            tokens.push('[');
        }
    }

    // Apply N phoneme rules
    const withNVariants = applyNPhonemeRules(tokens);

    // Map to PUA codepoints
    return mapToPUA(withNVariants);
}

export { PUA_MAP, applyNPhonemeRules, mapToPUA };
