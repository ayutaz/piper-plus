/**
 * KoreanG2P -- Hangul decomposition + IPA mapping for @piper-plus/g2p.
 *
 * Ported from src/rust/piper-g2p/src/korean.rs.
 *
 * Features:
 * - Hangul syllable decomposition (U+AC00-D7AF) into initial/medial/final jamo
 * - Jamo-to-IPA mapping with PUA multi-char tokens
 * - Basic liaison rules (연음법칙) for consecutive syllables
 * - Tense consonants (ㅃ,ㄸ,ㄲ,ㅆ,ㅉ) with PUA codepoints
 * - Aspirated consonants (ㅋ,ㅌ,ㅍ) sharing PUA with Chinese
 * - Unreleased finals (k̚, t̚, p̚)
 * - NFD Hangul jamo recomposition (macOS compatibility)
 * - Latin character and punctuation passthrough
 *
 * Prosody values are fixed at a1=0, a2=0, a3=0 for Korean.
 *
 * Pure JavaScript -- no external dependencies.
 */

// ---------------------------------------------------------------------------
// Hangul syllable block range
// ---------------------------------------------------------------------------

const HANGUL_START = 0xAC00;
const HANGUL_END = 0xD7A3;

// Decomposition constants
const N_INITIALS = 19;
const N_MEDIALS = 21;
const N_FINALS = 28;

// ---------------------------------------------------------------------------
// PUA codepoints for multi-character IPA tokens
// Must match pua-map.js / token_map.rs / token_mapper.py
// ---------------------------------------------------------------------------

// Aspirated consonants (shared with Chinese)
const PUA_PH  = '\uE020'; // p\u02B0  (aspirated bilabial stop)
const PUA_TH  = '\uE021'; // t\u02B0  (aspirated alveolar stop)
const PUA_KH  = '\uE022'; // k\u02B0  (aspirated velar stop)

// Affricates (shared with Chinese)
const PUA_TC  = '\uE023'; // t\u0255  (alveolo-palatal affricate)
const PUA_TCH = '\uE024'; // t\u0255\u02B0  (aspirated alveolo-palatal affricate)

// Tense consonants (Korean-only)
const PUA_PP   = '\uE04B'; // p\u0348  (tense bilabial stop)
const PUA_TT   = '\uE04C'; // t\u0348  (tense alveolar stop)
const PUA_KK   = '\uE04D'; // k\u0348  (tense velar stop)
const PUA_SS   = '\uE04E'; // s\u0348  (tense sibilant fricative)
const PUA_TTCH = '\uE04F'; // t\u0348\u0255  (tense alveolo-palatal affricate)

// Unreleased finals (Korean-only)
const PUA_K_UNREL = '\uE050'; // k\u031A  (unreleased velar stop)
const PUA_T_UNREL = '\uE051'; // t\u031A  (unreleased alveolar stop)
const PUA_P_UNREL = '\uE052'; // p\u031A  (unreleased bilabial stop)

// Single IPA codepoints used in output
const IPA_FLAP           = '\u027E'; // ɾ  alveolar flap (ㄹ initial)
const IPA_ENG            = '\u014B'; // ŋ  velar nasal (ㅇ coda)
const IPA_OPEN_E         = '\u025B'; // ɛ  open-mid front unrounded (ㅐ)
const IPA_OPEN_MID_BACK  = '\u028C'; // ʌ  open-mid back unrounded (ㅓ)
const IPA_CLOSE_BACK_UNR = '\u026F'; // ɯ  close back unrounded (ㅡ)
const IPA_VELAR_APPROX   = '\u0270'; // ɰ  velar approximant (ㅢ)

// ---------------------------------------------------------------------------
// Initial consonants (초성) -- 19 entries, index -> IPA char or null
// null = silent (ㅇ in initial position)
// ---------------------------------------------------------------------------

