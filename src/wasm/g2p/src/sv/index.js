/**
 * SwedishG2P -- rule-based Swedish G2P for @piper-plus/g2p.
 *
 * Ported from src/go/phonemize/swedish.go (1,218 lines).
 *
 * Features:
 * - 9 long / 9 short vowel mappings (Complementary Quantity)
 * - Soft k/g rules (before front vowels, with exception lists)
 * - Retroflex assimilation (rt -> ʈ, rd -> ɖ, rs -> ʂ, rn -> ɳ, rl -> ɭ)
 * - Loanword suffix rules (-tion, -sion, -age, -eur, etc.)
 * - Stress detection (function words, suffixes, prefixes)
 * - Prosody: A1=0, A2=stress_level, A3=syllable_count
 *
 * Pure JavaScript -- no external dependencies.
 */

// ---------------------------------------------------------------------------
// Vowel / consonant sets
// ---------------------------------------------------------------------------

const FRONT_VOWELS = new Set(['e', 'i', 'y', '\u00e4', '\u00f6']); // ä, ö
const ALL_VOWELS = new Set([
    'a', 'e', 'i', 'o', 'u', 'y',
    '\u00e5', '\u00e4', '\u00f6',  // å, ä, ö
]);
const CONSONANTS = new Set([
    'b', 'c', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'm',
    'n', 'p', 'q', 'r', 's', 't', 'v', 'w', 'x', 'z',
]);
const PUNCTUATION = new Set(['.', ',', ';', ':', '!', '?']);

// ---------------------------------------------------------------------------
// Vowel mappings (Complementary Quantity)
// ---------------------------------------------------------------------------

const LONG_VOWEL_MAP = {
    'a':      '\u0251\u02d0', // ɑː
    'e':      'e\u02d0',      // eː
    'i':      'i\u02d0',      // iː
    'o':      'u\u02d0',      // uː (default; oː for O_LONG_AS_OO words)
    'u':      '\u0289\u02d0', // ʉː
    'y':      'y\u02d0',      // yː
    '\u00e5': 'o\u02d0',      // å -> oː
    '\u00e4': '\u025b\u02d0', // ä -> ɛː
    '\u00f6': '\u00f8\u02d0', // ö -> øː
};

const SHORT_VOWEL_MAP = {
    'a':      'a',
    'e':      '\u025b',  // ɛ
    'i':      '\u026a',  // ɪ
    'o':      '\u0254',  // ɔ
    'u':      '\u0275',  // ɵ
    'y':      '\u028f',  // ʏ
    '\u00e5': '\u0254',  // å -> ɔ
    '\u00e4': '\u025b',  // ä -> ɛ
    '\u00f6': '\u0153',  // ö -> œ
};

const O_LONG_AS_OO_PHONEME = 'o\u02d0'; // oː

// ---------------------------------------------------------------------------
// Default consonant -> IPA
// ---------------------------------------------------------------------------

const CONSONANT_DEFAULT = {
    'b': 'b',
    'c': 'k',
    'd': 'd',
    'f': 'f',
    'g': '\u0261', // ɡ (IPA U+0261)
    'h': 'h',
    'j': 'j',
    'k': 'k',
    'l': 'l',
    'm': 'm',
    'n': 'n',
    'p': 'p',
    'q': 'k',
    'r': 'r',
    's': 's',
    't': 't',
    'v': 'v',
    'w': 'v',
    'x': 'ks',
    'z': 's',
};

// ---------------------------------------------------------------------------
// Exception word lists (matching Go reference exactly)
// ---------------------------------------------------------------------------

