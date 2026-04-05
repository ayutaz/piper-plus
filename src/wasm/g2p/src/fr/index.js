/**
 * FrenchG2P -- rule-based French grapheme-to-phoneme conversion for @piper-plus/g2p.
 *
 * Ported from src/rust/piper-plus-g2p/src/french.rs (1,586 lines).
 *
 * Features:
 * - Nasal vowels: PUA E056 (nasal open-e), PUA E057 (nasal a), PUA E058 (nasal o)
 * - Silent final consonants
 * - Consonant digraphs: ch, gn, ph, th, qu, gu
 * - Vowel digraphs: ou, au, eau, ai, ei, eu, oi, etc.
 * - -tion -> /sj + nasal-on/, -ille -> /ij/ (with exceptions)
 * - Front rounded vowels: slashed-o, oe-ligature, y_vowel (PUA E01E)
 * - Semi-vowel: turned-h (labial-palatal approximant)
 * - Intervocalic s voicing, -er verb endings, context-dependent x
 * - Exception dictionaries for ille-as-il and er-as-ehr words
 * - Prosody: a1=0, a2=word-final vowel stress, a3=word phoneme count
 *
 * Pure JavaScript -- no external dependencies.
 */

import {
    collapseNfdAccents,
    isPunctuation,
    PUNCTUATION,
    tokenize,
    normalizeWhitespace,
} from '../latin-common/index.js';

// ---------------------------------------------------------------------------
// PUA codepoints for multi-character phoneme tokens
// Must match pua-map.js / token_map.rs / token_mapper.py
// ---------------------------------------------------------------------------

const PUA_Y_VOWEL   = '\uE01E'; // y_vowel [y] (lune, tu)
const PUA_NASAL_EIN = '\uE056'; // nasal open-mid front unrounded  (vin, pain)
const PUA_NASAL_AN  = '\uE057'; // nasal open back unrounded       (dans, vent)
const PUA_NASAL_ON  = '\uE058'; // nasal open-mid back rounded     (bon, mont)

// Single IPA codepoints
const IPA_OPEN_E    = '\u025B'; // open-mid front unrounded
const IPA_OPEN_O    = '\u0254'; // open-mid back rounded
const IPA_SCHWA     = '\u0259'; // schwa
const IPA_VOICED_G  = '\u0261'; // voiced velar plosive (IPA g)
const IPA_ESH       = '\u0283'; // voiceless postalveolar fricative
const IPA_EZH       = '\u0292'; // voiced postalveolar fricative
const IPA_UVULAR_R  = '\u0281'; // voiced uvular fricative
const IPA_PALATAL_N = '\u0272'; // palatal nasal
const IPA_TURNED_H  = '\u0265'; // labial-palatal approximant
const IPA_SLASHED_O = '\u00F8'; // close-mid front rounded
const IPA_OE_LIG    = '\u0153'; // open-mid front rounded

// Stress marker
const STRESS_MARK   = '\u02C8'; // primary stress

// ---------------------------------------------------------------------------
// Character classification
// ---------------------------------------------------------------------------

const VOWEL_CHARS = new Set([
    'a', 'e', 'i', 'o', 'u', 'y',
    '\u00E0', // a-grave
    '\u00E2', // a-circumflex
    '\u00E6', // ae ligature
    '\u00E9', // e-acute
    '\u00E8', // e-grave
    '\u00EA', // e-circumflex
    '\u00EB', // e-diaeresis
    '\u00EE', // i-circumflex
    '\u00EF', // i-diaeresis
    '\u00F4', // o-circumflex
    '\u00F9', // u-grave
    '\u00FB', // u-circumflex
    '\u00FC', // u-diaeresis
    '\u0153', // oe ligature
]);

const CONSONANT_CHARS = new Set([
    'b', 'c', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'm',
    'n', 'p', 'q', 'r', 's', 't', 'v', 'w', 'x', 'z',
]);

const SILENT_FINAL_CHARS = new Set([
    'd', 'g', 'h', 'm', 'n', 'p', 's', 't', 'x', 'z',
]);