const INITIAL_TABLE = [
    'k',       //  0: ㄱ
    PUA_KK,    //  1: ㄲ (tense)
    'n',       //  2: ㄴ
    't',       //  3: ㄷ
    PUA_TT,    //  4: ㄸ (tense)
    IPA_FLAP,  //  5: ㄹ
    'm',       //  6: ㅁ
    'p',       //  7: ㅂ
    PUA_PP,    //  8: ㅃ (tense)
    's',       //  9: ㅅ
    PUA_SS,    // 10: ㅆ (tense)
    null,      // 11: ㅇ (silent in initial)
    PUA_TC,    // 12: ㅈ
    PUA_TTCH,  // 13: ㅉ (tense)
    PUA_TCH,   // 14: ㅊ (aspirated)
    PUA_KH,    // 15: ㅋ (aspirated)
    PUA_TH,    // 16: ㅌ (aspirated)
    PUA_PH,    // 17: ㅍ (aspirated)
    'h',       // 18: ㅎ
];

// ---------------------------------------------------------------------------
// Medial vowels (중성) -- 21 entries, index -> [phoneme1, phoneme2 or null]
// Diphthongs produce glide + vowel (2 phonemes).
// ---------------------------------------------------------------------------

const MEDIAL_TABLE = [
    ['a', null],                        //  0: ㅏ
    [IPA_OPEN_E, null],                 //  1: ㅐ
    ['j', 'a'],                         //  2: ㅑ
    ['j', IPA_OPEN_E],                  //  3: ㅒ
    [IPA_OPEN_MID_BACK, null],          //  4: ㅓ
    ['e', null],                        //  5: ㅔ
    ['j', IPA_OPEN_MID_BACK],           //  6: ㅕ
    ['j', 'e'],                         //  7: ㅖ
    ['o', null],                        //  8: ㅗ
    ['w', 'a'],                         //  9: ㅘ
    ['w', IPA_OPEN_E],                  // 10: ㅙ
    ['w', 'e'],                         // 11: ㅚ (modern Seoul: [we])
    ['j', 'o'],                         // 12: ㅛ
    ['u', null],                        // 13: ㅜ
    ['w', IPA_OPEN_MID_BACK],           // 14: ㅝ
    ['w', 'e'],                         // 15: ㅞ
    ['w', 'i'],                         // 16: ㅟ
    ['j', 'u'],                         // 17: ㅠ
    [IPA_CLOSE_BACK_UNR, null],         // 18: ㅡ
    [IPA_VELAR_APPROX, 'i'],            // 19: ㅢ
    ['i', null],                        // 20: ㅣ
];

// ---------------------------------------------------------------------------
// Final consonants (종성) -- 28 entries
//
// Finals are neutralized to 7 surface forms: k̚, t̚, p̚, n, m, l, ŋ.
// Complex finals (겹받침) are simplified to their representative sound.
// Index 0 = no final consonant.
//
// For liaison: `liaisonInitial` is the initial index the final "becomes"
// when followed by ㅇ (silent initial). -1 means no liaison.
// `residualFinal` holds the index remaining in the current syllable after
// liaison (for complex finals); 0 means the final moves entirely.
// ---------------------------------------------------------------------------

