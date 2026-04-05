/**
 * SpanishG2P -- rule-based Spanish G2P for @piper-plus/g2p.
 *
 * Ported from src/rust/piper-plus-g2p/src/spanish.rs (1,397 lines).
 *
 * Features:
 * - Latin American pronunciation (seseo: c/z -> s)
 * - Grapheme segmentation with digraphs: ch, ll, rr, qu, gu, sc, xc
 * - Syllabification via onset maximization with inseparable clusters
 * - Stress assignment: accent mark > penultimate/final defaults
 * - Allophonic rules: b/d/g spirantization between vowels
 * - Function word destressing (28 words)
 * - PUA mapping for multi-character IPA tokens (rr, tsh)
 * - NFD combining accent normalization
 *
 * Pure JavaScript -- no external dependencies.
 */

import { collapseNfdAccents } from '../latin-common/index.js';

// ---------------------------------------------------------------------------
// IPA codepoints used in output
// ---------------------------------------------------------------------------

/** Voiced bilabial fricative (allophone of /b/) */
const IPA_BETA = '\u03B2';
/** Voiced dental fricative (allophone of /d/) */
const IPA_ETH = '\u00F0';
/** Voiced velar stop (IPA g U+0261, NOT ASCII g) */
const IPA_G = '\u0261';
/** Voiced velar fricative (allophone of /g/) */
const IPA_GAMMA = '\u0263';
/** Palatal nasal (n-tilde) */
const IPA_PALATAL_NASAL = '\u0272';
/** Alveolar tap (single r) */
const IPA_TAP = '\u027E';
/** Voiced palatal fricative (y, ll -- yeismo) */
const IPA_PALATAL_FRIC = '\u029D';
/** Primary stress marker */
const IPA_STRESS = '\u02C8';

// PUA codepoints
const PUA_RR = '\uE01D';   // Alveolar trill (rr, word-initial r)
const PUA_TCH = '\uE054';  // Voiceless postalveolar affricate (ch)

// ---------------------------------------------------------------------------
// Punctuation
// ---------------------------------------------------------------------------

const PUNCTUATION = new Set([
    ',', '.', ';', ':', '!', '?', '\u00A1', '\u00BF',
]);

function isPunctuation(c) {
    return PUNCTUATION.has(c);
}

// ---------------------------------------------------------------------------
// Vowels & accents
// ---------------------------------------------------------------------------

function isVowel(c) {
    return c === 'a' || c === 'e' || c === 'i' || c === 'o' || c === 'u';
}

function isStrongVowel(c) {
    return c === 'a' || c === 'e' || c === 'o';
}

function isWeakVowel(c) {
    return c === 'i' || c === 'u';
}

/** Map accented vowel to base vowel. */
function accentBase(c) {
    switch (c) {
        case '\u00E1': return 'a'; // a-acute
        case '\u00E9': return 'e'; // e-acute
        case '\u00ED': return 'i'; // i-acute
        case '\u00F3': return 'o'; // o-acute
        case '\u00FA': return 'u'; // u-acute
        case '\u00FC': return 'u'; // u-diaeresis
        default: return c;
    }
}

function hasStressAccent(c) {
    return c === '\u00E1' || c === '\u00E9' || c === '\u00ED'
        || c === '\u00F3' || c === '\u00FA';
}

function isVowelOrAccented(c) {
    return isVowel(c) || hasStressAccent(c) || c === '\u00FC';
}

// ---------------------------------------------------------------------------
// Spanish alpha check (lowercase)
// ---------------------------------------------------------------------------

function isSpanishAlpha(c) {
    const code = c.codePointAt(0);
    if (code >= 0x61 && code <= 0x7A) return true; // a-z
    return c === '\u00F1'    // n-tilde
        || c === '\u00E1' || c === '\u00E9' || c === '\u00ED'
        || c === '\u00F3' || c === '\u00FA' || c === '\u00FC';
}

// ---------------------------------------------------------------------------
// Lowercase for Spanish
// ---------------------------------------------------------------------------