const FRONT_VOWELS_CG = new Set([
    'e', 'i', 'y',
    '\u00E9', '\u00E8', '\u00EA', '\u00EB',
    '\u00EE', '\u00EF',
]);

// PUNCTUATION / isPunctuation imported from latin-common

/**
 * Check if a character is a French letter (lowercase ASCII + accented).
 */
function isLetterFr(ch) {
    const code = ch.codePointAt(0);
    if (code >= 0x61 && code <= 0x7A) return true; // a-z
    return (
        ch === '\u00E0' || ch === '\u00E2' || ch === '\u00E6' ||
        ch === '\u00E9' || ch === '\u00E8' || ch === '\u00EA' || ch === '\u00EB' ||
        ch === '\u00EE' || ch === '\u00EF' ||
        ch === '\u00F4' ||
        ch === '\u00F9' || ch === '\u00FB' || ch === '\u00FC' ||
        ch === '\u0153' || ch === '\u00E7' || ch === '\u00F1'
    );
}

function isVowelChar(ch) {
    return VOWEL_CHARS.has(ch);
}

function isConsonantChar(ch) {
    return CONSONANT_CHARS.has(ch);
}

function isSilentFinal(ch) {
    return SILENT_FINAL_CHARS.has(ch);
}

function isFrontVowelForCG(ch) {
    return FRONT_VOWELS_CG.has(ch);
}

// Vowel phoneme detection (for prosody stress marking)
const VOWEL_PHONEMES = new Set([
    'a', 'e', 'i', 'o', 'u',
    IPA_OPEN_E, IPA_OPEN_O, IPA_SCHWA,
    IPA_SLASHED_O, IPA_OE_LIG,
    PUA_Y_VOWEL, PUA_NASAL_EIN, PUA_NASAL_AN, PUA_NASAL_ON,
]);

function isVowelPhoneme(ch) {
    return VOWEL_PHONEMES.has(ch);
}

// ---------------------------------------------------------------------------
// Exception word sets
// ---------------------------------------------------------------------------

const ILLE_AS_IL = new Set(['ville', 'mille', 'tranquille']);

const ER_AS_EHR = new Set([
    'hiver', 'enfer', 'amer', 'cancer', 'super', 'laser',
    'hamster', 'master', 'poster', 'cluster', 'starter',
    'leader', 'transfer', 'fer',
]);

// collapseNfdAccents, normalizeWhitespace imported from latin-common

/**
 * French-specific lowercase conversion.
 * @param {string} ch - Single character.
 * @returns {string} Lowercased character.
 */
function toLowerFr(ch) {
    const code = ch.codePointAt(0);
    // ASCII uppercase -> lowercase
    if (code >= 0x41 && code <= 0x5A) return String.fromCodePoint(code + 32);
    // Latin-1 uppercase block (A-grave..O-diaeresis, O-slash..Thorn)
    if ((code >= 0x00C0 && code <= 0x00D6) || (code >= 0x00D8 && code <= 0x00DE)) {
        return String.fromCodePoint(code + 0x20);
    }
    // OE ligature uppercase
    if (code === 0x0152) return '\u0153';
    return ch;
}

/**
 * Normalize text: collapse NFD, lowercase, collapse whitespace.
 * @param {string} text
 * @returns {string[]} Array of characters.
 */
function normalize(text) {
    // Split into character array and collapse NFD combining accents
    let cps = collapseNfdAccents([...text]);

    // Lowercase
    cps = cps.map(toLowerFr);

    // Collapse whitespace + trim
    return normalizeWhitespace(cps);
}

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

/**
 * Replace apostrophes (straight and curly) with spaces.
 * @param {string[]} chars
 * @returns {string[]}
 */
function normalizeApostrophes(chars) {
    return chars.map(ch => {
        if (ch === "'" || ch === '\u2019' || ch === '\u2018') return ' ';
        return ch;
    });
}

/**
 * Split normalized text into word and punctuation tokens.
 * Applies apostrophe normalization, then delegates to shared tokenizer.
 * @param {string[]} chars
 * @returns {Array<{chars: string[], isPunct: boolean}>}
 */