// svHardKWords: k + front vowel -> /k/ (hard). 75 words.
const HARD_K_WORDS = new Set([
    'backe', 'bricka', 'docka', 'dricka', 'dyker', 'dyket', 'enkel', 'ficka',
    'flicka', 'fr\u00f6ken', 'kebab', 'kennel', 'kent', 'keps', 'kerna',
    'keso', 'ketchup', 'kex', 'kibbutz', 'kick', 'kikare', 'kille', 'kilo',
    'kilt', 'kimono', 'kines', 'kinesisk', 'kiosk', 'kirke', 'kissa',
    'kitsch', 'kiwi', 'leken', 'leker', 'lekerska', 'l\u00e4ker', 'l\u00e4ket',
    'm\u00e4rke', 'm\u00e4rker', 'm\u00e4rket', 'm\u00f6rker', 'naken',
    'ocker', 'onkel', 'paket', 'pojke', 'raket', 'rike', 'ryker',
    'r\u00e4cker', 'r\u00f6ker', 'r\u00f6ket', 'silke', 'sjunker', 'skelett',
    'skicka', 'smeker', 'sockel', 'socker', 'staket', 'steker', 'steket',
    'sticker', 'stryker', 's\u00e4ker', 's\u00f6ker', 's\u00f6ket', 'tecken',
    'trycke', 't\u00e4nker', 't\u00e4nket', 'vacker', 'viker', 'vinkel',
    'v\u00e4cker',
]);

// svHardKStems: k + front vowel -> /k/ stem forms. 33 stems.
const HARD_K_STEMS = new Set([
    'back', 'block', 'brick', 'dock', 'drick', 'dyk', 'fick', 'flick',
    'lek', 'lock', 'l\u00e4k', 'm\u00e4rk', 'pack', 'rock', 'ryk',
    'r\u00e4ck', 'r\u00f6k', 'sack', 'sick', 'sjunk', 'skick', 'smek',
    'sock', 'stek', 'stick', 'stryk', 's\u00f6k', 'tack', 'trick',
    'tryck', 't\u00e4nk', 'vik', 'v\u00e4ck',
]);

// svHardGWords: g + front vowel -> /ɡ/ (hard). 55 words.
const HARD_G_WORDS = new Set([
    'agera', 'arrangera', 'bagel', 'bageri', 'berg', 'borg', 'bygel',
    'bygge', 'b\u00e5ge', 'dager', 'delegera', 'duger', 'engagera',
    'finger', 'flygel', 'flyger', 'fogel', 'f\u00e5gel', 'ge', 'gecko',
    'gel', 'ger', 'hage', 'hagel', 'hunger', 'ignorera', 'intrigera',
    'lager', 'ligger', 'ljuger', 'l\u00e4ge', 'l\u00e4ger', 'l\u00e4gger',
    'mage', 'nagel', 'navigera', 'negera', 'reagera', 'regel', 'segel',
    'seger', 'segregera', 'spegel', 'stege', 'stiger', 'suger', 'tagel',
    'tangera', 'tegel', 'tiger', 'tigger', 'tygel', 'v\u00e4ger',
    '\u00e4ger', '\u00e4ngel',
]);

// svHardGStems: g + front vowel -> /ɡ/ stem forms. 23 stems.
const HARD_G_STEMS = new Set([
    'bag', 'berg', 'borg', 'byg', 'dag', 'drag', 'dug', 'flyg', 'lag',
    'lig', 'ljug', 'l\u00e4gg', 'mag', 'nag', 'reg', 'seg', 'stig',
    'sug', 'tag', 'tig', 'vag', 'v\u00e4g', '\u00e4g',
]);

// svOLongAsOO: "o" -> /oː/ instead of default /uː/. 30 words.
const O_LONG_AS_OO = new Set([
    'blod', 'bo', 'bror', 'dom', 'flod', 'fon', 'fot', 'god', 'ion',
    'jord', 'ko', 'kol', 'kontroll', 'lo', 'lov', 'mod', 'mol', 'mor',
    'nod', 'ord', 'pol', 'ro', 'rod', 'roll', 'rot', 'son', 'tog',
    'ton', 'tro', 'zon',
]);

// svFinalMShortWords: words ending in -m with short vowel. 18 words.
const FINAL_M_SHORT_WORDS = new Set([
    'dam', 'dom', 'dr\u00f6m', 'dum', 'fem', 'gl\u00f6m', 'gum', 'ham',
    'hem', 'kam', 'lam', 'lem', 'ram', 'rum', 'som', 'stam',
    'str\u00f6m', 'tom',
]);

