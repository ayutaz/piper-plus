/**
 * PortugueseG2P -- rule-based Brazilian Portuguese G2P for @piper-plus/g2p.
 *
 * Ported from src/rust/piper-plus-g2p/src/portuguese.rs (1,352 lines).
 *
 * Features:
 * - Nasal vowels (ã, ẽ, ĩ, õ, ũ)
 * - Coda-l vocalization (l -> w at syllable end)
 * - t/d palatalization before i: t -> PUA E054 (tʃ), d -> PUA E055 (dʒ)
 * - r polymorphism: word-initial/coda -> voiced uvular, intervocalic -> tap
 * - lh -> palatal lateral, nh -> palatal nasal
 * - Stress assignment (accent marks or positional defaults)
 * - BR post-processing (final vowel reduction, t/d palatalization before
 *   unstressed final e)
 * - 3-stage pipeline: removeDuplicateNasalCoda -> codaLVocalization -> brPostprocessing
 *
 * Pure JavaScript -- no external dependencies.
 */

import {
    collapseNfdAccents,
    isPunctuation,
    tokenize,
    normalizeWhitespace,
} from '../latin-common/index.js';

// ---------------------------------------------------------------------------
// PUA codepoints for multi-codepoint IPA tokens
// Must match pua-map.js / token_map.rs
// ---------------------------------------------------------------------------

const PUA_AFFRICATE_TCH = '\uE054'; // tʃ (palatalized t before i)
const PUA_AFFRICATE_DZH = '\uE055'; // dʒ (palatalized d before i)

// ---------------------------------------------------------------------------
// Single IPA codepoints
// ---------------------------------------------------------------------------

const IPA_EPSILON   = '\u025B'; // ɛ  open-mid front unrounded (e aberto)
const IPA_OPEN_O    = '\u0254'; // ɔ  open-mid back rounded   (o aberto)
const IPA_VOICED_G  = '\u0261'; // ɡ  voiced velar plosive
const IPA_ESH       = '\u0283'; // ʃ  voiceless postalveolar fricative
const IPA_EZH       = '\u0292'; // ʒ  voiced postalveolar fricative
const IPA_UVULAR_R  = '\u0281'; // ʁ  voiced uvular fricative
const IPA_PALATAL_N = '\u0272'; // ɲ  palatal nasal
const IPA_TAP       = '\u027E'; // ɾ  alveolar tap
const IPA_PALATAL_L = '\u028E'; // ʎ  palatal lateral approximant

// Precomposed nasal vowels (NFC single codepoints)
const NASAL_A = '\u00E3'; // ã
const NASAL_E = '\u1EBD'; // ẽ
const NASAL_I = '\u0129'; // ĩ
const NASAL_O = '\u00F5'; // õ
const NASAL_U = '\u0169'; // ũ

// ---------------------------------------------------------------------------
// Character classification helpers
// ---------------------------------------------------------------------------

const VOWEL_CHARS = new Set([
    'a', 'e', 'i', 'o', 'u',
    '\u00E1', // á  a acute
    '\u00E0', // à  a grave
    '\u00E2', // â  a circumflex
    '\u00E3', // ã  a tilde
    '\u00E9', // é  e acute
    '\u00EA', // ê  e circumflex
    '\u00ED', // í  i acute
    '\u00F3', // ó  o acute
    '\u00F4', // ô  o circumflex
    '\u00F5', // õ  o tilde
    '\u00FA', // ú  u acute
    '\u00FC', // ü  u diaeresis
]);

function isVowelChar(ch) {
    return VOWEL_CHARS.has(ch);
}

const STRESS_ACCENTS = new Set([
    '\u00E1', // á
    '\u00E9', // é
    '\u00ED', // í
    '\u00F3', // ó
    '\u00FA', // ú
]);

function isStressAccent(ch) {
    return STRESS_ACCENTS.has(ch);
}

const CIRCUMFLEX_CHARS = new Set([
    '\u00E2', // â
    '\u00EA', // ê
    '\u00F4', // ô
]);

function isCircumflex(ch) {
    return CIRCUMFLEX_CHARS.has(ch);
}

function isTilde(ch) {
    return ch === '\u00E3' || ch === '\u00F5';
}