function toLowerSp(c) {
    const code = c.codePointAt(0);
    if (code >= 0x41 && code <= 0x5A) {
        return String.fromCodePoint(code + 32);
    }
    switch (c) {
        case '\u00C1': return '\u00E1'; // A-acute -> a-acute
        case '\u00C9': return '\u00E9'; // E-acute -> e-acute
        case '\u00CD': return '\u00ED'; // I-acute -> i-acute
        case '\u00D3': return '\u00F3'; // O-acute -> o-acute
        case '\u00DA': return '\u00FA'; // U-acute -> u-acute
        case '\u00DC': return '\u00FC'; // U-diaeresis -> u-diaeresis
        case '\u00D1': return '\u00F1'; // N-tilde -> n-tilde
        default: return c;
    }
}

// collapseCombiningAccents -> collapseNfdAccents imported from latin-common

// ---------------------------------------------------------------------------
// Normalize: NFC collapse + lowercase + whitespace collapse
// ---------------------------------------------------------------------------

function normalize(text) {
    // Convert string to array of characters (handles surrogates)
    const cps = [...text];
    const nfc = collapseNfdAccents(cps);
    return nfc.map(c => toLowerSp(c));
}

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

/**
 * Tokenize normalized codepoints into Word and Punct tokens.
 * Whitespace, digits, and unknown characters are skipped.
 */
function tokenize(cps) {
    const tokens = [];
    const n = cps.length;
    let i = 0;

    while (i < n) {
        if (isSpanishAlpha(cps[i])) {
            const chars = [];
            while (i < n && isSpanishAlpha(cps[i])) {
                chars.push(cps[i]);
                i += 1;
            }
            tokens.push({ type: 'word', chars });
        } else if (isPunctuation(cps[i])) {
            const chars = [];
            while (i < n && isPunctuation(cps[i])) {
                chars.push(cps[i]);
                i += 1;
            }
            tokens.push({ type: 'punct', chars });
        } else {
            i += 1; // skip whitespace, digits, unknown
        }
    }

    return tokens;
}

// ---------------------------------------------------------------------------
// Function words (unstressed)
// ---------------------------------------------------------------------------

const UNSTRESSED_FUNCTION_WORDS = new Set([
    'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'a',
    'en', 'con', 'por', 'y', 'o', 'que', 'se', 'me', 'te', 'le',
    'lo', 'nos', 'su', 'mi', 'tu', 'es', 'no', 'si',
]);

// ---------------------------------------------------------------------------
// Grapheme segmentation
// ---------------------------------------------------------------------------

/**
 * Segment a word into grapheme units (GUnit).
 * Recognizes digraphs: ch, ll, rr, qu, gu, gu-diaeresis, sc, xc.
 */