// svFunctionWords: unstressed function words. 37 words.
const FUNCTION_WORDS = new Set([
    'att', 'av', 'de', 'dem', 'den', 'det', 'din', 'du', 'en', 'ett',
    'fr\u00e5n', 'f\u00f6r', 'han', 'har', 'hon', 'hos', 'i', 'inte',
    'jag', 'kan', 'med', 'men', 'min', 'n\u00e4r', 'och', 'om',
    'p\u00e5', 'sig', 'sin', 'ska', 'som', 'till', 'ur', 'var', 'vi',
    'vill', '\u00e4r',
]);

// svSKBackVowelExceptions: sk + back vowel -> /ɧ/ exceptions. 2 words.
const SK_BACK_VOWEL_EXCEPTIONS = new Set(['m\u00e4nniska', 'marskalk']);

// svCHExceptionsK: ch -> /k/ exceptions. 5 words.
const CH_EXCEPTIONS_K = new Set(['krist', 'kristus', 'kron', 'kronik', 'och']);

// svAgeNativeWords: -age suffix that is native Swedish (not French loan). 11 words.
const AGE_NATIVE_WORDS = new Set([
    'bage', 'dage', 'drage', 'frage', 'hage', 'klage', 'lage', 'mage',
    'plage', 'sage', 'tage',
]);

// ---------------------------------------------------------------------------
// Loanword suffix rules (ordered longest-suffix first)
// ---------------------------------------------------------------------------

const LOANWORD_SUFFIX_RULES = [
    { suffix: 'ssion', phonemes: ['\u0267', 'u\u02d0', 'n'] },     // ɧ uː n
    { suffix: 'tion',  phonemes: ['\u0267', 'u\u02d0', 'n'] },     // ɧ uː n
    { suffix: 'sion',  phonemes: ['\u0267', 'u\u02d0', 'n'] },     // ɧ uː n
    { suffix: 'age',   phonemes: ['\u0251\u02d0', '\u0267'] },     // ɑː ɧ
    { suffix: 'eur',   phonemes: ['\u00f8\u02d0', 'r'] },          // øː r
    { suffix: 'eum',   phonemes: ['e\u02d0', '\u0275', 'm'] },     // eː ɵ m
    { suffix: 'ium',   phonemes: ['\u026a', '\u0275', 'm'] },      // ɪ ɵ m
];

// ---------------------------------------------------------------------------
// Stress-attracting suffixes and unstressed prefixes
// ---------------------------------------------------------------------------

const STRESS_ATTRACTING_SUFFIXES = [
    'ssion', 'tion', 'sion', 'itet',
    'eri', 'era', 'ist', '\u00f6r',  // ör
    'ment', 'ans', 'ens', 'ell',
    'ent', 'ant', 'ik', 'ur', 'al', '\u00f6s',  // ös
];

const UNSTRESSED_PREFIXES = [
    'f\u00f6r',  // för
    'be', 'ge', 'er', 'an',
];

// ---------------------------------------------------------------------------
// IPA vowel detection (for stress marker insertion)
// ---------------------------------------------------------------------------

const IPA_VOWEL_SET = new Set([
    'a', 'e', 'i', 'o', 'u', 'y',
    '\u00e5', '\u00e4', '\u00f6',  // å ä ö
    '\u0251', // ɑ
    '\u025b', // ɛ
    '\u026a', // ɪ
    '\u0254', // ɔ
    '\u028a', // ʊ
    '\u0289', // ʉ
    '\u028f', // ʏ
    '\u0153', // œ
    '\u00f8', // ø
    '\u0275', // ɵ
]);

// ---------------------------------------------------------------------------
// Retroflex assimilation map
// ---------------------------------------------------------------------------