function accentBase(ch) {
    switch (ch) {
    case '\u00E1': case '\u00E0': case '\u00E2': case '\u00E3': return 'a';
    case '\u00E9': case '\u00EA': return 'e';
    case '\u00ED': return 'i';
    case '\u00F3': case '\u00F4': case '\u00F5': return 'o';
    case '\u00FA': case '\u00FC': return 'u';
    default: return ch;
    }
}

const IPA_ORAL_VOWELS = new Set(['a', 'e', 'i', 'o', 'u', IPA_EPSILON, IPA_OPEN_O]);

function isIpaOralVowel(ch) {
    return IPA_ORAL_VOWELS.has(ch);
}

const IPA_NASAL_VOWELS = new Set([NASAL_A, NASAL_E, NASAL_I, NASAL_O, NASAL_U]);

function isIpaNasalVowel(ch) {
    return IPA_NASAL_VOWELS.has(ch);
}

function isIpaVowel(ch) {
    return isIpaOralVowel(ch) || isIpaNasalVowel(ch);
}

const IPA_CONSONANTS = new Set([
    'b', 'c', 'd', 'f', 'h', 'j', 'k', 'l', 'm', 'n', 'p',
    's', 't', 'v', 'w', 'z',
    IPA_VOICED_G, IPA_PALATAL_N, IPA_TAP, IPA_UVULAR_R,
    IPA_ESH, IPA_PALATAL_L, IPA_EZH,
]);

function isIpaConsonant(ch) {
    return IPA_CONSONANTS.has(ch);
}

// isPunctuation imported from latin-common

const SOFT_VOWELS = new Set([
    'e', 'i',
    '\u00E9', // é
    '\u00EA', // ê
    '\u00ED', // í
]);

function isSoftVowel(ch) {
    return SOFT_VOWELS.has(ch);
}

/**
 * Word character: a-z + common Portuguese accented range.
 */
function isWordChar(ch) {
    const cp = ch.codePointAt(0);
    // ASCII lowercase
    if (cp >= 0x61 && cp <= 0x7A) return true;
    // Latin-1 supplement lowercase (0xE0-0xFF except 0xF7 division sign)
    if (cp >= 0xE0 && cp <= 0xFF && cp !== 0xF7) return true;
    // c cedilla, n tilde (already in above range but explicit)
    if (ch === '\u00E7' || ch === '\u00F1') return true;
    // Extra nasal/accented
    if (ch === '\u1EBD' || ch === '\u0129' || ch === '\u0169') return true;
    return false;
}

// collapseNfdAccents imported from latin-common

/**
 * Simple lowercase for Latin + common accented letters.
 * @param {string} ch - Single character.
 * @returns {string} Lowercased character.
 */
function toLower(ch) {
    const cp = ch.codePointAt(0);
    // ASCII uppercase
    if (cp >= 0x41 && cp <= 0x5A) {
        return String.fromCodePoint(cp + 32);
    }
    // Latin-1 supplement uppercase (C0-DE except D7 multiply)
    if (cp >= 0xC0 && cp <= 0xDE && cp !== 0xD7) {
        return String.fromCodePoint(cp + 32);
    }
    return ch;
}

/**
 * Normalize text: NFC lowercase, collapse whitespace, trim.
 * @param {string} text - Input text.
 * @returns {string[]} Array of normalized characters.
 */
function normalize(text) {
    // Split into individual characters
    let cps = [...text];

    // NFD -> NFC: collapse combining accents
    cps = collapseNfdAccents(cps);

    // Lowercase
    cps = cps.map(toLower);

    // Collapse whitespace + trim
    return normalizeWhitespace(cps);
}

// tokenize imported from latin-common (uses isWordChar as predicate)

// ---------------------------------------------------------------------------
// Vowel-group counting (digraph-aware)
// ---------------------------------------------------------------------------

/**
 * Count vowel groups in a word (syllable estimate).
 * Handles qu/gu/ou digraphs.
 * @param {string[]} word - Array of characters.
 * @returns {number} Number of vowel groups.
 */