function segmentGraphemes(word) {
    const bw = word.map(c => accentBase(c));
    const units = [];
    const n = word.length;
    let i = 0;

    while (i < n) {
        const bc = bw[i];

        // "qu" (u is silent)
        if (bc === 'q' && i + 1 < n && bw[i + 1] === 'u') {
            units.push({ chars: [word[i], word[i + 1]], isVowel: false, isSilent: false });
            i += 2;
            continue;
        }

        // "gu-diaeresis" before e/i
        if (bc === 'g' && i + 1 < n && word[i + 1] === '\u00FC'
            && i + 2 < n && (bw[i + 2] === 'e' || bw[i + 2] === 'i')) {
            units.push({ chars: [word[i], word[i + 1]], isVowel: false, isSilent: false });
            i += 2;
            continue;
        }

        // "gu" before e/i (u silent)
        if (bc === 'g' && i + 1 < n && bw[i + 1] === 'u'
            && i + 2 < n && (bw[i + 2] === 'e' || bw[i + 2] === 'i')) {
            units.push({ chars: [word[i], word[i + 1]], isVowel: false, isSilent: false });
            i += 2;
            continue;
        }

        // "ch"
        if (bc === 'c' && i + 1 < n && bw[i + 1] === 'h') {
            units.push({ chars: [word[i], word[i + 1]], isVowel: false, isSilent: false });
            i += 2;
            continue;
        }

        // "ll"
        if (bc === 'l' && i + 1 < n && bw[i + 1] === 'l') {
            units.push({ chars: [word[i], word[i + 1]], isVowel: false, isSilent: false });
            i += 2;
            continue;
        }

        // "rr"
        if (bc === 'r' && i + 1 < n && bw[i + 1] === 'r') {
            units.push({ chars: [word[i], word[i + 1]], isVowel: false, isSilent: false });
            i += 2;
            continue;
        }

        // "sc" before e/i
        if (bc === 's' && i + 1 < n && bw[i + 1] === 'c'
            && i + 2 < n && (bw[i + 2] === 'e' || bw[i + 2] === 'i')) {
            units.push({ chars: [word[i], word[i + 1]], isVowel: false, isSilent: false });
            i += 2;
            continue;
        }

        // "xc" before e/i
        if (bc === 'x' && i + 1 < n && bw[i + 1] === 'c'
            && i + 2 < n && (bw[i + 2] === 'e' || bw[i + 2] === 'i')) {
            units.push({ chars: [word[i], word[i + 1]], isVowel: false, isSilent: false });
            i += 2;
            continue;
        }

        // Silent "h"
        if (bc === 'h') {
            units.push({ chars: [word[i]], isVowel: false, isSilent: true });
            i += 1;
            continue;
        }

        // Vowels (including accented)
        if (isVowel(bc)) {
            units.push({ chars: [word[i]], isVowel: true, isSilent: false });
            i += 1;
            continue;
        }

        // All other consonants
        units.push({ chars: [word[i]], isVowel: false, isSilent: false });
        i += 1;
    }

    return units;
}

// ---------------------------------------------------------------------------
// Syllabification
// ---------------------------------------------------------------------------

/**
 * 13 inseparable onset clusters (pr, pl, br, bl, tr, tl, dr, cl, cr, gr, gl, fr, fl).
 */
function isInseparable(c1, c2) {
    if (c2 === 'l') return c1 === 'b' || c1 === 'c' || c1 === 'f' || c1 === 'g' || c1 === 'p' || c1 === 't';
    if (c2 === 'r') return c1 === 'b' || c1 === 'c' || c1 === 'd' || c1 === 'f' || c1 === 'g' || c1 === 'p' || c1 === 't';
    return false;
}

/** Return the base consonant letter from a grapheme unit. */
function baseConsOfUnit(unit) {
    return accentBase(unit.chars[unit.chars.length - 1]);
}

/**
 * Find syllable boundaries in units.
 * Returns array of unit indices where each syllable starts.
 */
function findSyllableBoundaries(units) {
    // Build non-silent mask
    const nsIdx = [];
    const nsVow = [];
    for (let idx = 0; idx < units.length; idx++) {
        if (units[idx].isSilent) continue;
        nsIdx.push(idx);
        nsVow.push(units[idx].isVowel);
    }

    const nsN = nsIdx.length;
    if (nsN === 0) return [0];

    const nsBounds = [0];
    let i = 1;

    while (i < nsN) {
        if (nsVow[i]) {
            if (i > 0 && nsVow[i - 1]) {
                // Two adjacent vowels: hiatus vs diphthong
                const prevG = units[nsIdx[i - 1]].chars[units[nsIdx[i - 1]].chars.length - 1];
                const currG = units[nsIdx[i]].chars[units[nsIdx[i]].chars.length - 1];
                const prevB = accentBase(prevG);
                const currB = accentBase(currG);
                if (isStrongVowel(prevB) && isStrongVowel(currB)) {
                    nsBounds.push(i); // hiatus
                } else {
                    // Accented weak vowel forces hiatus
                    if ((isWeakVowel(currB) && hasStressAccent(currG))
                        || (isWeakVowel(prevB) && hasStressAccent(prevG))) {
                        nsBounds.push(i);
                    }
                }
            }
            i += 1;
        } else {
            // Consonant cluster before next vowel
            const consStart = i;
            while (i < nsN && !nsVow[i]) {
                i += 1;
            }
            const consCount = i - consStart;
            if (i < nsN) {
                // vowel follows
                if (consCount === 1) {
                    nsBounds.push(consStart);
                } else if (consCount === 2) {
                    const c1 = baseConsOfUnit(units[nsIdx[consStart]]);
                    const c2 = baseConsOfUnit(units[nsIdx[consStart + 1]]);
                    if (isInseparable(c1, c2)) {
                        nsBounds.push(consStart);
                    } else {
                        nsBounds.push(consStart + 1);
                    }
                } else {
                    // 3+ consonants
                    const c1 = baseConsOfUnit(units[nsIdx[i - 2]]);
                    const c2 = baseConsOfUnit(units[nsIdx[i - 1]]);
                    if (isInseparable(c1, c2)) {
                        nsBounds.push(i - 2);
                    } else {
                        nsBounds.push(i - 1);
                    }
                }
            }
        }
    }

    // Map back to unit indices
    return nsBounds.map(b => nsIdx[b]);
}