const RETROFLEX_MAP = {
    't': '\u0288', // ʈ
    'd': '\u0256', // ɖ
    's': '\u0282', // ʂ
    'n': '\u0273', // ɳ
    'l': '\u026d', // ɭ
};

// Retroflexes that propagate cascade (ɭ stops it).
const PROPAGATING_RETROFLEXES = new Set([
    '\u0288', // ʈ
    '\u0256', // ɖ
    '\u0282', // ʂ
    '\u0273', // ɳ
]);

// ---------------------------------------------------------------------------
// Normalization
// ---------------------------------------------------------------------------

/**
 * Normalize Swedish text: NFC, lowercase, collapse whitespace.
 * @param {string} text
 * @returns {string}
 */
function svNormalize(text) {
    text = text.trim();
    text = text.normalize('NFC');
    text = text.toLowerCase();
    text = text.replace(/\s+/g, ' ');
    return text;
}

// ---------------------------------------------------------------------------
// Tokenization
// ---------------------------------------------------------------------------

/** @param {number} code */
function isWordChar(code) {
    // a-z
    if (code >= 0x61 && code <= 0x7A) return true;
    // Swedish special chars: å ä ö
    if (code === 0xE5 || code === 0xE4 || code === 0xF6) return true;
    // Loanword accented chars: é à ü á è ë ï
    if (code === 0xE9 || code === 0xE0 || code === 0xFC) return true;
    if (code === 0xE1 || code === 0xE8 || code === 0xEB || code === 0xEF) return true;
    return false;
}

/**
 * Tokenize text into word and punctuation tokens.
 * @param {string} text - Normalized text.
 * @returns {Array<{ text: string, isPun: boolean }>}
 */
function svTokenize(text) {
    const tokens = [];
    const chars = [...text]; // Handle Unicode correctly
    let i = 0;
    const n = chars.length;

    while (i < n) {
        const ch = chars[i];
        const code = ch.codePointAt(0);

        if (ch === ' ' || ch === '\t' || ch === '\n') {
            i++;
            continue;
        }

        if (PUNCTUATION.has(ch)) {
            tokens.push({ text: ch, isPun: true });
            i++;
            continue;
        }

        if (isWordChar(code)) {
            const start = i;
            while (i < n && isWordChar(chars[i].codePointAt(0))) {
                i++;
            }
            tokens.push({ text: chars.slice(start, i).join(''), isPun: false });
            continue;
        }

        i++; // skip unknown characters
    }

    return tokens;
}

// ---------------------------------------------------------------------------
// Helper: count syllables in a word
// ---------------------------------------------------------------------------

function countSyllables(word) {
    let count = 0;
    let prevVowel = false;
    for (const ch of word) {
        if (ALL_VOWELS.has(ch)) {
            if (!prevVowel) count++;
            prevVowel = true;
        } else {
            prevVowel = false;
        }
    }
    return count === 0 ? 1 : count;
}

// ---------------------------------------------------------------------------
// Loanword suffix detection
// ---------------------------------------------------------------------------

function detectLoanwordSuffix(word) {
    for (const rule of LOANWORD_SUFFIX_RULES) {
        if (word.endsWith(rule.suffix) && word.length > rule.suffix.length) {
            // -age native exception
            if (rule.suffix === 'age' && AGE_NATIVE_WORDS.has(word)) {
                continue;
            }
            const stem = word.slice(0, word.length - rule.suffix.length);
            return { stem, phonemes: rule.phonemes, found: true };
        }
    }
    return { stem: '', phonemes: null, found: false };
}

// ---------------------------------------------------------------------------
// Hard k/g checks (with morphological heuristic)
// ---------------------------------------------------------------------------

function isHardK(word) {
    if (HARD_K_WORDS.has(word)) return true;
    const runes = [...word];
    for (let suffLen = 3; suffLen >= 1; suffLen--) {
        if (runes.length > suffLen) {
            const stem = runes.slice(0, runes.length - suffLen).join('');
            if (HARD_K_STEMS.has(stem)) return true;
        }
    }
    return false;
}