function splitWords(chars) {
    const processed = normalizeApostrophes(chars);
    return tokenize(processed, isLetterFr);
}

// ---------------------------------------------------------------------------
// Core word conversion: French G2P rules
// ---------------------------------------------------------------------------

/**
 * Count vowel characters in a word.
 * @param {string[]} word
 * @returns {number}
 */
function countVowels(word) {
    let count = 0;
    for (const ch of word) {
        if (isVowelChar(ch)) count++;
    }
    return count;
}

/**
 * Check if word matches ille-as-il exceptions.
 * @param {string[]} word
 * @returns {boolean}
 */
function isIlleAsIl(word) {
    return ILLE_AS_IL.has(word.join(''));
}

/**
 * Check if word matches er-as-ehr exceptions.
 * @param {string[]} word
 * @returns {boolean}
 */
function isErAsEhr(word) {
    return ER_AS_EHR.has(word.join(''));
}

/**
 * Try nasalizing a vowel + n/m sequence.
 * Returns true and pushes the nasal PUA if nasalization applies,
 * false otherwise.
 *
 * Nasal vowel guard (ALL 3 must be true for nasalization):
 * 1. word-final (i + 2 >= n)
 * 2. next-next is NOT a vowel
 * 3. next-next is NOT the same as n/m (no double nn/mm)
 *
 * @param {string[]} word
 * @param {number} i - Current index (vowel position)
 * @param {number} n - Word length
 * @param {string} nasalPua - PUA char for this nasal vowel
 * @param {string[]} phonemes - Output array
 * @returns {number|false} New index if consumed, false if not nasalized
 */
function tryNasalVowel(word, i, n, nasalPua, phonemes) {
    if (i + 1 >= n) return false;
    const nm = word[i + 1];
    if (nm !== 'n' && nm !== 'm') return false;

    // Word-final: nasalize
    if (i + 2 >= n) {
        phonemes.push(nasalPua);
        return i + 2;
    }

    // Next-next is vowel: DON'T nasalize ("anime")
    if (isVowelChar(word[i + 2])) return false;

    // Doubled nn/mm: DON'T nasalize ("bonne")
    if (word[i + 2] === nm) return false;

    // All 3 guards passed: nasalize
    phonemes.push(nasalPua);
    return i + 2;
}

/**
 * Convert a French word to IPA phoneme characters.
 *
 * Implements all G2P rules from french.rs convert_word():
 * multi-character sequences (longest match first), nasal vowels,
 * vowel digraphs, context-dependent single vowels, consonant digraphs,
 * silent final consonants, doubled consonant dedup, intervocalic s voicing.
 *
 * @param {string[]} word - Array of lowercase characters.
 * @returns {string[]} Array of IPA phoneme characters.
 */