// ---------------------------------------------------------------------------
// Stress assignment
// ---------------------------------------------------------------------------

/** Find the character-index of the first accented vowel in a word, or -1. */
function findAccentIndex(word) {
    for (let i = 0; i < word.length; i++) {
        if (hasStressAccent(word[i])) return i;
    }
    return -1;
}

function getStressedSyllable(word, units, boundaries) {
    const numSyl = boundaries.length;
    if (numSyl === 0) return 0;

    // Check for explicit accent
    const accIdx = findAccentIndex(word);
    if (accIdx >= 0) {
        // Map char index to unit index
        let charOff = 0;
        let accUnitIdx = 0;
        for (let uid = 0; uid < units.length; uid++) {
            const uLen = units[uid].chars.length;
            if (charOff <= accIdx && accIdx < charOff + uLen) {
                accUnitIdx = uid;
                break;
            }
            charOff += uLen;
        }
        // Find which syllable contains this unit
        for (let s = numSyl - 1; s >= 0; s--) {
            if (boundaries[s] <= accUnitIdx) {
                return s;
            }
        }
        return 0;
    }

    if (numSyl === 1) return 0;

    // Default stress rules
    const last = accentBase(word[word.length - 1]);
    if (isVowel(last) || last === 'n' || last === 's') {
        return Math.max(0, numSyl - 2); // penultimate
    } else {
        return numSyl - 1; // ultimate
    }
}

// ---------------------------------------------------------------------------
// G2P: grapheme-to-phoneme conversion
// ---------------------------------------------------------------------------