function isHardG(word) {
    if (HARD_G_WORDS.has(word)) return true;
    // -era verb heuristic
    if (word.endsWith('era') || word.endsWith('erar') || word.endsWith('erade')) {
        return true;
    }
    const runes = [...word];
    for (let suffLen = 3; suffLen >= 1; suffLen--) {
        if (runes.length > suffLen) {
            const stem = runes.slice(0, runes.length - suffLen).join('');
            if (HARD_G_STEMS.has(stem)) return true;
        }
    }
    return false;
}

// ---------------------------------------------------------------------------
// Consonant conversion
// ---------------------------------------------------------------------------

/**
 * Convert consonant(s) starting at pos in runes.
 * @param {string[]} runes - Array of single characters.
 * @param {number} pos - Current position.
 * @param {string} fullWord - Complete word for exception lookup.
 * @returns {{ ipa: string[], consumed: number }}
 */
function convertConsonant(runes, pos, fullWord) {
    const n = runes.length;
    const remaining = n - pos;
    const ch = runes[pos];
    const nextCh = pos + 1 < n ? runes[pos + 1] : '';

    // === 3-char patterns ===
    if (remaining >= 3) {
        const tri = runes[pos] + runes[pos + 1] + runes[pos + 2];
        switch (tri) {
            case 'skj': return { ipa: ['\u0267'], consumed: 3 }; // ɧ
            case 'stj': return { ipa: ['\u0267'], consumed: 3 }; // ɧ
            case 'sch': return { ipa: ['\u0267'], consumed: 3 }; // ɧ
            case 'sng': return { ipa: ['s', 'n'], consumed: 3 };
            case 'ckj': return { ipa: ['\u0255'], consumed: 3 }; // ɕ
        }
    }

    // === 2-char patterns ===
    if (remaining >= 2) {
        const di = runes[pos] + runes[pos + 1];

        if (di === 'sk') {
            if (remaining >= 3 && FRONT_VOWELS.has(runes[pos + 2]) &&
                !SK_BACK_VOWEL_EXCEPTIONS.has(fullWord)) {
                return { ipa: ['\u0267'], consumed: 2 }; // ɧ
            }
            return { ipa: ['s', 'k'], consumed: 2 };
        }
        if (di === 'sj') return { ipa: ['\u0267'], consumed: 2 }; // ɧ
        if (di === 'sh') return { ipa: ['\u0267'], consumed: 2 }; // ɧ
        if (di === 'ch') {
            if (CH_EXCEPTIONS_K.has(fullWord)) return { ipa: ['k'], consumed: 2 };
            return { ipa: ['\u0267'], consumed: 2 }; // ɧ
        }
        if (di === 'ph') return { ipa: ['f'], consumed: 2 };
        if (di === 'th') return { ipa: ['t'], consumed: 2 };
        if (di === 'tj') return { ipa: ['\u0255'], consumed: 2 }; // ɕ
        if (di === 'kj') return { ipa: ['\u0255'], consumed: 2 }; // ɕ
        if (di === 'gn') {
            if (pos === 0) return { ipa: ['\u0261', 'n'], consumed: 2 }; // ɡn word-initial
            return { ipa: ['\u014b', 'n'], consumed: 2 }; // ŋn word-medial
        }
        if (di === 'ng') return { ipa: ['\u014b'], consumed: 2 }; // ŋ
        if (di === 'nk') return { ipa: ['\u014b', 'k'], consumed: 2 }; // ŋk
        if (di === 'ck') return { ipa: ['k'], consumed: 2 };
        // gj/lj/dj/hj: word-initial only
        if (di === 'gj' && pos === 0) return { ipa: ['j'], consumed: 2 };
        if (di === 'lj' && pos === 0) return { ipa: ['j'], consumed: 2 };
        if (di === 'dj' && pos === 0) return { ipa: ['j'], consumed: 2 };
        if (di === 'hj' && pos === 0) return { ipa: ['j'], consumed: 2 };
    }

    // === 1-char patterns ===

    // k + front vowel -> soft /ɕ/ or hard /k/
    if (ch === 'k' && FRONT_VOWELS.has(nextCh)) {
        if (isHardK(fullWord)) return { ipa: ['k'], consumed: 1 };
        return { ipa: ['\u0255'], consumed: 1 }; // ɕ
    }

    // g + front vowel -> soft /j/ or hard /ɡ/
    if (ch === 'g' && FRONT_VOWELS.has(nextCh)) {
        if (isHardG(fullWord)) return { ipa: ['\u0261'], consumed: 1 }; // ɡ
        return { ipa: ['j'], consumed: 1 };
    }

    // g + back vowel / consonant / word-final -> /ɡ/
    if (ch === 'g') return { ipa: ['\u0261'], consumed: 1 }; // ɡ

    // c before e/i -> /s/, otherwise /k/
    if (ch === 'c') {
        if (nextCh === 'e' || nextCh === 'i') return { ipa: ['s'], consumed: 1 };
        return { ipa: ['k'], consumed: 1 };
    }

    // x -> /ks/
    if (ch === 'x') return { ipa: ['k', 's'], consumed: 1 };

    // Default single consonant
    const ipa = CONSONANT_DEFAULT[ch];
    if (ipa !== undefined) {
        if (ipa.length > 1) {
            return { ipa: [...ipa], consumed: 1 };
        }
        return { ipa: [ipa], consumed: 1 };
    }

    return { ipa: [ch], consumed: 1 };
}