const FINAL_TABLE = [
    { ph: null,        liaisonInitial: -1, residualFinal:  0 }, //  0: (none)
    { ph: PUA_K_UNREL, liaisonInitial:  0, residualFinal:  0 }, //  1: ㄱ
    { ph: PUA_K_UNREL, liaisonInitial:  1, residualFinal:  0 }, //  2: ㄲ
    { ph: PUA_K_UNREL, liaisonInitial:  9, residualFinal:  1 }, //  3: ㄳ -> ㅅ, residual ㄱ
    { ph: 'n',         liaisonInitial: -1, residualFinal:  0 }, //  4: ㄴ
    { ph: 'n',         liaisonInitial: 12, residualFinal:  4 }, //  5: ㄵ -> ㅈ, residual ㄴ
    { ph: 'n',         liaisonInitial: -1, residualFinal:  0 }, //  6: ㄶ (ㄴ+ㅎ -> n)
    { ph: PUA_T_UNREL, liaisonInitial:  3, residualFinal:  0 }, //  7: ㄷ
    { ph: 'l',         liaisonInitial:  5, residualFinal:  0 }, //  8: ㄹ
    { ph: PUA_K_UNREL, liaisonInitial:  0, residualFinal:  8 }, //  9: ㄺ -> ㄱ, residual ㄹ
    { ph: 'm',         liaisonInitial:  6, residualFinal:  8 }, // 10: ㄻ -> ㅁ, residual ㄹ
    { ph: 'l',         liaisonInitial:  7, residualFinal:  8 }, // 11: ㄼ -> ㅂ, residual ㄹ
    { ph: 'l',         liaisonInitial:  9, residualFinal:  8 }, // 12: ㄽ -> ㅅ, residual ㄹ
    { ph: 'l',         liaisonInitial: 16, residualFinal:  8 }, // 13: ㄾ -> ㅌ, residual ㄹ
    { ph: 'l',         liaisonInitial: 17, residualFinal:  8 }, // 14: ㄿ -> ㅍ, residual ㄹ
    { ph: 'l',         liaisonInitial: -1, residualFinal:  0 }, // 15: ㅀ (ㄹ+ㅎ -> l)
    { ph: 'm',         liaisonInitial: -1, residualFinal:  0 }, // 16: ㅁ
    { ph: PUA_P_UNREL, liaisonInitial:  7, residualFinal:  0 }, // 17: ㅂ
    { ph: PUA_P_UNREL, liaisonInitial:  9, residualFinal: 17 }, // 18: ㅄ -> ㅅ, residual ㅂ
    { ph: PUA_T_UNREL, liaisonInitial:  9, residualFinal:  0 }, // 19: ㅅ
    { ph: PUA_T_UNREL, liaisonInitial: 10, residualFinal:  0 }, // 20: ㅆ
    { ph: IPA_ENG,     liaisonInitial: -1, residualFinal:  0 }, // 21: ㅇ (velar nasal)
    { ph: PUA_T_UNREL, liaisonInitial: 12, residualFinal:  0 }, // 22: ㅈ
    { ph: PUA_T_UNREL, liaisonInitial: 14, residualFinal:  0 }, // 23: ㅊ
    { ph: PUA_K_UNREL, liaisonInitial: 15, residualFinal:  0 }, // 24: ㅋ
    { ph: PUA_T_UNREL, liaisonInitial: 16, residualFinal:  0 }, // 25: ㅌ
    { ph: PUA_P_UNREL, liaisonInitial: 17, residualFinal:  0 }, // 26: ㅍ
    { ph: PUA_T_UNREL, liaisonInitial: -1, residualFinal:  0 }, // 27: ㅎ (h dropped)
];

// ---------------------------------------------------------------------------
// Punctuation
// ---------------------------------------------------------------------------

const PUNCTUATION = new Set([
    ',', '.', ';', ':', '!', '?',
    '\u3002', // 。 CJK period
    '\uFF0C', // ， CJK comma
    '\uFF01', // ！ CJK exclamation
    '\uFF1F', // ？ CJK question
    '\u3001', // 、 CJK enumeration comma
]);

// ---------------------------------------------------------------------------
// Hangul decomposition
// ---------------------------------------------------------------------------

/**
 * Check if a codepoint is a precomposed Hangul syllable (U+AC00..U+D7A3).
 * @param {number} code - Character codepoint.
 * @returns {boolean}
 */
function isHangulSyllable(code) {
    return code >= HANGUL_START && code <= HANGUL_END;
}

/**
 * Decompose a Hangul syllable codepoint into (initial, medial, final) indices.
 * @param {number} code - Hangul syllable codepoint.
 * @returns {{ initial: number, medial: number, final_: number }}
 */
function decompose(code) {
    const offset = code - HANGUL_START;
    const initial = Math.floor(offset / (N_MEDIALS * N_FINALS));
    const medial = Math.floor((offset % (N_MEDIALS * N_FINALS)) / N_FINALS);
    const final_ = offset % N_FINALS;
    return { initial, medial, final_ };
}

// ---------------------------------------------------------------------------
// NFD Hangul jamo -> NFC recomposition
//
// macOS decomposes Hangul into NFD jamo sequences (U+1100-U+11FF).
// This function recomposes them into precomposed syllables (U+AC00-U+D7A3).
// ---------------------------------------------------------------------------

/**
 * Check if a codepoint is a leading jamo (U+1100..U+1112).
 * @param {number} code
 * @returns {boolean}
 */