function convertWord(word) {
    const phonemes = [];
    let i = 0;
    const n = word.length;

    while (i < n) {
        const ch = word[i];

        // ---------------------------------------------------------------
        // Phase A: Multi-character sequences (longest match first)
        // ---------------------------------------------------------------

        // -er word-final: verb infinitive ending -> /e/
        if (ch === 'e' && i + 1 === n - 1 && word[i + 1] === 'r') {
            const vc = countVowels(word);
            if (vc >= 2 && !isErAsEhr(word)) {
                phonemes.push('e');
                i += 2;
                continue;
            }
        }

        // "eau" -> o
        if (ch === 'e' && i + 2 < n && word[i + 1] === 'a' && word[i + 2] === 'u') {
            phonemes.push('o');
            i += 3;
            continue;
        }

        // "ouille" -> /uj/
        if (ch === 'o'
            && i + 5 < n
            && word[i + 1] === 'u'
            && word[i + 2] === 'i'
            && word[i + 3] === 'l'
            && word[i + 4] === 'l'
            && word[i + 5] === 'e'
            && (i + 6 >= n || !isVowelChar(word[i + 6]))
        ) {
            phonemes.push('u');
            phonemes.push('j');
            i += 6;
            continue;
        }

        // "aille" -> /aj/
        if (ch === 'a'
            && i + 4 < n
            && word[i + 1] === 'i'
            && word[i + 2] === 'l'
            && word[i + 3] === 'l'
            && word[i + 4] === 'e'
            && (i + 5 >= n || !isVowelChar(word[i + 5]))
        ) {
            phonemes.push('a');
            phonemes.push('j');
            i += 5;
            continue;
        }

        // "euille" -> /oej/ at word end (feuille)
        if (ch === 'e'
            && i + 5 < n
            && word[i + 1] === 'u'
            && word[i + 2] === 'i'
            && word[i + 3] === 'l'
            && word[i + 4] === 'l'
            && word[i + 5] === 'e'
            && i + 6 >= n
        ) {
            phonemes.push(IPA_OE_LIG);
            phonemes.push('j');
            i += 6;
            continue;
        }

        // "eil" at word end -> /ej/ (soleil, reveil)
        if (ch === 'e'
            && i + 2 < n
            && word[i + 1] === 'i'
            && word[i + 2] === 'l'
            && i + 3 >= n
        ) {
            phonemes.push(IPA_OPEN_E);
            phonemes.push('j');
            i += 3;
            continue;
        }

        // "eille" -> /ej/
        if (ch === 'e'
            && i + 4 < n
            && word[i + 1] === 'i'
            && word[i + 2] === 'l'
            && word[i + 3] === 'l'
            && word[i + 4] === 'e'
            && (i + 5 >= n || !isVowelChar(word[i + 5]))
        ) {
            phonemes.push(IPA_OPEN_E);
            phonemes.push('j');
            i += 5;
            continue;
        }

        // "ain", "aim" -> nasal-epsilon-tilde
        if (ch === 'a'
            && i + 2 < n
            && word[i + 1] === 'i'
            && (word[i + 2] === 'n' || word[i + 2] === 'm')
            && (i + 3 >= n || !isVowelChar(word[i + 3]))
        ) {
            phonemes.push(PUA_NASAL_EIN);
            i += 3;
            continue;
        }

        // "ein", "eim" -> nasal-epsilon-tilde
        if (ch === 'e'
            && i + 2 < n
            && word[i + 1] === 'i'
            && (word[i + 2] === 'n' || word[i + 2] === 'm')
            && (i + 3 >= n || !isVowelChar(word[i + 3]))
        ) {
            phonemes.push(PUA_NASAL_EIN);
            i += 3;
            continue;
        }

        // "oin" -> w + nasal-epsilon-tilde
        if (ch === 'o'
            && i + 2 < n
            && word[i + 1] === 'i'
            && word[i + 2] === 'n'
            && (i + 3 >= n || !isVowelChar(word[i + 3]))
        ) {
            phonemes.push('w');
            phonemes.push(PUA_NASAL_EIN);
            i += 3;
            continue;
        }

        // "ien" -> j + nasal-epsilon-tilde
        if (ch === 'i'
            && i + 2 < n
            && word[i + 1] === 'e'
            && word[i + 2] === 'n'
            && (i + 3 >= n || !isVowelChar(word[i + 3]))
        ) {
            phonemes.push('j');
            phonemes.push(PUA_NASAL_EIN);
            i += 3;
            continue;
        }

        // "tion" -> /sj + nasal-on/ (or /tj + nasal-on/ after 's')
        if (ch === 't'
            && i + 3 < n
            && word[i + 1] === 'i'
            && word[i + 2] === 'o'
            && word[i + 3] === 'n'
            && (i + 4 >= n || !isVowelChar(word[i + 4]))
        ) {
            if (i > 0 && word[i - 1] === 's') {
                phonemes.push('t');
            } else {
                phonemes.push('s');
            }
            phonemes.push('j');
            phonemes.push(PUA_NASAL_ON);
            i += 4;
            continue;
        }

        // "ille" -> /ij/ default, /il/ for exceptions
        if (ch === 'i'
            && i + 3 < n
            && word[i + 1] === 'l'
            && word[i + 2] === 'l'
            && word[i + 3] === 'e'
            && (i + 4 >= n || !isVowelChar(word[i + 4]))
        ) {
            phonemes.push('i');
            if (isIlleAsIl(word)) {
                phonemes.push('l');
            } else {
                phonemes.push('j');
            }
            i += 4;
            continue;
        }

        // "gn" -> palatal nasal
        if (ch === 'g' && i + 1 < n && word[i + 1] === 'n') {
            phonemes.push(IPA_PALATAL_N);
            i += 2;
            continue;
        }

        // "ph" -> f
        if (ch === 'p' && i + 1 < n && word[i + 1] === 'h') {
            phonemes.push('f');
            i += 2;
            continue;
        }

        // "th" -> t
        if (ch === 't' && i + 1 < n && word[i + 1] === 'h') {
            phonemes.push('t');
            i += 2;
            continue;
        }

        // "ch" -> voiceless postalveolar fricative
        if (ch === 'c' && i + 1 < n && word[i + 1] === 'h') {
            phonemes.push(IPA_ESH);
            i += 2;
            continue;
        }

        // "qu" -> k
        if (ch === 'q' && i + 1 < n && word[i + 1] === 'u') {
            phonemes.push('k');
            i += 2;
            continue;
        }

        // "gu" + front vowel -> voiced velar (silent u)
        if (ch === 'g'
            && i + 1 < n
            && word[i + 1] === 'u'
            && i + 2 < n
            && isFrontVowelForCG(word[i + 2])
        ) {
            phonemes.push(IPA_VOICED_G);
            i += 2;
            continue;
        }

        // ---------------------------------------------------------------
        // Phase B: Nasal vowels (5 vowel groups)
        // ---------------------------------------------------------------

        // "an", "am", "en", "em" -> nasal-alpha-tilde
        if (ch === 'a' || ch === 'e') {
            const result = tryNasalVowel(word, i, n, PUA_NASAL_AN, phonemes);
            if (result !== false) {
                i = result;
                continue;
            }
        }

        // "in", "im" -> nasal-epsilon-tilde
        if (ch === 'i') {
            const result = tryNasalVowel(word, i, n, PUA_NASAL_EIN, phonemes);
            if (result !== false) {
                i = result;
                continue;
            }
        }

        // "on", "om" -> nasal-open-o-tilde
        if (ch === 'o') {
            const result = tryNasalVowel(word, i, n, PUA_NASAL_ON, phonemes);
            if (result !== false) {
                i = result;
                continue;
            }
        }

        // "un", "um" -> nasal-epsilon-tilde (modern French merger)
        if (ch === 'u') {
            const result = tryNasalVowel(word, i, n, PUA_NASAL_EIN, phonemes);
            if (result !== false) {
                i = result;
                continue;
            }
        }

        // "yn", "ym" -> nasal-epsilon-tilde (syndicat, symbole)
        if (ch === 'y') {
            const result = tryNasalVowel(word, i, n, PUA_NASAL_EIN, phonemes);
            if (result !== false) {
                i = result;
                continue;
            }
        }

        // ---------------------------------------------------------------
        // Phase C: Vowel digraphs
        // ---------------------------------------------------------------

        // "ou" -> u
        if (ch === 'o' && i + 1 < n && word[i + 1] === 'u') {
            phonemes.push('u');
            i += 2;
            continue;
        }

        // "au" -> o
        if (ch === 'a' && i + 1 < n && word[i + 1] === 'u') {
            phonemes.push('o');
            i += 2;
            continue;
        }

        // "oi" -> wa
        if (ch === 'o' && i + 1 < n && word[i + 1] === 'i') {
            phonemes.push('w');
            phonemes.push('a');
            i += 2;
            continue;
        }

        // "ai" -> open-e
        if (ch === 'a' && i + 1 < n && word[i + 1] === 'i') {
            phonemes.push(IPA_OPEN_E);
            i += 2;
            continue;
        }

        // "ei" -> open-e
        if (ch === 'e' && i + 1 < n && word[i + 1] === 'i') {
            phonemes.push(IPA_OPEN_E);
            i += 2;
            continue;
        }

        // "eu", "oeu" -> slashed-o (closed) or oe-ligature (open before pronounced consonant)
        if ((ch === 'e' || ch === '\u0153') && i + 1 < n && word[i + 1] === 'u') {
            if (i + 2 < n && isConsonantChar(word[i + 2]) && !isSilentFinal(word[i + 2])) {
                phonemes.push(IPA_OE_LIG);
            } else {
                phonemes.push(IPA_SLASHED_O);
            }
            i += 2;
            continue;
        }

        // ---------------------------------------------------------------
        // Phase D: Single vowels
        // ---------------------------------------------------------------

        // e-acute -> e
        if (ch === '\u00E9') {
            phonemes.push('e');
            i += 1;
            continue;
        }

        // e-grave, e-circumflex -> open-e
        if (ch === '\u00E8' || ch === '\u00EA') {
            phonemes.push(IPA_OPEN_E);
            i += 1;
            continue;
        }

        // e-diaeresis -> open-e
        if (ch === '\u00EB') {
            phonemes.push(IPA_OPEN_E);
            i += 1;
            continue;
        }

        // a-grave, a-circumflex -> a
        if (ch === '\u00E0' || ch === '\u00E2') {
            phonemes.push('a');
            i += 1;
            continue;
        }

        // plain 'a'
        if (ch === 'a') {
            phonemes.push('a');
            i += 1;
            continue;
        }

        // i-circumflex, i-diaeresis -> i
        if (ch === '\u00EE' || ch === '\u00EF') {
            phonemes.push('i');
            i += 1;
            continue;
        }

        // i: before vowel -> j (semi-vowel), except before word-final silent 'e'
        if (ch === 'i') {
            if (i + 1 < n && isVowelChar(word[i + 1])) {
                if (i + 1 === n - 1 && word[i + 1] === 'e') {
                    phonemes.push('i');
                } else {
                    phonemes.push('j');
                }
            } else {
                phonemes.push('i');
            }
            i += 1;
            continue;
        }

        // o-circumflex -> o
        if (ch === '\u00F4') {
            phonemes.push('o');
            i += 1;
            continue;
        }

        // plain 'o': open before pronounced consonant, closed otherwise
        if (ch === 'o') {
            const effStart = i + 1;
            let effEnd = n;
            if (effEnd > effStart) {
                if (effEnd - effStart >= 2
                    && word[effEnd - 2] === 'e'
                    && word[effEnd - 1] === 's'
                ) {
                    effEnd -= 2;
                } else if (word[effEnd - 1] === 'e') {
                    effEnd -= 1;
                }
            }

            let hasEffective = false;
            let allConsonants = true;
            let hasPronounced = false;

            for (let k = effStart; k < effEnd; k++) {
                hasEffective = true;
                if (!isConsonantChar(word[k])) {
                    allConsonants = false;
                    break;
                }
                if (!isSilentFinal(word[k])) {
                    hasPronounced = true;
                }
            }

            if (hasEffective && allConsonants && hasPronounced) {
                phonemes.push(IPA_OPEN_O);
            } else {
                phonemes.push('o');
            }
            i += 1;
            continue;
        }

        // u-grave, u-circumflex -> y_vowel
        if (ch === '\u00F9' || ch === '\u00FB') {
            phonemes.push(PUA_Y_VOWEL);
            i += 1;
            continue;
        }

        // u-diaeresis -> y_vowel
        if (ch === '\u00FC') {
            phonemes.push(PUA_Y_VOWEL);
            i += 1;
            continue;
        }

        // u: semi-vowel before i, otherwise y_vowel
        if (ch === 'u') {
            if (i + 1 < n && word[i + 1] === 'i') {
                phonemes.push(IPA_TURNED_H);
                phonemes.push('i');
                i += 2;
                continue;
            }
            phonemes.push(PUA_Y_VOWEL);
            i += 1;
            continue;
        }

        // y: before vowel -> j, otherwise -> i
        if (ch === 'y') {
            if (i + 1 < n && isVowelChar(word[i + 1])) {
                phonemes.push('j');
            } else {
                phonemes.push('i');
            }
            i += 1;
            continue;
        }

        // oe ligature
        if (ch === '\u0153') {
            phonemes.push(IPA_OE_LIG);
            i += 1;
            continue;
        }

        // ae ligature
        if (ch === '\u00E6') {
            phonemes.push('e');
            i += 1;
            continue;
        }

        // plain 'e': context-dependent
        if (ch === 'e') {
            // Word-final e is silent
            if (i === n - 1) {
                i += 1;
                continue;
            }

            // Count consecutive consonants after this e
            let consCount = 0;
            for (let k = i + 1; k < n; k++) {
                if (isConsonantChar(word[k])) {
                    consCount++;
                } else {
                    break;
                }
            }

            // Closed syllable: 2+ consonants after e -> open-e
            if (consCount >= 2) {
                phonemes.push(IPA_OPEN_E);
                i += 1;
                continue;
            }

            // Check if remaining chars are all consonants with at least one pronounced
            const remaining = word.slice(i + 1);
            const allCons = remaining.length > 0 && remaining.every(c => isConsonantChar(c));
            const hasPronouncedCons = remaining.some(c => !isSilentFinal(c));

            if (remaining.length > 0 && allCons && hasPronouncedCons) {
                phonemes.push(IPA_OPEN_E);
            } else {
                phonemes.push(IPA_SCHWA);
            }
            i += 1;
            continue;
        }

        // ---------------------------------------------------------------
        // Phase E: Consonants
        // ---------------------------------------------------------------

        // c: before front vowel -> s, otherwise -> k
        if (ch === 'c') {
            if (i + 1 < n && isFrontVowelForCG(word[i + 1])) {
                phonemes.push('s');
            } else {
                phonemes.push('k');
            }
            i += 1;
            continue;
        }

        // c-cedilla -> s
        if (ch === '\u00E7') {
            phonemes.push('s');
            i += 1;
            continue;
        }

        // g: before front vowel -> ezh, otherwise -> voiced velar
        if (ch === 'g') {
            if (i + 1 < n && isFrontVowelForCG(word[i + 1])) {
                phonemes.push(IPA_EZH);
            } else {
                phonemes.push(IPA_VOICED_G);
            }
            i += 1;
            continue;
        }

        // j -> ezh
        if (ch === 'j') {
            phonemes.push(IPA_EZH);
            i += 1;
            continue;
        }

        // r: deduplicate rr -> single uvular-R
        if (ch === 'r') {
            phonemes.push(IPA_UVULAR_R);
            if (i + 1 < n && word[i + 1] === 'r') {
                i += 2;
            } else {
                i += 1;
            }
            continue;
        }

        // x: context-dependent
        if (ch === 'x') {
            // Word-final x: silent
            if (i === n - 1) {
                i += 1;
                continue;
            }
            // x + final "e" or "es": silent
            {
                const remLen = n - (i + 1);
                let silentBefore = false;
                if (remLen === 1 && word[i + 1] === 'e') {
                    silentBefore = true;
                } else if (remLen === 2 && word[i + 1] === 'e' && word[i + 2] === 's') {
                    silentBefore = true;
                }
                if (silentBefore) {
                    i += 1;
                    continue;
                }
            }
            // ex + vowel -> gz
            if (i > 0 && word[i - 1] === 'e' && i + 1 < n && isVowelChar(word[i + 1])) {
                phonemes.push(IPA_VOICED_G);
                phonemes.push('z');
                i += 1;
                continue;
            }
            // Default: ks
            phonemes.push('k');
            phonemes.push('s');
            i += 1;
            continue;
        }

        // h: always silent
        if (ch === 'h') {
            i += 1;
            continue;
        }

        // ---------------------------------------------------------------
        // Simple consonant mappings with silent final / intervocalic / dedup
        // ---------------------------------------------------------------
        const SIMPLE_MAP = {
            'b': 'b', 'd': 'd', 'f': 'f', 'k': 'k', 'l': 'l',
            'm': 'm', 'n': 'n', 'p': 'p', 's': 's', 't': 't',
            'v': 'v', 'w': 'w', 'z': 'z',
        };

        const mappedCh = SIMPLE_MAP[ch];
        if (mappedCh !== undefined) {
            const isWordFinal = (i === n - 1);
            const isBeforeFinalS = (n >= 2 && i === n - 2 && word[n - 1] === 's');
            const isFinal = isWordFinal || isBeforeFinalS;

            // Silent final consonant
            if (isFinal && isSilentFinal(ch)) {
                i += 1;
                continue;
            }

            // Intervocalic s voicing
            if (ch === 's') {
                const prevVowel = i > 0 && isVowelChar(word[i - 1]);
                const nextVowel = i + 1 < n && isVowelChar(word[i + 1]);
                const isSingle = !(i + 1 < n && word[i + 1] === 's');
                if (prevVowel && nextVowel && isSingle) {
                    phonemes.push('z');
                    i += 1;
                    continue;
                }
            }

            phonemes.push(mappedCh);
            // Dedup doubled consonants
            if (i + 1 < n && word[i + 1] === ch) {
                i += 2;
            } else {
                i += 1;
            }
            continue;
        }

        // Punctuation passthrough
        if (PUNCTUATION.has(ch)) {
            phonemes.push(ch);
            i += 1;
            continue;
        }

        // Unknown character: skip
        i += 1;
    }

    return phonemes;
}