// ---------------------------------------------------------------------------
// Vowel length determination
// ---------------------------------------------------------------------------

function countFollowingConsonants(runes, pos) {
    let count = 0;
    let i = pos + 1;
    while (i < runes.length && CONSONANTS.has(runes[i])) {
        count++;
        i++;
    }
    return count;
}

function longVowel(ch, fullWord) {
    if (ch === 'o' && O_LONG_AS_OO.has(fullWord)) {
        return O_LONG_AS_OO_PHONEME;
    }
    return LONG_VOWEL_MAP[ch] || ch;
}

function getVowelPhoneme(runes, pos, fullWord, isStressed) {
    const ch = runes[pos];

    // 1. Unstressed -> short
    if (!isStressed) {
        return SHORT_VOWEL_MAP[ch] || ch;
    }

    // 2. Function word -> short
    if (FUNCTION_WORDS.has(fullWord)) {
        return SHORT_VOWEL_MAP[ch] || ch;
    }

    // 3. Final-m exception -> short
    if (FINAL_M_SHORT_WORDS.has(fullWord)) {
        return SHORT_VOWEL_MAP[ch] || ch;
    }

    // 4. Count following consonants
    const nFollowing = countFollowingConsonants(runes, pos);

    // 4a. Word-final vowel -> long
    if (nFollowing === 0 && pos === runes.length - 1) {
        return longVowel(ch, fullWord);
    }

    // 4b+4c. r + single C exception: vowel stays long (except 'o')
    if (nFollowing === 2 && ch !== 'o' && pos + 1 < runes.length && runes[pos + 1] === 'r') {
        return longVowel(ch, fullWord);
    }

    // 4d. Geminate / cluster (2+ consonants) -> short
    if (nFollowing >= 2) {
        return SHORT_VOWEL_MAP[ch] || ch;
    }

    // 4e. Single consonant -> long
    return longVowel(ch, fullWord);
}

// ---------------------------------------------------------------------------
// Word-level native G2P
// ---------------------------------------------------------------------------