function isLeadingJamo(code) {
    return code >= 0x1100 && code <= 0x1112;
}

/**
 * Check if a codepoint is a vowel jamo (U+1161..U+1175).
 * @param {number} code
 * @returns {boolean}
 */
function isVowelJamo(code) {
    return code >= 0x1161 && code <= 0x1175;
}

/**
 * Check if a codepoint is a trailing jamo (U+11A8..U+11C2).
 * @param {number} code
 * @returns {boolean}
 */
function isTrailingJamo(code) {
    return code >= 0x11A8 && code <= 0x11C2;
}

/**
 * Recompose NFD Hangul jamo sequences into NFC precomposed syllables.
 * Non-jamo codepoints are passed through unchanged.
 * @param {number[]} codepoints - Array of codepoints.
 * @returns {number[]} Recomposed codepoints.
 */
function composeHangulJamo(codepoints) {
    const out = [];
    const n = codepoints.length;
    let i = 0;

    while (i < n) {
        if (isLeadingJamo(codepoints[i]) &&
            i + 1 < n &&
            isVowelJamo(codepoints[i + 1])) {
            const leading = codepoints[i] - 0x1100;
            const vowel = codepoints[i + 1] - 0x1161;
            let trailing;
            if (i + 2 < n && isTrailingJamo(codepoints[i + 2])) {
                trailing = codepoints[i + 2] - 0x11A8 + 1;
                i += 3;
            } else {
                trailing = 0;
                i += 2;
            }
            const composed = (leading * 21 + vowel) * 28 + trailing + 0xAC00;
            out.push(composed);
        } else {
            out.push(codepoints[i]);
            i += 1;
        }
    }

    return out;
}

// ---------------------------------------------------------------------------
// Emit phonemes for a single syllable (after liaison adjustment)
// ---------------------------------------------------------------------------

/**
 * Emit IPA phoneme characters for a single decomposed syllable.
 * @param {{ initial: number, medial: number, final_: number }} syl
 * @param {string[]} out - Output array to push phoneme chars into.
 */
function emitSyllable(syl, out) {
    // Initial consonant
    if (syl.initial < N_INITIALS) {
        const ph = INITIAL_TABLE[syl.initial];
        if (ph !== null) {
            out.push(ph);
        }
    }

    // Medial vowel (1-2 phonemes)
    if (syl.medial < N_MEDIALS) {
        const [ph1, ph2] = MEDIAL_TABLE[syl.medial];
        out.push(ph1);
        if (ph2 !== null) {
            out.push(ph2);
        }
    }

    // Final consonant
    if (syl.final_ > 0 && syl.final_ < N_FINALS) {
        const entry = FINAL_TABLE[syl.final_];
        if (entry.ph !== null) {
            out.push(entry.ph);
        }
    }
}

// ---------------------------------------------------------------------------
// Process a run of Hangul syllables: decompose, apply liaison, emit phonemes
// ---------------------------------------------------------------------------

/**
 * Process a contiguous run of Hangul syllable codepoints.
 * Decomposes each syllable, applies basic liaison (연음화), and emits
 * IPA phoneme characters.
 *
 * Liaison rule: if syllable[i] has a final consonant and syllable[i+1]
 * starts with ㅇ (initial index 11, silent), the final moves to become
 * the next syllable's initial in its released form. For complex finals
 * (겹받침), the second component moves and the first remains.
 *
 * @param {number[]} codes - Array of Hangul syllable codepoints.
 * @param {string[]} out - Output array to push phoneme chars into.
 */
function processHangulRun(codes, out) {
    if (codes.length === 0) {
        return;
    }

    // Decompose all syllables
    const syls = codes.map(code => decompose(code));

    // Apply basic liaison (연음화)
    for (let i = 0; i < syls.length - 1; i++) {
        const fi = syls[i].final_;
        if (fi === 0 || fi >= N_FINALS) {
            continue;
        }
        if (syls[i + 1].initial !== 11) {
            continue;
        }

        const entry = FINAL_TABLE[fi];
        if (entry.liaisonInitial < 0) {
            continue;
        }

        // Move final -> next initial (released form)
        syls[i + 1].initial = entry.liaisonInitial;
        // For complex finals, keep residual; for simple finals, clears entirely.
        syls[i].final_ = entry.residualFinal;
    }

    // Emit phonemes for all syllables
    for (const syl of syls) {
        emitSyllable(syl, out);
    }
}