function countVowelGroups(word) {
    let count = 0;
    let i = 0;
    const n = word.length;

    while (i < n) {
        const ch = word[i];
        // qu digraph: u silent or glide -- skip both
        if (ch === 'q' && i + 1 < n && word[i + 1] === 'u') {
            i += 2;
            continue;
        }
        // gu before e/i: u silent
        if (ch === 'g' && i + 1 < n && word[i + 1] === 'u' && i + 2 < n && isSoftVowel(word[i + 2])) {
            i += 2;
            continue;
        }
        // ou diphthong: one vowel group
        if (ch === 'o' && i + 1 < n && word[i + 1] === 'u') {
            count += 1;
            i += 2;
            continue;
        }
        if (isVowelChar(ch)) {
            count += 1;
        }
        i += 1;
    }

    return count;
}

// ---------------------------------------------------------------------------
// Stress position finder
// ---------------------------------------------------------------------------

/**
 * Find the stressed syllable index (0-based from end).
 *
 * Portuguese stress rules:
 * - Words with acute/circumflex/tilde accent: stress on accented syllable
 * - Words ending in a, e, o, am, em, en: penultimate (paroxytone)
 * - Words ending in consonant (except s), i, u: ultimate (oxytone)
 *
 * @param {string[]} word - Array of word characters.
 * @returns {number} Stress position from end (0=final, 1=penultimate, etc.).
 */
function findStressPosition(word) {
    const vowelGroupCount = countVowelGroups(word);

    // Find accented vowel group position
    let accentGroup = -1;
    let currentGroup = 0;
    let i = 0;
    const n = word.length;

    while (i < n) {
        const ch = word[i];
        // Skip digraphs same as countVowelGroups
        if (ch === 'q' && i + 1 < n && word[i + 1] === 'u') {
            i += 2;
            continue;
        }
        if (ch === 'g' && i + 1 < n && word[i + 1] === 'u' && i + 2 < n && isSoftVowel(word[i + 2])) {
            i += 2;
            continue;
        }
        if (ch === 'o' && i + 1 < n && word[i + 1] === 'u') {
            if (isStressAccent(ch) || isCircumflex(ch) || isTilde(ch)) {
                accentGroup = currentGroup;
            }
            currentGroup += 1;
            i += 2;
            continue;
        }
        if (isVowelChar(ch)) {
            if (isStressAccent(ch) || isCircumflex(ch) || isTilde(ch)) {
                accentGroup = currentGroup;
            }
            currentGroup += 1;
        }
        i += 1;
    }

    if (vowelGroupCount === 0) {
        return 0;
    }

    if (accentGroup >= 0) {
        return vowelGroupCount - 1 - accentGroup;
    }

    // Default rules based on ending
    // Strip trailing 's' for rule check
    const stripped = word.slice();
    while (stripped.length > 0 && stripped[stripped.length - 1] === 's') {
        stripped.pop();
    }
    const sn = stripped.length;

    // Check endings: a, e, o, am, em, en -> paroxytone
    let paroxytone = false;
    if (sn >= 1) {
        const last = stripped[sn - 1];
        if (last === 'a' || last === 'e' || last === 'o') {
            paroxytone = true;
        }
    }
    if (!paroxytone && sn >= 2) {
        const sl = stripped[sn - 2];
        const el = stripped[sn - 1];
        if ((sl === 'a' && el === 'm') ||
            (sl === 'e' && el === 'm') ||
            (sl === 'e' && el === 'n')) {
            paroxytone = true;
        }
    }

    if (paroxytone) {
        return Math.min(1, vowelGroupCount - 1);
    }
    // Oxytone: last syllable
    return 0;
}

// ---------------------------------------------------------------------------
// Intervocalic helper
// ---------------------------------------------------------------------------

function isIntervocalic(i, word) {
    if (i === 0 || i >= word.length - 1) return false;
    return isVowelChar(word[i - 1]) && isVowelChar(word[i + 1]);
}

// ---------------------------------------------------------------------------
// Vowel helpers
// ---------------------------------------------------------------------------

function nasalOf(base) {
    switch (base) {
    case 'a': return NASAL_A;
    case 'e': return NASAL_E;
    case 'i': return NASAL_I;
    case 'o': return NASAL_O;
    case 'u': return NASAL_U;
    default: return base;
    }
}