function g2pWord(word) {
    const ph = [];
    const n = word.length;

    // Build base-form word
    const bw = word.map(c => accentBase(c));

    const prevIsVowel = (idx) => idx > 0 && isVowelOrAccented(word[idx - 1]);
    const isAfterNasal = (idx) => idx > 0 && (bw[idx - 1] === 'm' || bw[idx - 1] === 'n');
    const isWordInitial = (idx) => idx === 0;

    let i = 0;
    while (i < n) {
        const bc = bw[i];

        // --- Vowels ---
        if (isVowel(bc)) {
            ph.push(bc);
            i += 1;
            continue;
        }

        // --- Multi-character sequences (longest first) ---

        // "qu" -> k
        if (bc === 'q' && i + 1 < n && bw[i + 1] === 'u') {
            ph.push('k');
            i += 2;
            continue;
        }

        // "ch" -> tsh (PUA)
        if (bc === 'c' && i + 1 < n && bw[i + 1] === 'h') {
            ph.push(PUA_TCH);
            i += 2;
            continue;
        }

        // "ll" -> palatal fricative (yeismo)
        if (bc === 'l' && i + 1 < n && bw[i + 1] === 'l') {
            ph.push(IPA_PALATAL_FRIC);
            i += 2;
            continue;
        }

        // "rr" -> trill (PUA)
        if (bc === 'r' && i + 1 < n && bw[i + 1] === 'r') {
            ph.push(PUA_RR);
            i += 2;
            continue;
        }

        // "gu-diaeresis" before e/i -> g w
        if (bc === 'g' && i + 1 < n && word[i + 1] === '\u00FC'
            && i + 2 < n && (bw[i + 2] === 'e' || bw[i + 2] === 'i')) {
            ph.push(IPA_G);
            ph.push('w');
            i += 2;
            continue;
        }

        // "gu" before e/i -> g (u silent); allophonic
        if (bc === 'g' && i + 1 < n && bw[i + 1] === 'u'
            && i + 2 < n && (bw[i + 2] === 'e' || bw[i + 2] === 'i')) {
            if (prevIsVowel(i) && !isAfterNasal(i)) {
                ph.push(IPA_GAMMA);
            } else {
                ph.push(IPA_G);
            }
            i += 2;
            continue;
        }

        // "sc" before e/i -> s (seseo, no geminate)
        if (bc === 's' && i + 1 < n && bw[i + 1] === 'c'
            && i + 2 < n && (bw[i + 2] === 'e' || bw[i + 2] === 'i')) {
            ph.push('s');
            i += 2;
            continue;
        }

        // --- Single character rules ---

        // b / v (betacismo)
        if (bc === 'b' || bc === 'v') {
            if (isWordInitial(i) || isAfterNasal(i) || (i > 0 && bw[i - 1] === 'l')) {
                ph.push('b');
            } else {
                ph.push(IPA_BETA);
            }
            i += 1;
            continue;
        }

        // c
        if (bc === 'c') {
            if (i + 1 < n && (bw[i + 1] === 'e' || bw[i + 1] === 'i')) {
                ph.push('s'); // seseo
            } else {
                ph.push('k');
            }
            i += 1;
            continue;
        }

        // d
        if (bc === 'd') {
            if (isWordInitial(i) || isAfterNasal(i) || (i > 0 && bw[i - 1] === 'l')) {
                ph.push('d');
            } else {
                ph.push(IPA_ETH);
            }
            i += 1;
            continue;
        }

        // f
        if (bc === 'f') {
            ph.push('f');
            i += 1;
            continue;
        }

        // g
        if (bc === 'g') {
            if (i + 1 < n && (bw[i + 1] === 'e' || bw[i + 1] === 'i')) {
                ph.push('x'); // velar fricative (jota)
            } else if (isWordInitial(i) || isAfterNasal(i) || (i > 0 && bw[i - 1] === 'l')) {
                ph.push(IPA_G);
            } else {
                ph.push(IPA_GAMMA);
            }
            i += 1;
            continue;
        }

        // h (silent)
        if (bc === 'h') {
            i += 1;
            continue;
        }

        // j
        if (bc === 'j') {
            ph.push('x');
            i += 1;
            continue;
        }

        // k
        if (bc === 'k') {
            ph.push('k');
            i += 1;
            continue;
        }

        // l
        if (bc === 'l') {
            ph.push('l');
            i += 1;
            continue;
        }

        // m
        if (bc === 'm') {
            ph.push('m');
            i += 1;
            continue;
        }

        // n
        if (bc === 'n') {
            ph.push('n');
            i += 1;
            continue;
        }

        // n-tilde
        if (bc === '\u00F1') {
            ph.push(IPA_PALATAL_NASAL);
            i += 1;
            continue;
        }

        // p
        if (bc === 'p') {
            ph.push('p');
            i += 1;
            continue;
        }

        // r (single)
        if (bc === 'r') {
            if (isWordInitial(i)) {
                ph.push(PUA_RR); // trill
            } else if (i > 0 && (bw[i - 1] === 'l' || bw[i - 1] === 'n' || bw[i - 1] === 's')) {
                ph.push(PUA_RR); // trill after l/n/s
            } else {
                ph.push(IPA_TAP);
            }
            i += 1;
            continue;
        }

        // s
        if (bc === 's') {
            ph.push('s');
            i += 1;
            continue;
        }

        // t
        if (bc === 't') {
            ph.push('t');
            i += 1;
            continue;
        }

        // w
        if (bc === 'w') {
            ph.push('w');
            i += 1;
            continue;
        }

        // x
        if (bc === 'x') {
            // xc+e/i: c is absorbed, x provides /ks/
            if (i + 1 < n && bw[i + 1] === 'c'
                && i + 2 < n && (bw[i + 2] === 'e' || bw[i + 2] === 'i')) {
                ph.push('k');
                ph.push('s');
                i += 2;
                continue;
            }
            ph.push('k');
            ph.push('s');
            i += 1;
            continue;
        }

        // y
        if (bc === 'y') {
            if (i === n - 1) {
                ph.push('i'); // word-final y -> vowel
            } else {
                ph.push(IPA_PALATAL_FRIC);
            }
            i += 1;
            continue;
        }

        // z (seseo)
        if (bc === 'z') {
            ph.push('s');
            i += 1;
            continue;
        }

        // Unknown -> skip
        i += 1;
    }

    // Syllabification & stress
    const units = segmentGraphemes(word);
    const boundaries = findSyllableBoundaries(units);
    const stressedSyl = getStressedSyllable(word, units, boundaries);

    return { phonemes: ph, stressedSyl, units, boundaries };
}

