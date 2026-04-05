/**
 * latin-common -- shared utilities for Latin-script G2P modules (ES/FR/PT).
 *
 * Extracted from the ES, FR, and PT G2P implementations to eliminate
 * near-identical code across those three modules.
 *
 * Exports:
 * - collapseNfdAccents(chars): NFD combining accent -> NFC precomposed
 * - PUNCTUATION / isPunctuation: common Latin punctuation set
 * - tokenize(chars, isWordCharFn): generic word/punct tokenizer
 * - normalizeWhitespace(chars): collapse + trim whitespace
 *
 * Pure JavaScript -- no external dependencies.
 */

// ---------------------------------------------------------------------------
// Punctuation set (shared by FR, PT; ES uses a subset but can reuse)
// ---------------------------------------------------------------------------

/**
 * Common Latin-script punctuation characters.
 * @type {Set<string>}
 */
export const PUNCTUATION = new Set([
    ',', '.', ';', ':', '!', '?',
    '\u00A1',  // inverted exclamation
    '\u00BF',  // inverted question
    '\u2014',  // em dash
    '\u2013',  // en dash
    '\u2026',  // horizontal ellipsis
    '\u00AB',  // left guillemet
    '\u00BB',  // right guillemet
]);

/**
 * Check if a character is a common Latin punctuation mark.
 * @param {string} ch - Single character.
 * @returns {boolean}
 */
export function isPunctuation(ch) {
    return PUNCTUATION.has(ch);
}

// ---------------------------------------------------------------------------
// NFD combining accent -> NFC precomposed collapse
// ---------------------------------------------------------------------------

/**
 * NFD-to-NFC composition table.
 *
 * Maps (base char, combining mark) -> precomposed NFC codepoint.
 * Covers all combining marks used across ES, FR, and PT:
 *   U+0300 GRAVE, U+0301 ACUTE, U+0302 CIRCUMFLEX,
 *   U+0303 TILDE, U+0308 DIAERESIS, U+0327 CEDILLA.
 *
 * @type {Map<string, Map<string, string>>}
 */
const NFC_TABLE = new Map();

// Helper to populate table entries.
function addNfc(combining, base, composed) {
    if (!NFC_TABLE.has(combining)) {
        NFC_TABLE.set(combining, new Map());
    }
    NFC_TABLE.get(combining).set(base, composed);
}

// U+0300 COMBINING GRAVE ACCENT
addNfc('\u0300', 'A', '\u00C0');
addNfc('\u0300', 'a', '\u00E0');
addNfc('\u0300', 'E', '\u00C8');
addNfc('\u0300', 'e', '\u00E8');
addNfc('\u0300', 'U', '\u00D9');
addNfc('\u0300', 'u', '\u00F9');

// U+0301 COMBINING ACUTE ACCENT
addNfc('\u0301', 'A', '\u00C1');
addNfc('\u0301', 'a', '\u00E1');
addNfc('\u0301', 'E', '\u00C9');
addNfc('\u0301', 'e', '\u00E9');
addNfc('\u0301', 'I', '\u00CD');
addNfc('\u0301', 'i', '\u00ED');
addNfc('\u0301', 'O', '\u00D3');
addNfc('\u0301', 'o', '\u00F3');
addNfc('\u0301', 'U', '\u00DA');
addNfc('\u0301', 'u', '\u00FA');

// U+0302 COMBINING CIRCUMFLEX ACCENT
addNfc('\u0302', 'A', '\u00C2');
addNfc('\u0302', 'a', '\u00E2');
addNfc('\u0302', 'E', '\u00CA');
addNfc('\u0302', 'e', '\u00EA');
addNfc('\u0302', 'I', '\u00CE');
addNfc('\u0302', 'i', '\u00EE');
addNfc('\u0302', 'O', '\u00D4');
addNfc('\u0302', 'o', '\u00F4');
addNfc('\u0302', 'U', '\u00DB');
addNfc('\u0302', 'u', '\u00FB');