function convertWordNative(word, fullWord, stressedSyl) {
    const runes = [...word];
    const n = runes.length;
    const phonemes = [];
    let pos = 0;
    let sylCount = 0;
    let prevWasVowel = false;

    while (pos < n) {
        const ch = runes[pos];

        if (ALL_VOWELS.has(ch)) {
            if (!prevWasVowel) {
                const isStressed = sylCount === stressedSyl && stressedSyl >= 0;
                const vowel = getVowelPhoneme(runes, pos, fullWord, isStressed);
                phonemes.push(vowel);
                sylCount++;
            } else {
                // Consecutive vowel: short
                phonemes.push(SHORT_VOWEL_MAP[ch] || ch);
            }
            prevWasVowel = true;
            pos++;
        } else if (CONSONANTS.has(ch)) {
            prevWasVowel = false;
            const { ipa, consumed } = convertConsonant(runes, pos, fullWord);
            phonemes.push(...ipa);
            pos += consumed;
        } else {
            prevWasVowel = false;
            pos++;
        }
    }

    return phonemes;
}

// ---------------------------------------------------------------------------
// Retroflex assimilation
// ---------------------------------------------------------------------------

const RETRO_NORMAL = 0;
const RETRO_R_DETECTED = 1;
const RETRO_CASCADING = 2;

function applyRetroflex(phonemes) {
    const result = [];
    let state = RETRO_NORMAL;

    for (const ph of phonemes) {
        switch (state) {
            case RETRO_NORMAL:
                if (ph === 'r') {
                    state = RETRO_R_DETECTED;
                } else {
                    result.push(ph);
                }
                break;

            case RETRO_R_DETECTED: {
                if (ph === 'r') {
                    // Geminate rr -> r + r, no assimilation
                    result.push('r', 'r');
                    state = RETRO_NORMAL;
                } else {
                    const retro = RETROFLEX_MAP[ph];
                    if (retro) {
                        result.push(retro);
                        state = PROPAGATING_RETROFLEXES.has(retro) ? RETRO_CASCADING : RETRO_NORMAL;
                    } else {
                        result.push('r', ph);
                        state = RETRO_NORMAL;
                    }
                }
                break;
            }

            case RETRO_CASCADING: {
                const retro = RETROFLEX_MAP[ph];
                if (retro) {
                    result.push(retro);
                    if (!PROPAGATING_RETROFLEXES.has(retro)) {
                        state = RETRO_NORMAL; // ɭ stops cascade
                    }
                } else {
                    result.push(ph);
                    state = RETRO_NORMAL;
                }
                break;
            }
        }
    }

    // Terminal flush: if r was pending, output it
    if (state === RETRO_R_DETECTED) {
        result.push('r');
    }

    return result;
}

// ---------------------------------------------------------------------------
// Stress detection
// ---------------------------------------------------------------------------

function detectStress(word) {
    // Priority 1: Function word -> no stress
    if (FUNCTION_WORDS.has(word)) return -1;

    // Priority 2: Monosyllabic
    const nSyl = countSyllables(word);
    if (nSyl <= 1) return 0;

    // Priority 3: Stress-attracting suffix (longest match first)
    for (const suffix of STRESS_ATTRACTING_SUFFIXES) {
        if (word.endsWith(suffix) && word.length > suffix.length) {
            const prefixPart = word.slice(0, word.length - suffix.length);
            return countSyllables(prefixPart);
        }
    }

    // Priority 4: Unstressed prefix
    for (const prefix of UNSTRESSED_PREFIXES) {
        if (word.startsWith(prefix) && word.length > prefix.length + 1) {
            return 1;
        }
    }

    // Priority 5: Default -- first syllable
    return 0;
}

// ---------------------------------------------------------------------------
// IPA vowel check (for stress marker insertion)
// ---------------------------------------------------------------------------