function openVowelOf(base) {
    switch (base) {
    case 'a': return 'a';
    case 'e': return IPA_EPSILON;
    case 'i': return 'i';
    case 'o': return IPA_OPEN_O;
    case 'u': return 'u';
    default: return base;
    }
}

// ---------------------------------------------------------------------------
// Convert a single word to IPA phonemes
// ---------------------------------------------------------------------------

/**
 * Core word conversion: linear scanner over grapheme array.
 * @param {string[]} word - Array of word characters.
 * @returns {{ phonemes: string[], stressIdx: number }}
 */
function convertWord(word) {
    const ph = [];
    let stressIdx = -1;
    let i = 0;
    const n = word.length;

    // Determine stress target
    const stressFromEnd = findStressPosition(word);
    const vowelGroupCount = countVowelGroups(word);
    const stressVowelTarget = vowelGroupCount - 1 - stressFromEnd;
    let currentVowelGroup = 0;

    while (i < n) {
        const ch = word[i];

        // === Multi-character sequences (longest first) ===

        // "nh" -> palatal nasal
        if (ch === 'n' && i + 1 < n && word[i + 1] === 'h') {
            ph.push(IPA_PALATAL_N);
            i += 2;
            continue;
        }
        // "lh" -> palatal lateral
        if (ch === 'l' && i + 1 < n && word[i + 1] === 'h') {
            ph.push(IPA_PALATAL_L);
            i += 2;
            continue;
        }
        // "ch" -> voiceless postalveolar fricative
        if (ch === 'c' && i + 1 < n && word[i + 1] === 'h') {
            ph.push(IPA_ESH);
            i += 2;
            continue;
        }
        // "rr" -> uvular fricative
        if (ch === 'r' && i + 1 < n && word[i + 1] === 'r') {
            ph.push(IPA_UVULAR_R);
            i += 2;
            continue;
        }
        // "ss" -> voiceless alveolar sibilant
        if (ch === 's' && i + 1 < n && word[i + 1] === 's') {
            ph.push('s');
            i += 2;
            continue;
        }
        // "sc" before e/i -> s
        if (ch === 's' && i + 1 < n && word[i + 1] === 'c' && i + 2 < n && isSoftVowel(word[i + 2])) {
            ph.push('s');
            i += 2; // skip "sc", vowel handled next iteration
            continue;
        }
        // "qu" digraph
        if (ch === 'q' && i + 1 < n && word[i + 1] === 'u') {
            ph.push('k');
            if (i + 2 < n && isSoftVowel(word[i + 2])) {
                // Silent u before e/i
                i += 2;
            } else {
                // Pronounced u before a/o -> append w glide
                ph.push('w');
                i += 2;
            }
            continue;
        }
        // "gu" before e/i -> voiced velar plosive (u silent)
        if (ch === 'g' && i + 1 < n && word[i + 1] === 'u' && i + 2 < n && isSoftVowel(word[i + 2])) {
            ph.push(IPA_VOICED_G);
            i += 2;
            continue;
        }
        // "ou" -> o (common BR reduction, single vowel group)
        if (ch === 'o' && i + 1 < n && word[i + 1] === 'u') {
            const isStressed = currentVowelGroup === stressVowelTarget;
            if (isStressed) {
                stressIdx = ph.length;
            }
            ph.push('o');
            currentVowelGroup += 1;
            i += 2;
            continue;
        }

        // === Consonants ===

        if (ch === 'r') {
            if (isIntervocalic(i, word)) {
                ph.push(IPA_TAP);
            } else {
                ph.push(IPA_UVULAR_R);
            }
            i += 1;
            continue;
        }
        if (ch === 's') {
            // Intervocalic s -> z
            if (i > 0 && i + 1 < n && isVowelChar(word[i - 1]) && isVowelChar(word[i + 1])) {
                ph.push('z');
            } else {
                ph.push('s');
            }
            i += 1;
            continue;
        }
        if (ch === 'x') {
            if (i === 0) {
                ph.push(IPA_ESH);
            } else if (i > 0 && isVowelChar(word[i - 1]) && i + 1 < n && isVowelChar(word[i + 1])) {
                ph.push('z');
            } else {
                ph.push(IPA_ESH);
            }
            i += 1;
            continue;
        }
        if (ch === 'c') {
            if (i + 1 < n && isSoftVowel(word[i + 1])) {
                ph.push('s');
            } else {
                ph.push('k');
            }
            i += 1;
            continue;
        }
        if (ch === '\u00E7') {
            // c cedilla
            ph.push('s');
            i += 1;
            continue;
        }
        if (ch === 'g') {
            if (i + 1 < n && isSoftVowel(word[i + 1])) {
                ph.push(IPA_EZH);
            } else {
                ph.push(IPA_VOICED_G);
            }
            i += 1;
            continue;
        }
        if (ch === 'j') {
            ph.push(IPA_EZH);
            i += 1;
            continue;
        }
        if (ch === 't') {
            // BR Portuguese: t before i -> affricate
            if (i + 1 < n && (word[i + 1] === 'i' || word[i + 1] === '\u00ED')) {
                ph.push(PUA_AFFRICATE_TCH);
            } else {
                ph.push('t');
            }
            i += 1;
            continue;
        }
        if (ch === 'd') {
            // BR Portuguese: d before i -> affricate
            if (i + 1 < n && (word[i + 1] === 'i' || word[i + 1] === '\u00ED')) {
                ph.push(PUA_AFFRICATE_DZH);
            } else {
                ph.push('d');
            }
            i += 1;
            continue;
        }
        if (ch === 'h') {
            // Silent (digraphs already handled above)
            i += 1;
            continue;
        }
        // Simple consonant pass-through: b f k l m n p v
        if (ch === 'b' || ch === 'f' || ch === 'k' || ch === 'l' ||
            ch === 'm' || ch === 'n' || ch === 'p' || ch === 'v') {
            ph.push(ch);
            i += 1;
            continue;
        }
        if (ch === 'z') {
            ph.push('z');
            i += 1;
            continue;
        }
        if (ch === 'w') {
            ph.push('w');
            i += 1;
            continue;
        }

        // === Vowels ===

        if (isVowelChar(ch)) {
            const isStressed = currentVowelGroup === stressVowelTarget;
            const base = accentBase(ch);

            // --- Nasalization check ---
            let isNasal = false;
            let nasalAbsorbed = false;

            if (isTilde(ch)) {
                isNasal = true;
            } else if (i + 1 < n && (word[i + 1] === 'n' || word[i + 1] === 'm')) {
                // Exception: "nh" digraph -- do NOT nasalize before nh
                if (word[i + 1] === 'n' && i + 2 < n && word[i + 2] === 'h') {
                    // isNasal stays false
                } else if (i + 2 >= n) {
                    // n/m at end of word: absorb nasal consonant
                    isNasal = true;
                    nasalAbsorbed = true;
                } else if (!isVowelChar(word[i + 2])) {
                    // n/m followed by consonant: absorb nasal coda
                    isNasal = true;
                    nasalAbsorbed = true;
                }
            }

            let phoneme;
            if (isNasal) {
                phoneme = nasalOf(base);
            } else if (isStressAccent(ch)) {
                // Acute accent = open vowel
                phoneme = openVowelOf(base);
            } else if (isCircumflex(ch)) {
                // Circumflex = closed vowel (base)
                phoneme = base;
            } else {
                phoneme = base;
            }

            if (isStressed) {
                stressIdx = ph.length;
            }
            ph.push(phoneme);
            currentVowelGroup += 1;

            if (nasalAbsorbed) {
                i += 2; // skip vowel + nasal consonant
            } else {
                i += 1;
            }
            continue;
        }

        // Punctuation pass-through
        if (isPunctuation(ch)) {
            ph.push(ch);
            i += 1;
            continue;
        }

        // Unknown character: skip
        i += 1;
    }

    return { phonemes: ph, stressIdx };
}