// U+0303 COMBINING TILDE
addNfc('\u0303', 'A', '\u00C3');
addNfc('\u0303', 'a', '\u00E3');
addNfc('\u0303', 'N', '\u00D1');
addNfc('\u0303', 'n', '\u00F1');
addNfc('\u0303', 'O', '\u00D5');
addNfc('\u0303', 'o', '\u00F5');

// U+0308 COMBINING DIAERESIS
addNfc('\u0308', 'E', '\u00CB');
addNfc('\u0308', 'e', '\u00EB');
addNfc('\u0308', 'I', '\u00CF');
addNfc('\u0308', 'i', '\u00EF');
addNfc('\u0308', 'U', '\u00DC');
addNfc('\u0308', 'u', '\u00FC');

// U+0327 COMBINING CEDILLA
addNfc('\u0327', 'C', '\u00C7');
addNfc('\u0327', 'c', '\u00E7');

/**
 * Collapse NFD combining accent sequences into precomposed NFC codepoints.
 *
 * Operates on an array of single characters (string[]).
 * Handles all combining marks relevant to ES, FR, and PT.
 *
 * @param {string[]} cps - Array of single characters (possibly with NFD combining marks).
 * @returns {string[]} Array with combining sequences replaced by NFC precomposed characters.
 */
export function collapseNfdAccents(cps) {
    if (cps.length < 2) return cps.slice();

    const out = [];
    let i = 0;
    const n = cps.length;

    while (i < n) {
        if (i + 1 < n) {
            const base = cps[i];
            const comb = cps[i + 1];
            const combMap = NFC_TABLE.get(comb);
            if (combMap) {
                const composed = combMap.get(base);
                if (composed !== undefined) {
                    out.push(composed);
                    i += 2;
                    continue;
                }
            }
        }

        out.push(cps[i]);
        i += 1;
    }

    return out;
}

// ---------------------------------------------------------------------------
// Whitespace normalization
// ---------------------------------------------------------------------------

/**
 * Collapse consecutive whitespace into single spaces and trim
 * leading/trailing whitespace.
 *
 * @param {string[]} chars - Array of characters (already lowercased / NFC-collapsed).
 * @returns {string[]} Whitespace-normalized character array.
 */
export function normalizeWhitespace(chars) {
    const out = [];
    let prevSpace = true; // trim leading

    for (const ch of chars) {
        if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') {
            if (!prevSpace) {
                out.push(' ');
            }
            prevSpace = true;
        } else {
            out.push(ch);
            prevSpace = false;
        }
    }

    // trim trailing
    if (out.length > 0 && out[out.length - 1] === ' ') {
        out.pop();
    }

    return out;
}

// ---------------------------------------------------------------------------
// Generic tokenizer
// ---------------------------------------------------------------------------

/**
 * Split an array of characters into word and punctuation tokens.
 *
 * Uses the provided `isWordCharFn` callback to determine what constitutes
 * a word character (language-specific). Punctuation is identified via
 * `isPunctuation`. Everything else (whitespace, digits, unknown chars)
 * is skipped.
 *
 * @param {string[]} chars - Normalized character array.
 * @param {(ch: string) => boolean} isWordCharFn - Predicate for word characters.
 * @returns {{ chars: string[], isPunct: boolean }[]} Array of tokens.
 */
export function tokenize(chars, isWordCharFn) {
    const tokens = [];
    const n = chars.length;
    let i = 0;

    while (i < n) {
        const ch = chars[i];

        if (isWordCharFn(ch)) {
            const wordChars = [];
            while (i < n && isWordCharFn(chars[i])) {
                wordChars.push(chars[i]);
                i += 1;
            }
            tokens.push({ chars: wordChars, isPunct: false });
        } else if (isPunctuation(ch)) {
            tokens.push({ chars: [ch], isPunct: true });
            i += 1;
        } else {
            // whitespace, digits, unknown: skip
            i += 1;
        }
    }

    return tokens;
}