// ---------------------------------------------------------------------------
// Phoneme count per grapheme unit (for stress marker insertion)
// ---------------------------------------------------------------------------

function phonemeCountForUnit(unit) {
    const base = unit.chars.map(c => accentBase(c));

    // Silent h -> 0
    if (base.length === 1 && base[0] === 'h') return 0;

    // "gu-diaeresis" digraph -> 2 (g + w)
    if (base.length === 2 && base[0] === 'g' && unit.chars[1] === '\u00FC') return 2;

    // "xc" digraph before e/i -> k s (2 phonemes)
    if (base.length === 2 && base[0] === 'x' && base[1] === 'c') return 2;

    // x -> ks (2)
    if (base.length === 1 && base[0] === 'x') return 2;

    // Everything else -> 1
    return 1;
}

// ---------------------------------------------------------------------------
// Insert stress marker
// ---------------------------------------------------------------------------

function insertStressMarker(phonemes, units, boundaries, stressedSyl) {
    if (phonemes.length === 0 || boundaries.length === 0) return;
    if (stressedSyl >= boundaries.length) return;

    const numUnits = units.length;
    const sylStart = boundaries[stressedSyl];
    const sylEnd = stressedSyl + 1 < boundaries.length
        ? boundaries[stressedSyl + 1]
        : numUnits;

    // Find first vowel unit in stressed syllable
    let stressedUnitIdx = -1;
    for (let offset = 0; offset < Math.min(sylEnd, numUnits) - sylStart; offset++) {
        if (units[sylStart + offset].isVowel) {
            stressedUnitIdx = sylStart + offset;
            break;
        }
    }

    if (stressedUnitIdx < 0) return;

    // Walk units -> accumulate phoneme count to find insertion point
    let phI = 0;
    for (let uid = 0; uid < units.length; uid++) {
        if (uid === stressedUnitIdx) {
            phonemes.splice(phI, 0, IPA_STRESS);
            return;
        }
        phI += phonemeCountForUnit(units[uid]);
    }
}

// ---------------------------------------------------------------------------
// Core phonemization: text -> flat array of IPA phoneme characters
// ---------------------------------------------------------------------------

/**
 * Convert Spanish text to a flat array of IPA phoneme characters.
 *
 * @param {string} text - Input Spanish text.
 * @returns {string[]} Array of single-character IPA phoneme tokens.
 */