// ---------------------------------------------------------------------------
// Post-processing step 1: remove duplicate nasal coda
// ---------------------------------------------------------------------------

/**
 * After nasal vowel, remove following n/m at word boundary.
 * Scans BACKWARDS. Adjusts stressIdx when removing before stress position.
 * @param {string[]} ph - Phoneme array (mutated in place).
 * @param {number} stressIdx - Current stress index.
 * @returns {{ phonemes: string[], stressIdx: number }}
 */
function removeDuplicateNasalCoda(ph, stressIdx) {
    let i = ph.length - 1;
    while (i >= 1) {
        if ((ph[i] === 'n' || ph[i] === 'm') && isIpaNasalVowel(ph[i - 1])) {
            // Check boundary: at end, or next is space / punctuation
            const atBoundary =
                i === ph.length - 1 || ph[i + 1] === ' ' || isPunctuation(ph[i + 1]);
            if (atBoundary) {
                if (stressIdx >= 0 && i < stressIdx) {
                    stressIdx -= 1;
                }
                ph.splice(i, 1);
            }
        }
        i -= 1;
    }
    return { phonemes: ph, stressIdx };
}

// ---------------------------------------------------------------------------
// Post-processing step 2: coda-l vocalization (l -> w in coda)
// ---------------------------------------------------------------------------

