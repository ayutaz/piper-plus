/**
 * PUA (Private Use Area) mapping table.
 *
 * Canonical source: src/python/g2p/piper_plus_g2p/data/pua.json (99 entries)
 *
 * Multi-character phoneme tokens are mapped to single Unicode PUA codepoints
 * (U+E000..U+E064) so that the model's phoneme_id_map can look them up as
 * single characters.
 *
 * @module pua-map
 */

/**
 * PUA compatibility version. Increment when new PUA mappings are added.
 * @type {number}
 */
export const PUA_COMPAT_VERSION = 2;

/**
 * Check if a model's PUA version is compatible.
 * @param {number|undefined|null} modelVersion
 * @returns {{ compatible: boolean, message?: string }}
 */
export function checkPuaCompat(modelVersion) {
    if (modelVersion === undefined || modelVersion === null) {
        return { compatible: true };
    }
    if (modelVersion === PUA_COMPAT_VERSION) {
        return { compatible: true };
    }
    return {
        compatible: false,
        message: `PUA version mismatch: model has pua_compat_version=${modelVersion}, ` +
            `but @piper-plus/g2p expects version ${PUA_COMPAT_VERSION}. ` +
            `Some phoneme tokens may not encode correctly.`,
    };
}

/**
 * Forward mapping: multi-char token -> PUA character (99 entries).
 * @type {Record<string, string>}
 */