function textToPhonemeChars(text) {
    if (!text) return [];

    const cps = normalize(text);
    const tokens = tokenize(cps);
    if (tokens.length === 0) return [];

    const sentence = [];
    let needSpace = false;

    for (const tok of tokens) {
        if (tok.type === 'punct') {
            for (const c of tok.chars) {
                sentence.push(c);
            }
            // Do not set needSpace here -- punctuation does not trigger space
        } else if (tok.type === 'word') {
            if (needSpace) {
                sentence.push(' ');
            }

            const res = g2pWord(tok.chars);
            const wordStr = tok.chars.join('');
            const isFunctionWord = UNSTRESSED_FUNCTION_WORDS.has(wordStr);

            if (!isFunctionWord) {
                insertStressMarker(
                    res.phonemes,
                    res.units,
                    res.boundaries,
                    res.stressedSyl,
                );
            }

            for (const ph of res.phonemes) {
                sentence.push(ph);
            }

            needSpace = true;
        }
    }

    return sentence;
}

// ---------------------------------------------------------------------------
// SpanishG2P class
// ---------------------------------------------------------------------------

export class SpanishG2P {
    /**
     * Create a SpanishG2P instance.
     * @param {object} [options] - Options.
     * @param {Record<string, number[]>} [options.phonemeIdMap] - Phoneme ID map.
     */
    constructor(options = {}) {
        this.phonemeIdMap = options.phonemeIdMap || null;
    }

    /**
     * Language code for this G2P instance.
     * @type {string}
     */
    get languageCode() {
        return 'es';
    }

    /**
     * Set or replace the phoneme ID map.
     * @param {Record<string, number[]>} phonemeIdMap
     */
    setPhonemeIdMap(phonemeIdMap) {
        this.phonemeIdMap = phonemeIdMap;
    }

    /**
     * Convert Spanish text to phoneme tokens.
     *
     * Returns an object with `tokens` (array of single-character IPA strings)
     * and `prosody` (array of nulls, since Spanish G2P provides prosody via
     * phonemizeWithProsody).
     *
     * @param {string} text - Input Spanish text.
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
     * Convert Spanish text to phoneme tokens with prosody information.
     *
     * Spanish prosody: A1=0, A2=stress-based (0 or 2), A3=word phoneme count.
     *
     * @param {string} text - Input Spanish text.
     * @returns {{ tokens: string[], prosody: (null|{ a1: number, a2: number, a3: number })[] }}
     */
    phonemizeWithProsody(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }

        const cps = normalize(text);
        const toks = tokenize(cps);
        if (toks.length === 0) {
            return { tokens: [], prosody: [] };
        }

        const allTokens = [];
        const allProsody = [];
        let needSpace = false;

        for (const tok of toks) {
            if (tok.type === 'punct') {
                for (const c of tok.chars) {
                    allTokens.push(c);
                    allProsody.push({ a1: 0, a2: 0, a3: 0 });
                }
            } else if (tok.type === 'word') {
                if (needSpace) {
                    allTokens.push(' ');
                    allProsody.push({ a1: 0, a2: 0, a3: 0 });
                }

                const res = g2pWord(tok.chars);
                const wordStr = tok.chars.join('');
                const isFunctionWord = UNSTRESSED_FUNCTION_WORDS.has(wordStr);

                if (!isFunctionWord) {
                    insertStressMarker(
                        res.phonemes,
                        res.units,
                        res.boundaries,
                        res.stressedSyl,
                    );
                }

                const wordPhonemeCount = res.phonemes.filter(c => c !== IPA_STRESS).length;

                for (let idx = 0; idx < res.phonemes.length; idx++) {
                    const ph = res.phonemes[idx];
                    if (ph === IPA_STRESS) {
                        allTokens.push(ph);
                        allProsody.push({ a1: 0, a2: 2, a3: wordPhonemeCount });
                    } else {
                        const isStressedVowel =
                            idx > 0 && res.phonemes[idx - 1] === IPA_STRESS && isVowel(ph);
                        allTokens.push(ph);
                        allProsody.push({ a1: 0, a2: isStressedVowel ? 2 : 0, a3: wordPhonemeCount });
                    }
                }

                needSpace = true;
            }
        }

        return { tokens: allTokens, prosody: allProsody };
    }
}