// ---------------------------------------------------------------------------
// Core phonemization: text -> flat array of IPA phoneme characters
// ---------------------------------------------------------------------------

/**
 * Convert Korean text to a flat array of IPA phoneme characters.
 * Each element is a single character (including PUA codepoints for
 * multi-codepoint IPA tokens).
 *
 * Processing order:
 * 1. NFD jamo recomposition (for macOS)
 * 2. Whitespace marks word boundaries
 * 3. Punctuation is emitted directly
 * 4. Hangul syllable runs are decomposed with liaison applied
 * 5. Latin alphabetic characters pass through lowercase
 * 6. Unknown characters are skipped
 *
 * @param {string} text - Input Korean text.
 * @returns {string[]} Array of single-character IPA phoneme tokens.
 */
function textToPhonemeChars(text) {
    if (!text) {
        return [];
    }

    // Convert to array of codepoints
    let codepoints = [];
    for (const ch of text) {
        codepoints.push(ch.codePointAt(0));
    }

    // Recompose NFD Hangul jamo sequences (macOS) into NFC precomposed syllables
    codepoints = composeHangulJamo(codepoints);

    const sentence = [];
    let needSpace = false;

    const n = codepoints.length;
    let i = 0;

    while (i < n) {
        const code = codepoints[i];
        const ch = String.fromCodePoint(code);

        // Whitespace -> mark word boundary
        if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') {
            needSpace = true;
            i++;
            continue;
        }

        // Punctuation -> emit directly
        if (PUNCTUATION.has(ch)) {
            sentence.push(ch);
            needSpace = false;
            i++;
            continue;
        }

        // Hangul syllable run
        if (isHangulSyllable(code)) {
            if (needSpace && sentence.length > 0) {
                sentence.push(' ');
            }

            // Find the extent of the Hangul run
            const runStart = i;
            while (i < n && isHangulSyllable(codepoints[i])) {
                i++;
            }
            processHangulRun(codepoints.slice(runStart, i), sentence);
            needSpace = true;
            continue;
        }

        // Latin alphabetic -> pass through lowercase
        if ((code >= 0x41 && code <= 0x5A) || (code >= 0x61 && code <= 0x7A)) {
            if (needSpace && sentence.length > 0) {
                sentence.push(' ');
            }
            sentence.push(ch.toLowerCase());
            needSpace = true;
            i++;
            continue;
        }

        // Unknown character -> skip
        i++;
    }

    return sentence;
}

// ---------------------------------------------------------------------------
// KoreanG2P class
// ---------------------------------------------------------------------------

export class KoreanG2P {
    /**
     * Create a KoreanG2P instance.
     * @param {object} [options] - Reserved for future options.
     */
    constructor(options = {}) {
        this._options = options;
    }

    /**
     * Language code for this G2P instance.
     * @type {string}
     */
    get languageCode() {
        return 'ko';
    }

    /**
     * Convert Korean text to phoneme tokens.
     *
     * Returns an object with `tokens` (array of single-character IPA strings)
     * and `prosody` (array of nulls, since Korean G2P does not provide
     * prosody information via this method).
     *
     * Hangul syllables are decomposed into jamo and mapped to IPA phonemes.
     * Basic liaison (연음법칙) is applied when a final consonant is followed
     * by a syllable starting with ㅇ (silent initial).
     *
     * @param {string} text - Input Korean text.
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
     * Convert Korean text to phoneme tokens with prosody information.
     *
     * Korean prosody: A1=0, A2=0, A3=0 (fixed; Korean does not use
     * pitch accent or stress-based prosody features in this G2P).
     *
     * @param {string} text - Input Korean text.
     * @returns {{ tokens: string[], prosody: ({ a1: number, a2: number, a3: number })[] }}
     */
    phonemizeWithProsody(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }

        const tokens = textToPhonemeChars(text);
        const prosody = tokens.map(() => ({ a1: 0, a2: 0, a3: 0 }));
        return { tokens, prosody };
    }
}