function isIPAVowel(ph) {
    for (const c of ph) {
        if (IPA_VOWEL_SET.has(c)) return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Stress marker insertion
// ---------------------------------------------------------------------------

function insertStressMarker(phonemes, stressSyl) {
    if (stressSyl < 0 || phonemes.length === 0) return phonemes;

    // Find the first vowel of the target syllable
    let sylCount = 0;
    let vowelIdx = -1;
    let prevWasVowel = false;

    for (let i = 0; i < phonemes.length; i++) {
        const isV = isIPAVowel(phonemes[i]);
        if (isV && !prevWasVowel) {
            if (sylCount === stressSyl) {
                vowelIdx = i;
                break;
            }
            sylCount++;
        }
        prevWasVowel = isV;
    }

    if (vowelIdx < 0) return phonemes;

    // Walk backwards to find syllable onset
    let onsetIdx = vowelIdx;
    while (onsetIdx > 0 && !isIPAVowel(phonemes[onsetIdx - 1])) {
        onsetIdx--;
    }

    // For syllable 0, onset starts at beginning
    if (stressSyl === 0) {
        onsetIdx = 0;
    }

    // Insert primary stress marker
    const result = [
        ...phonemes.slice(0, onsetIdx),
        '\u02c8', // ˈ
        ...phonemes.slice(onsetIdx),
    ];
    return result;
}

// ---------------------------------------------------------------------------
// Full word G2P pipeline
// ---------------------------------------------------------------------------

function phonemizeWord(word) {
    if (!word) return [];

    // Stress detection
    const stressedSyl = detectStress(word);

    // Loanword suffix check
    let rawPhonemes;
    const loan = detectLoanwordSuffix(word);
    if (loan.found) {
        const stemSylCount = countSyllables(loan.stem);
        const stemStress = stressedSyl >= stemSylCount ? -1 : stressedSyl;
        const stemPhonemes = convertWordNative(loan.stem, word, stemStress);
        rawPhonemes = [...stemPhonemes, ...loan.phonemes];
    } else {
        rawPhonemes = convertWordNative(word, word, stressedSyl);
    }

    // Retroflex assimilation
    let phonemes = applyRetroflex(rawPhonemes);

    // Stress marker insertion
    phonemes = insertStressMarker(phonemes, stressedSyl);

    return phonemes;
}

// ---------------------------------------------------------------------------
// SwedishG2P class
// ---------------------------------------------------------------------------

export class SwedishG2P {
    /**
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
        return 'sv';
    }

    /**
     * Convert Swedish text to phoneme tokens.
     *
     * @param {string} text - Input Swedish text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemize(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }

        const result = this._phonemizeInternal(text);
        return {
            tokens: result.tokens,
            prosody: new Array(result.tokens.length).fill(null),
        };
    }

    /**
     * Convert Swedish text to phoneme tokens with prosody information.
     *
     * SV prosody: A1=0, A2=stress_level (0 or 2), A3=word_phoneme_count.
     *
     * @param {string} text - Input Swedish text.
     * @returns {{ tokens: string[], prosody: ({ a1: number, a2: number, a3: number }|null)[] }}
     */
    phonemizeWithProsody(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }
        return this._phonemizeInternal(text);
    }

    /**
     * @private
     * Core phonemization with prosody generation.
     * @param {string} text
     * @returns {{ tokens: string[], prosody: ({ a1: number, a2: number, a3: number }|null)[] }}
     */
    _phonemizeInternal(text) {
        const normalized = svNormalize(text);
        const toks = svTokenize(normalized);

        const tokens = [];
        const prosody = [];
        let needSpace = false;

        for (const tk of toks) {
            if (tk.isPun) {
                for (const c of tk.text) {
                    tokens.push(c);
                    prosody.push({ a1: 0, a2: 0, a3: 0 });
                }
            } else {
                if (needSpace) {
                    tokens.push(' ');
                    prosody.push({ a1: 0, a2: 0, a3: 0 });
                }

                const wp = phonemizeWord(tk.text);

                // A3: count non-stress-marker phonemes
                let wordPhCount = 0;
                for (const ph of wp) {
                    if (ph !== '\u02c8' && ph !== '\u02cc') {
                        wordPhCount++;
                    }
                }

                for (const ph of wp) {
                    let a2 = 0;
                    if (ph === '\u02c8') {
                        a2 = 2; // primary stress
                    }
                    tokens.push(ph);
                    prosody.push({ a1: 0, a2, a3: wordPhCount });
                }

                needSpace = true;
            }
        }

        return { tokens, prosody };
    }
}