/**
 * Syllable-final l -> w (before consonant, word-end, or punctuation).
 * PUA affricates (E054, E055) count as consonants.
 * @param {string[]} ph - Phoneme array (mutated in place).
 */
function applyCodaLVocalization(ph) {
    for (let i = 0; i < ph.length; i++) {
        if (ph[i] !== 'l') continue;

        // l at end of list -> coda
        if (i === ph.length - 1) {
            ph[i] = 'w';
            continue;
        }
        const next = ph[i + 1];
        // l before space or punctuation -> coda (word-final)
        if (next === ' ' || isPunctuation(next)) {
            ph[i] = 'w';
            continue;
        }
        // l before a consonant -> coda (also handle PUA affricates)
        if ((isIpaConsonant(next) || next === PUA_AFFRICATE_TCH || next === PUA_AFFRICATE_DZH)
            && !isIpaVowel(next)) {
            ph[i] = 'w';
        }
    }
}

// ---------------------------------------------------------------------------
// Post-processing step 3: BR postprocessing
// ---------------------------------------------------------------------------

/**
 * Find (start, end) ranges for each word delimited by space phonemes.
 * @param {string[]} ph - Phoneme array.
 * @returns {[number, number][]} Array of [start, end) ranges.
 */
function findWordRanges(ph) {
    const ranges = [];
    let start = 0;
    for (let i = 0; i < ph.length; i++) {
        if (ph[i] === ' ') {
            if (i > start) {
                ranges.push([start, i]);
            }
            start = i + 1;
        }
    }
    if (start < ph.length) {
        ranges.push([start, ph.length]);
    }
    return ranges;
}

/**
 * BR post-processing: t/d palatalization before final unstressed e,
 * unstressed final e -> i, unstressed final o -> u.
 * @param {string[]} ph - Phoneme array (mutated in place).
 * @param {number} stressIdx - Stress index.
 */
function applyBrPostprocessing(ph, stressIdx) {
    const ranges = findWordRanges(ph);

    for (const [start, end] of ranges) {
        if (end - start < 2) continue;

        let lastIdx = end - 1;
        // Skip trailing punctuation
        while (lastIdx >= start && isPunctuation(ph[lastIdx])) {
            lastIdx -= 1;
        }
        if (lastIdx < start) continue;

        // Unstressed final 'e'
        if (ph[lastIdx] === 'e' && lastIdx !== stressIdx) {
            // Preceded by 't' -> t + e -> affricate + i
            if (lastIdx > start && ph[lastIdx - 1] === 't') {
                ph[lastIdx - 1] = PUA_AFFRICATE_TCH;
                ph[lastIdx] = 'i';
                continue;
            }
            // Preceded by 'd' -> d + e -> affricate + i
            if (lastIdx > start && ph[lastIdx - 1] === 'd') {
                ph[lastIdx - 1] = PUA_AFFRICATE_DZH;
                ph[lastIdx] = 'i';
                continue;
            }
            // General reduction: unstressed final e -> i
            ph[lastIdx] = 'i';
        }
        // Unstressed final 'o' -> u
        else if (ph[lastIdx] === 'o' && lastIdx !== stressIdx) {
            ph[lastIdx] = 'u';
        }
    }
}