export const PUA_MAP = {
    // --- Japanese (ja) ---
    'a:':       '\uE000',  // Long vowel a
    'i:':       '\uE001',  // Long vowel i
    'u:':       '\uE002',  // Long vowel u
    'e:':       '\uE003',  // Long vowel e
    'o:':       '\uE004',  // Long vowel o
    'cl':       '\uE005',  // Geminate consonant (sokuon)
    'ky':       '\uE006',  // Palatalized velar stop k
    'kw':       '\uE007',  // Labialized velar stop k
    'gy':       '\uE008',  // Palatalized voiced velar stop g
    'gw':       '\uE009',  // Labialized voiced velar stop g
    'ty':       '\uE00A',  // Palatalized alveolar stop t
    'dy':       '\uE00B',  // Palatalized voiced alveolar stop d
    'py':       '\uE00C',  // Palatalized bilabial stop p
    'by':       '\uE00D',  // Palatalized voiced bilabial stop b
    'ch':       '\uE00E',  // Voiceless postalveolar affricate
    'ts':       '\uE00F',  // Voiceless alveolar affricate
    'sh':       '\uE010',  // Voiceless postalveolar fricative
    'zy':       '\uE011',  // Palatalized voiced alveolar fricative
    'hy':       '\uE012',  // Palatalized glottal fricative
    'ny':       '\uE013',  // Palatalized alveolar nasal
    'my':       '\uE014',  // Palatalized bilabial nasal
    'ry':       '\uE015',  // Palatalized alveolar lateral
    '?!':       '\uE016',  // Emphatic question marker
    '?.':       '\uE017',  // Neutral/rhetorical question marker
    '?~':       '\uE018',  // Tag question marker
    'N_m':      '\uE019',  // Moraic nasal before bilabial
    'N_n':      '\uE01A',  // Moraic nasal before alveolar
    'N_ng':     '\uE01B',  // Moraic nasal before velar
    'N_uvular': '\uE01C',  // Moraic nasal uvular (word-final/pre-vocalic)

    // --- Shared ---
    'rr':       '\uE01D',  // Alveolar trill (Spanish rr)
    'y_vowel':  '\uE01E',  // Close front rounded vowel [y]

    // --- Chinese (zh) ---
    'p\u02B0':          '\uE020',  // Aspirated bilabial stop
    't\u02B0':          '\uE021',  // Aspirated alveolar stop
    'k\u02B0':          '\uE022',  // Aspirated velar stop
    't\u0255':          '\uE023',  // Alveolo-palatal affricate
    't\u0255\u02B0':    '\uE024',  // Aspirated alveolo-palatal affricate
    't\u0282':          '\uE025',  // Retroflex affricate
    't\u0282\u02B0':    '\uE026',  // Aspirated retroflex affricate
    'ts\u02B0':         '\uE027',  // Aspirated alveolar affricate
    'a\u026A':          '\uE028',  // Diphthong ai
    'e\u026A':          '\uE029',  // Diphthong ei
    'a\u028A':          '\uE02A',  // Diphthong ao
    'o\u028A':          '\uE02B',  // Diphthong ou
    'an':               '\uE02C',  // Nasal final an
    '\u0259n':          '\uE02D',  // Nasal final en
    'a\u014B':          '\uE02E',  // Nasal final ang
    '\u0259\u014B':     '\uE02F',  // Nasal final eng
    'u\u014B':          '\uE030',  // Nasal final ong
    'ia':               '\uE031',  // Compound final ia
    'i\u025B':          '\uE032',  // Compound final ie
    'iou':              '\uE033',  // Compound final iou
    'ia\u028A':         '\uE034',  // Compound final iao
    'i\u025Bn':         '\uE035',  // Compound final ian
    'in':               '\uE036',  // Compound final in
    'ia\u014B':         '\uE037',  // Compound final iang
    'i\u014B':          '\uE038',  // Compound final ing
    'iu\u014B':         '\uE039',  // Compound final iong
    'ua':               '\uE03A',  // Compound final ua
    'uo':               '\uE03B',  // Compound final uo
    'ua\u026A':         '\uE03C',  // Compound final uai
    'ue\u026A':         '\uE03D',  // Compound final uei
    'uan':              '\uE03E',  // Compound final uan
    'u\u0259n':         '\uE03F',  // Compound final uen
    'ua\u014B':         '\uE040',  // Compound final uang
    'u\u0259\u014B':    '\uE041',  // Compound final ueng
    'y\u025B':          '\uE042',  // Compound final ye
    'y\u025Bn':         '\uE043',  // Compound final yuan
    'yn':               '\uE044',  // Compound final yn
    '\u027B\u0329':     '\uE045',  // Syllabic retroflex approximant
    'tone1':            '\uE046',  // Tone 1 (high level)
    'tone2':            '\uE047',  // Tone 2 (rising)
    'tone3':            '\uE048',  // Tone 3 (dipping)
    'tone4':            '\uE049',  // Tone 4 (falling)
    'tone5':            '\uE04A',  // Tone 5 (neutral)

    // --- Korean (ko) ---
    'p\u0348':          '\uE04B',  // Tense bilabial stop
    't\u0348':          '\uE04C',  // Tense alveolar stop
    'k\u0348':          '\uE04D',  // Tense velar stop
    's\u0348':          '\uE04E',  // Tense sibilant fricative
    't\u0348\u0255':    '\uE04F',  // Tense alveolo-palatal affricate
    'k\u031A':          '\uE050',  // Unreleased velar stop
    't\u031A':          '\uE051',  // Unreleased alveolar stop
    'p\u031A':          '\uE052',  // Unreleased bilabial stop

    // --- Spanish (es) ---
    't\u0283':          '\uE054',  // Voiceless postalveolar affricate
    'd\u0292':          '\uE055',  // Voiced postalveolar affricate

    // --- French (fr) ---
    '\u025B\u0303':     '\uE056',  // Nasal open-mid front unrounded vowel
    '\u0251\u0303':     '\uE057',  // Nasal open back unrounded vowel
    '\u0254\u0303':     '\uE058',  // Nasal open-mid back rounded vowel

    // --- Swedish (sv) --- 9 entries (long vowels)
    'i\u02D0':          '\uE059',  // iː  Long close front unrounded vowel
    'y\u02D0':          '\uE05A',  // yː  Long close front rounded vowel
    'e\u02D0':          '\uE05B',  // eː  Long close-mid front unrounded vowel
    '\u025B\u02D0':     '\uE05C',  // ɛː  Long open-mid front unrounded vowel
    '\u00F8\u02D0':     '\uE05D',  // øː  Long close-mid front rounded vowel
    '\u0251\u02D0':     '\uE05E',  // ɑː  Long open back unrounded vowel
    'o\u02D0':          '\uE05F',  // oː  Long close-mid back rounded vowel
    'u\u02D0':          '\uE060',  // uː  Long close back rounded vowel
    '\u0289\u02D0':     '\uE061',  // ʉː  Long close central rounded vowel

    // --- Additional multi-codepoint diphthongs / nasal vowels (PUA v2) --- 3 entries
    '\u0254\u026A':     '\uE062',  // ɔɪ  English diphthong (OY)
    '\u0153\u0303':     '\uE063',  // œ̃ French nasal open-mid front rounded vowel
    '\u0250\u0303':     '\uE064',  // ɐ̃ Portuguese nasal near-open central vowel
};

/**
 * Reverse mapping: PUA character -> original multi-char token.
 * Built automatically from PUA_MAP.
 * @type {Record<string, string>}
 */
const REVERSE_PUA_MAP = Object.create(null);
for (const [token, puaChar] of Object.entries(PUA_MAP)) {
    REVERSE_PUA_MAP[puaChar] = token;
}

/**
 * Map a multi-character token to its PUA single character.
 * Returns the token unchanged if no mapping exists.
 *
 * @param {string} token - A phoneme token (e.g. "ch", "N_m", "tone1")
 * @returns {string} The PUA character, or the original token if unmapped
 */
export function mapToken(token) {
    return PUA_MAP[token] ?? token;
}

/**
 * Map a PUA single character back to its original multi-character token.
 * Returns the character unchanged if no reverse mapping exists.
 *
 * @param {string} puaChar - A PUA character (e.g. "\uE00E")
 * @returns {string} The original token (e.g. "ch"), or the character if unmapped
 */
export function unmapToken(puaChar) {
    return REVERSE_PUA_MAP[puaChar] ?? puaChar;
}