// ---------------------------------------------------------------------------
// Top-level French phonemization
// ---------------------------------------------------------------------------

/**
 * Convert French text to phoneme characters with word spacing and punctuation.
 * @param {string} text
 * @returns {{ phonemes: string[], prosody: Array<{a1: number, a2: number, a3: number}|null> }}
 */
function phonemizeFrenchInternal(text) {
    if (!text) return { phonemes: [], prosody: [] };

    const normalized = normalize(text);
    const tokens = splitWords(normalized);

    const phonemes = [];
    const prosodyList = [];
    let needSpace = false;

    for (const tok of tokens) {
        if (!tok.isPunct && needSpace) {
            phonemes.push(' ');
            prosodyList.push({ a1: 0, a2: 0, a3: 0 });
        }

        if (tok.isPunct) {
            for (const ch of tok.chars) {
                phonemes.push(ch);
                prosodyList.push({ a1: 0, a2: 0, a3: 0 });
            }
        } else {
            const wordPhonemes = convertWord(tok.chars);
            const wordPhonemeCount = wordPhonemes.length;

            // Find last vowel index for stress marking
            let lastVowelIdx = -1;
            for (let j = wordPhonemes.length - 1; j >= 0; j--) {
                if (isVowelPhoneme(wordPhonemes[j])) {
                    lastVowelIdx = j;
                    break;
                }
            }

            for (let j = 0; j < wordPhonemes.length; j++) {
                const a2 = (j === lastVowelIdx) ? 2 : 0;
                phonemes.push(wordPhonemes[j]);
                prosodyList.push({ a1: 0, a2, a3: wordPhonemeCount });
            }
        }

        needSpace = true;
    }

    return { phonemes, prosody: prosodyList };
}

// ---------------------------------------------------------------------------
// FrenchG2P class
// ---------------------------------------------------------------------------

export class FrenchG2P {
    /**
     * Create a FrenchG2P instance.
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
        return 'fr';
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
     * Returns an object with `tokens` (array of single-character IPA strings)
     * and `prosody` (array of nulls, since French G2P does not provide
     * prosody information via this method).
     *
     * @param {string} text - Input French text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemize(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }

        const { phonemes } = phonemizeFrenchInternal(text);
        const prosody = new Array(phonemes.length).fill(null);
        return { tokens: phonemes, prosody };
    }

    /**
     * Convert French text to phoneme tokens with prosody information.
     *
     * French prosody: A1=0, A2=stress level (2=stressed, 0=unstressed),
     * A3=word phoneme count.
     *
     * @param {string} text - Input French text.
     * @returns {{ tokens: string[], prosody: ({ a1: number, a2: number, a3: number })[] }}
     */
    phonemizeWithProsody(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }

        const { phonemes, prosody } = phonemizeFrenchInternal(text);
        return { tokens: phonemes, prosody };
    }
}