// ---------------------------------------------------------------------------
// Full word conversion pipeline
// ---------------------------------------------------------------------------

/**
 * Convert a single word through the full 3-stage pipeline:
 * convertWord -> removeDuplicateNasalCoda -> codaLVocalization -> brPostprocessing
 * @param {string[]} word - Array of word characters.
 * @returns {{ phonemes: string[], stressIdx: number }}
 */
function processWord(word) {
    let wr = convertWord(word);
    wr = removeDuplicateNasalCoda(wr.phonemes, wr.stressIdx);
    applyCodaLVocalization(wr.phonemes);
    applyBrPostprocessing(wr.phonemes, wr.stressIdx);
    return wr;
}

// ---------------------------------------------------------------------------
// Top-level phonemization: text -> flat array of IPA phoneme characters
// ---------------------------------------------------------------------------

/**
 * Phonemize a Portuguese sentence.
 * @param {string} text - Input text.
 * @returns {string[]} Array of single-character IPA phoneme tokens.
 */
function textToPhonemeChars(text) {
    if (!text) return [];

    const cps = normalize(text);
    const tokens = tokenize(cps, isWordChar);

    const phonemes = [];
    let needSpace = false;

    for (const tok of tokens) {
        if (tok.isPunct) {
            for (const ch of tok.chars) {
                phonemes.push(ch);
            }
            needSpace = true;
        } else {
            if (needSpace) {
                phonemes.push(' ');
            }
            const wr = processWord(tok.chars);
            for (const ph of wr.phonemes) {
                phonemes.push(ph);
            }
            needSpace = true;
        }
    }

    return phonemes;
}

// ---------------------------------------------------------------------------
// PortugueseG2P class
// ---------------------------------------------------------------------------

export class PortugueseG2P {
    /**
     * Create a PortugueseG2P instance.
     * @param {object} [options]
     * @param {Record<string, number[]>} [options.phonemeIdMap]
     */
    constructor(options = {}) {
        this.phonemeIdMap = options.phonemeIdMap || null;
    }

    /**
     * Language code for this G2P instance.
     * @type {string}
     */
    get languageCode() {
        return 'pt';
    }

    /**
     * Set or replace the phoneme ID map.
     * @param {Record<string, number[]>} phonemeIdMap
     */
    setPhonemeIdMap(phonemeIdMap) {
        this.phonemeIdMap = phonemeIdMap;
    }

    /**
     * Convert Portuguese text to phoneme tokens.
     *
     * Returns an object with `tokens` (array of single-character IPA strings)
     * and `prosody` (array of nulls, since Portuguese G2P does not provide
     * prosody information via this method).
     *
     * @param {string} text - Input Portuguese text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemize(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }

        const tokens = textToPhonemeChars(text);
        const prosody = new Array(tokens.length).fill(null);
        return { tokens, prosody };
    }

    /**
     * Convert Portuguese text to phoneme tokens with prosody.
     *
     * @param {string} text - Input Portuguese text.
     * @returns {{ tokens: string[], prosody: Array<{a1: number, a2: number, a3: number}> }}
     */
    phonemizeWithProsody(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }

        const cps = normalize(text);
        const toks = tokenize(cps, isWordChar);

        const tokens = [];
        const prosody = [];
        let needSpace = false;

        for (const tok of toks) {
            if (tok.isPunct) {
                for (const ch of tok.chars) {
                    tokens.push(ch);
                    prosody.push({ a1: 0, a2: 0, a3: 0 });
                }
                needSpace = true;
            } else {
                if (needSpace) {
                    tokens.push(' ');
                    prosody.push({ a1: 0, a2: 0, a3: 0 });
                }
                const wr = processWord(tok.chars);
                const wordPhonemeCount = wr.phonemes.length;

                for (let j = 0; j < wr.phonemes.length; j++) {
                    const a2 = (j === wr.stressIdx) ? 2 : 0;
                    tokens.push(wr.phonemes[j]);
                    prosody.push({ a1: 0, a2, a3: wordPhonemeCount });
                }
                needSpace = true;
            }
        }

        return { tokens, prosody };
    }
}
