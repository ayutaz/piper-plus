/**
 * @piper-plus/g2p - English G2P module
 *
 * Lightweight English grapheme-to-phoneme conversion.
 * Ported from SimpleEnglishPhonemizer (piper-plus npm package).
 *
 * Uses a built-in pronunciation dictionary (common words) with
 * letter-by-letter fallback for unknown words, then converts to IPA tokens.
 *
 * Pure JavaScript -- no external dependencies.
 */

// ---------------------------------------------------------------------------
// ARPAbet -> IPA mapping (matches Python english.py ARPABET_TO_IPA)
// ---------------------------------------------------------------------------

const ARPABET_TO_IPA = {
    'AA': '\u0251',     // ɑ
    'AE': '\u00e6',     // æ
    'AH': '\u028c',     // ʌ
    'AO': '\u0254\u02d0', // ɔː
    'AW': 'a\u028a',    // aʊ
    'AY': 'a\u026a',    // aɪ
    'B':  'b',
    'CH': 't\u0283',    // tʃ
    'D':  'd',
    'DH': '\u00f0',     // ð
    'EH': '\u025b',     // ɛ
    'ER': '\u025a',     // ɚ  (unstressed default; stressed -> ɜː)
    'EY': 'e\u026a',    // eɪ
    'F':  'f',
    'G':  '\u0261',     // ɡ
    'HH': 'h',
    'IH': '\u026a',     // ɪ
    'IY': 'i\u02d0',    // iː
    'JH': 'd\u0292',    // dʒ
    'K':  'k',
    'L':  'l',
    'M':  'm',
    'N':  'n',
    'NG': '\u014b',     // ŋ
    'OW': 'o\u028a',    // oʊ
    'OY': '\u0254\u026a', // ɔɪ
    'P':  'p',
    'R':  '\u0279',     // ɹ
    'S':  's',
    'SH': '\u0283',     // ʃ
    'T':  't',
    'TH': '\u03b8',     // θ
    'UH': '\u028a',     // ʊ
    'UW': 'u\u02d0',    // uː
    'V':  'v',
    'W':  'w',
    'Y':  'j',
    'Z':  'z',
    'ZH': '\u0292',     // ʒ
};

// Unstressed AH -> schwa
const AH_UNSTRESSED_IPA = '\u0259'; // ə

// Regex to split ARPAbet token: base letters + optional stress digit
const RE_ARPABET = /^([A-Z]+)(\d)?$/;

// Punctuation characters
const PUNCTUATION = new Set([',', '.', ';', ':', '!', '?']);

// ---------------------------------------------------------------------------
// Function words -- stress is removed to match espeak-ng behavior.
// ---------------------------------------------------------------------------

const FUNCTION_WORDS = new Set([
    // articles / determiners
    'a', 'an', 'the',
    // pronouns
    'i', 'me', 'my', 'mine', 'myself',
    'you', 'your', 'yours', 'yourself',
    'he', 'him', 'his', 'himself',
    'she', 'her', 'hers', 'herself',
    'it', 'its', 'itself',
    'we', 'us', 'our', 'ours', 'ourselves',
    'they', 'them', 'their', 'theirs', 'themselves',
    // be-verbs
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    // auxiliaries
    'have', 'has', 'had', 'having',
    'do', 'does', 'did',
    'will', 'would', 'shall', 'should',
    'can', 'could', 'may', 'might', 'must',
    // prepositions
    'at', 'by', 'for', 'from', 'in', 'of', 'on', 'to', 'with',
    'about', 'after', 'before', 'between', 'into', 'through', 'under',
    // conjunctions
    'and', 'but', 'or', 'nor', 'so', 'yet', 'if',
    'that', 'than', 'when', 'while', 'as', 'because', 'since',
    // others
    'not', 'no',
]);

// ---------------------------------------------------------------------------
// Built-in pronunciation dictionary (common words -> ARPAbet)
//
// Entries use CMU-dict style notation: uppercase base + stress digit on vowels.
// This provides better quality than pure letter rules for frequent words.
// ---------------------------------------------------------------------------

const DICTIONARY = {
    // Common words
    'hello':        ['HH', 'AH0', 'L', 'OW1'],
    'world':        ['W', 'ER1', 'L', 'D'],
    'the':          ['DH', 'AH0'],
    'a':            ['AH0'],
    'an':           ['AE1', 'N'],
    'and':          ['AE1', 'N', 'D'],
    'is':           ['IH1', 'Z'],
    'are':          ['AA1', 'R'],
    'was':          ['W', 'AA1', 'Z'],
    'were':         ['W', 'ER1'],
    'been':         ['B', 'IH1', 'N'],
    'have':         ['HH', 'AE1', 'V'],
    'has':          ['HH', 'AE1', 'Z'],
    'had':          ['HH', 'AE1', 'D'],
    'do':           ['D', 'UW1'],
    'does':         ['D', 'AH1', 'Z'],
    'did':          ['D', 'IH1', 'D'],
    'will':         ['W', 'IH1', 'L'],
    'would':        ['W', 'UH1', 'D'],
    'can':          ['K', 'AE1', 'N'],
    'could':        ['K', 'UH1', 'D'],
    'should':       ['SH', 'UH1', 'D'],
    'may':          ['M', 'EY1'],
    'might':        ['M', 'AY1', 'T'],
    'must':         ['M', 'AH1', 'S', 'T'],
    'to':           ['T', 'UW1'],
    'of':           ['AH1', 'V'],
    'in':           ['IH1', 'N'],
    'on':           ['AA1', 'N'],
    'at':           ['AE1', 'T'],
    'by':           ['B', 'AY1'],
    'for':          ['F', 'AO1', 'R'],
    'with':         ['W', 'IH1', 'TH'],
    'from':         ['F', 'R', 'AH1', 'M'],
    'up':           ['AH1', 'P'],
    'out':          ['AW1', 'T'],
    'over':         ['OW1', 'V', 'ER0'],
    'under':        ['AH1', 'N', 'D', 'ER0'],
    'not':          ['N', 'AA1', 'T'],
    'all':          ['AO1', 'L'],
    'one':          ['W', 'AH1', 'N'],
    'two':          ['T', 'UW1'],
    'three':        ['TH', 'R', 'IY1'],
    'four':         ['F', 'AO1', 'R'],
    'five':         ['F', 'AY1', 'V'],
    'good':         ['G', 'UH1', 'D'],
    'bad':          ['B', 'AE1', 'D'],
    'new':          ['N', 'UW1'],
    'old':          ['OW1', 'L', 'D'],
    'big':          ['B', 'IH1', 'G'],
    'small':        ['S', 'M', 'AO1', 'L'],
    'this':         ['DH', 'IH1', 'S'],
    'that':         ['DH', 'AE1', 'T'],
    'these':        ['DH', 'IY1', 'Z'],
    'those':        ['DH', 'OW1', 'Z'],
    'what':         ['W', 'AH1', 'T'],
    'when':         ['W', 'EH1', 'N'],
    'where':        ['W', 'EH1', 'R'],
    'which':        ['W', 'IH1', 'CH'],
    'who':          ['HH', 'UW1'],
    'how':          ['HH', 'AW1'],
    'if':           ['IH1', 'F'],
    'then':         ['DH', 'EH1', 'N'],
    'than':         ['DH', 'AE1', 'N'],
    'so':           ['S', 'OW1'],
    'no':           ['N', 'OW1'],
    'yes':          ['Y', 'EH1', 'S'],
    'or':           ['AO1', 'R'],
    'but':          ['B', 'AH1', 'T'],
    'just':         ['JH', 'AH1', 'S', 'T'],
    'also':         ['AO1', 'L', 'S', 'OW0'],
    'very':         ['V', 'EH1', 'R', 'IY0'],
    'much':         ['M', 'AH1', 'CH'],
    'more':         ['M', 'AO1', 'R'],
    'most':         ['M', 'OW1', 'S', 'T'],
    'other':        ['AH1', 'DH', 'ER0'],
    'some':         ['S', 'AH1', 'M'],
    'any':          ['EH1', 'N', 'IY0'],
    'each':         ['IY1', 'CH'],
    'every':        ['EH1', 'V', 'ER0', 'IY0'],
    'many':         ['M', 'EH1', 'N', 'IY0'],
    'few':          ['F', 'Y', 'UW1'],
    'about':        ['AH0', 'B', 'AW1', 'T'],
    'after':        ['AE1', 'F', 'T', 'ER0'],
    'before':       ['B', 'IH0', 'F', 'AO1', 'R'],
    'between':      ['B', 'IH0', 'T', 'W', 'IY1', 'N'],
    'into':         ['IH1', 'N', 'T', 'UW0'],
    'through':      ['TH', 'R', 'UW1'],
    'because':      ['B', 'IH0', 'K', 'AH1', 'Z'],
    'since':        ['S', 'IH1', 'N', 'S'],
    'while':        ['W', 'AY1', 'L'],
    'only':         ['OW1', 'N', 'L', 'IY0'],
    'still':        ['S', 'T', 'IH1', 'L'],
    'even':         ['IY1', 'V', 'AH0', 'N'],
    'back':         ['B', 'AE1', 'K'],
    'now':          ['N', 'AW1'],
    'here':         ['HH', 'IY1', 'R'],
    'there':        ['DH', 'EH1', 'R'],

    // Common verbs
    'go':           ['G', 'OW1'],
    'going':        ['G', 'OW1', 'IH0', 'NG'],
    'come':         ['K', 'AH1', 'M'],
    'get':          ['G', 'EH1', 'T'],
    'make':         ['M', 'EY1', 'K'],
    'know':         ['N', 'OW1'],
    'think':        ['TH', 'IH1', 'NG', 'K'],
    'take':         ['T', 'EY1', 'K'],
    'see':          ['S', 'IY1'],
    'say':          ['S', 'EY1'],
    'said':         ['S', 'EH1', 'D'],
    'give':         ['G', 'IH1', 'V'],
    'use':          ['Y', 'UW1', 'Z'],
    'find':         ['F', 'AY1', 'N', 'D'],
    'tell':         ['T', 'EH1', 'L'],
    'ask':          ['AE1', 'S', 'K'],
    'work':         ['W', 'ER1', 'K'],
    'call':         ['K', 'AO1', 'L'],
    'try':          ['T', 'R', 'AY1'],
    'need':         ['N', 'IY1', 'D'],
    'feel':         ['F', 'IY1', 'L'],
    'keep':         ['K', 'IY1', 'P'],
    'let':          ['L', 'EH1', 'T'],
    'begin':        ['B', 'IH0', 'G', 'IH1', 'N'],
    'seem':         ['S', 'IY1', 'M'],
    'help':         ['HH', 'EH1', 'L', 'P'],
    'show':         ['SH', 'OW1'],
    'hear':         ['HH', 'IY1', 'R'],
    'play':         ['P', 'L', 'EY1'],
    'run':          ['R', 'AH1', 'N'],
    'move':         ['M', 'UW1', 'V'],
    'like':         ['L', 'AY1', 'K'],
    'live':         ['L', 'IH1', 'V'],
    'want':         ['W', 'AA1', 'N', 'T'],
    'look':         ['L', 'UH1', 'K'],
    'put':          ['P', 'UH1', 'T'],
    'read':         ['R', 'IY1', 'D'],
    'write':        ['R', 'AY1', 'T'],
    'open':         ['OW1', 'P', 'AH0', 'N'],
    'close':        ['K', 'L', 'OW1', 'Z'],
    'stop':         ['S', 'T', 'AA1', 'P'],
    'start':        ['S', 'T', 'AA1', 'R', 'T'],

    // Common nouns
    'people':       ['P', 'IY1', 'P', 'AH0', 'L'],
    'time':         ['T', 'AY1', 'M'],
    'year':         ['Y', 'IY1', 'R'],
    'way':          ['W', 'EY1'],
    'day':          ['D', 'EY1'],
    'man':          ['M', 'AE1', 'N'],
    'woman':        ['W', 'UH1', 'M', 'AH0', 'N'],
    'child':        ['CH', 'AY1', 'L', 'D'],
    'part':         ['P', 'AA1', 'R', 'T'],
    'place':        ['P', 'L', 'EY1', 'S'],
    'case':         ['K', 'EY1', 'S'],
    'week':         ['W', 'IY1', 'K'],
    'hand':         ['HH', 'AE1', 'N', 'D'],
    'point':        ['P', 'OY1', 'N', 'T'],
    'home':         ['HH', 'OW1', 'M'],
    'water':        ['W', 'AO1', 'T', 'ER0'],
    'room':         ['R', 'UW1', 'M'],
    'name':         ['N', 'EY1', 'M'],
    'school':       ['S', 'K', 'UW1', 'L'],
    'life':         ['L', 'AY1', 'F'],

    // Tech terms
    'text':         ['T', 'EH1', 'K', 'S', 'T'],
    'speech':       ['S', 'P', 'IY1', 'CH'],
    'voice':        ['V', 'OY1', 'S'],
    'audio':        ['AO1', 'D', 'IY0', 'OW0'],
    'system':       ['S', 'IH1', 'S', 'T', 'AH0', 'M'],
    'computer':     ['K', 'AH0', 'M', 'P', 'Y', 'UW1', 'T', 'ER0'],
    'artificial':   ['AA1', 'R', 'T', 'AH0', 'F', 'IH1', 'SH', 'AH0', 'L'],
    'intelligence': ['IH0', 'N', 'T', 'EH1', 'L', 'AH0', 'JH', 'AH0', 'N', 'S'],
    'technology':   ['T', 'EH0', 'K', 'N', 'AA1', 'L', 'AH0', 'JH', 'IY0'],
    'synthesis':    ['S', 'IH1', 'N', 'TH', 'AH0', 'S', 'IH0', 'S'],
    'model':        ['M', 'AA1', 'D', 'AH0', 'L'],
    'data':         ['D', 'EY1', 'T', 'AH0'],
    'language':     ['L', 'AE1', 'NG', 'G', 'W', 'AH0', 'JH'],
    'english':      ['IH1', 'NG', 'G', 'L', 'IH0', 'SH'],
    'japanese':     ['JH', 'AE2', 'P', 'AH0', 'N', 'IY1', 'Z'],
    'chinese':      ['CH', 'AY0', 'N', 'IY1', 'Z'],
    'today':        ['T', 'AH0', 'D', 'EY1'],
    'test':         ['T', 'EH1', 'S', 'T'],
    'please':       ['P', 'L', 'IY1', 'Z'],
    'thank':        ['TH', 'AE1', 'NG', 'K'],
    'thanks':       ['TH', 'AE1', 'NG', 'K', 'S'],
    'right':        ['R', 'AY1', 'T'],
    'left':         ['L', 'EH1', 'F', 'T'],
    'first':        ['F', 'ER1', 'S', 'T'],
    'last':         ['L', 'AE1', 'S', 'T'],
    'long':         ['L', 'AO1', 'NG'],
    'great':        ['G', 'R', 'EY1', 'T'],
    'little':       ['L', 'IH1', 'T', 'AH0', 'L'],
    'own':          ['OW1', 'N'],
    'well':         ['W', 'EH1', 'L'],
    'really':       ['R', 'IY1', 'L', 'IY0'],
    'always':       ['AO1', 'L', 'W', 'EY0', 'Z'],
    'never':        ['N', 'EH1', 'V', 'ER0'],
    'again':        ['AH0', 'G', 'EH1', 'N'],
    'down':         ['D', 'AW1', 'N'],
    'away':         ['AH0', 'W', 'EY1'],
    'together':     ['T', 'AH0', 'G', 'EH1', 'DH', 'ER0'],
    'without':      ['W', 'IH0', 'DH', 'AW1', 'T'],
    'however':      ['HH', 'AW0', 'EH1', 'V', 'ER0'],
    'something':    ['S', 'AH1', 'M', 'TH', 'IH0', 'NG'],
    'nothing':      ['N', 'AH1', 'TH', 'IH0', 'NG'],
    'everything':   ['EH1', 'V', 'R', 'IY0', 'TH', 'IH0', 'NG'],
};

// ---------------------------------------------------------------------------
// Letter-to-ARPAbet fallback rules
//
// Used for unknown words. Maps single letters to ARPAbet tokens.
// Digraph patterns are checked first for better accuracy.
// ---------------------------------------------------------------------------

const DIGRAPH_RULES = [
    ['th', ['TH']],
    ['sh', ['SH']],
    ['ch', ['CH']],
    ['ph', ['F']],
    ['wh', ['W']],
    ['ck', ['K']],
    ['ng', ['NG']],
    ['qu', ['K', 'W']],
    ['oo', ['UW1']],
    ['ee', ['IY1']],
    ['ea', ['IY1']],
    ['ai', ['EY1']],
    ['ay', ['EY1']],
    ['oi', ['OY1']],
    ['oy', ['OY1']],
    ['ou', ['AW1']],
    ['ow', ['OW1']],
    ['aw', ['AO1']],
    ['au', ['AO1']],
    ['igh', ['AY1']],
];

const LETTER_RULES = {
    'a': ['AE1'], 'b': ['B'],  'c': ['K'],  'd': ['D'],
    'e': ['EH1'], 'f': ['F'],  'g': ['G'],  'h': ['HH'],
    'i': ['IH1'], 'j': ['JH'], 'k': ['K'],  'l': ['L'],
    'm': ['M'],   'n': ['N'],  'o': ['AA1'], 'p': ['P'],
    'q': ['K'],   'r': ['R'],  's': ['S'],   't': ['T'],
    'u': ['AH1'], 'v': ['V'],  'w': ['W'],   'x': ['K', 'S'],
    'y': ['Y'],   'z': ['Z'],
};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Convert a single ARPAbet token to (ipaString, stressLevel).
 * stress: 0 = unstressed vowel, 1 = primary, 2 = secondary, -1 = consonant.
 */
function arpabetToIpa(token) {
    const m = RE_ARPABET.exec(token);
    if (!m) {
        // Punctuation or unknown -- return as-is
        return [token, -1];
    }
    const base = m[1];
    const stress = m[2] !== undefined ? parseInt(m[2], 10) : -1;

    // Unstressed AH -> schwa
    if (base === 'AH' && stress === 0) {
        return [AH_UNSTRESSED_IPA, stress];
    }

    const ipa = ARPABET_TO_IPA[base];
    if (ipa === undefined) {
        return [token, stress];
    }
    return [ipa, stress];
}

/**
 * Convert a word's ARPAbet tokens to IPA with context-dependent rules.
 *   AA + R -> ɑːɹ
 *   ER with stress=1 -> ɜː
 */
function convertWordToIpa(tokens) {
    const result = [];
    let i = 0;
    while (i < tokens.length) {
        const token = tokens[i];
        const m = RE_ARPABET.exec(token);
        if (m) {
            const base = m[1];
            const stress = m[2] !== undefined ? parseInt(m[2], 10) : -1;

            // AA + R -> ɑːɹ
            if (base === 'AA' && i + 1 < tokens.length && tokens[i + 1] === 'R') {
                result.push(['\u0251\u02d0\u0279', stress]); // ɑːɹ
                i += 2;
                continue;
            }

            // Stressed ER -> ɜː
            if (base === 'ER' && stress === 1) {
                result.push(['\u025c\u02d0', stress]); // ɜː
                i += 1;
                continue;
            }
        }

        const [ipa, stress] = arpabetToIpa(token);
        result.push([ipa, stress]);
        i += 1;
    }
    return result;
}

/**
 * Check whether a word (ARPAbet token list) is punctuation only.
 */
function isPunctuationWord(tokens) {
    return tokens.every(t => PUNCTUATION.has(t));
}

/**
 * Extract source (alphabetic) words from text for function-word matching.
 */
function getSourceWords(text) {
    const matches = text.toLowerCase().match(/[a-z']+/g);
    return matches || [];
}

/**
 * Convert a cleaned word into ARPAbet tokens using dictionary + fallback.
 */
function wordToArpabet(word) {
    const entry = DICTIONARY[word];
    if (entry) {
        return entry;
    }
    // Fallback: digraph then letter rules
    const tokens = [];
    let i = 0;
    while (i < word.length) {
        let matched = false;
        // Try trigraphs / digraphs first (longest match)
        for (const [pattern, arpa] of DIGRAPH_RULES) {
            if (word.substring(i, i + pattern.length) === pattern) {
                tokens.push(...arpa);
                i += pattern.length;
                matched = true;
                break;
            }
        }
        if (!matched) {
            const letter = word[i];
            const arpa = LETTER_RULES[letter];
            if (arpa) {
                tokens.push(...arpa);
            }
            i += 1;
        }
    }
    return tokens;
}

/**
 * Tokenize text into word groups (ARPAbet token arrays).
 * Punctuation characters form their own groups.
 */
function textToArpabetWords(text) {
    const rawWords = text.toLowerCase().split(/\s+/);
    const words = [];

    for (const raw of rawWords) {
        if (!raw) continue;
        // Separate trailing/leading punctuation from the word
        let word = raw;
        const trailingPunct = [];

        // Strip trailing punctuation
        while (word.length > 0 && PUNCTUATION.has(word[word.length - 1])) {
            trailingPunct.unshift(word[word.length - 1]);
            word = word.slice(0, -1);
        }

        // Strip leading punctuation (rare but possible)
        const leadingPunct = [];
        while (word.length > 0 && PUNCTUATION.has(word[0])) {
            leadingPunct.push(word[0]);
            word = word.slice(1);
        }

        for (const p of leadingPunct) {
            words.push([p]);
        }

        if (word.length > 0) {
            // Remove non-alpha characters (except apostrophe in contractions)
            const cleanWord = word.replace(/[^a-z']/g, '');
            if (cleanWord.length > 0) {
                words.push(wordToArpabet(cleanWord));
            }
        }

        for (const p of trailingPunct) {
            words.push([p]);
        }
    }

    return words;
}

// ---------------------------------------------------------------------------
// EnglishG2P class
// ---------------------------------------------------------------------------

export class EnglishG2P {
    /**
     * Create an EnglishG2P instance.
     *
     * @param {Object} [options={}] - Reserved for future options.
     */
    constructor(options = {}) {
        // Reserved for future options (e.g. custom dictionary additions)
        this._options = options;
    }

    /**
     * Convert English text to IPA tokens.
     *
     * Processing flow:
     *   1. Lowercase the text
     *   2. Look up each word in the built-in dictionary (CMU-dict style)
     *   3. Fall back to digraph / letter rules for unknown words
     *   4. Convert ARPAbet tokens to IPA
     *   5. Apply function-word stress removal
     *   6. Insert stress markers (ˈ / ˌ) before stressed vowels
     *   7. Return flat IPA token array with word-boundary spaces
     *
     * @param {string} text - Input English text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemize(text) {
        if (!text || typeof text !== 'string') {
            return { tokens: [], prosody: [] };
        }

        const words = textToArpabetWords(text);
        const sourceWords = getSourceWords(text);

        const tokens = [];

        // Build function-word flags
        let srcIdx = 0;
        const wordIsFunction = [];
        for (const wordTokens of words) {
            if (isPunctuationWord(wordTokens)) {
                wordIsFunction.push(false);
            } else {
                let isFunc = false;
                if (srcIdx < sourceWords.length) {
                    isFunc = FUNCTION_WORDS.has(sourceWords[srcIdx]);
                    srcIdx += 1;
                }
                wordIsFunction.push(isFunc);
            }
        }

        let needSpace = false;

        for (let wordIdx = 0; wordIdx < words.length; wordIdx++) {
            const wordTokens = words[wordIdx];
            const isPunct = isPunctuationWord(wordTokens);
            const isFunc = wordIsFunction[wordIdx];

            // Word boundary: space before non-punctuation words (except first)
            if (!isPunct && needSpace) {
                tokens.push(' ');
            }

            // Convert ARPAbet -> IPA with context rules
            let wordIpas = convertWordToIpa(wordTokens);

            // Remove stress from function words
            if (isFunc) {
                wordIpas = wordIpas.map(([ipa, stress]) => [
                    ipa,
                    stress >= 1 ? 0 : stress,
                ]);
            }

            for (const [ipa, stress] of wordIpas) {
                // Insert stress marker before stressed vowels
                if (stress === 1) {
                    tokens.push('\u02c8'); // ˈ primary stress
                } else if (stress === 2) {
                    tokens.push('\u02cc'); // ˌ secondary stress
                }

                // Each IPA character becomes a separate token
                for (const ch of ipa) {
                    tokens.push(ch);
                }
            }

            needSpace = true;
        }

        return {
            tokens,
            prosody: new Array(tokens.length).fill(null),
        };
    }

    /**
     * Convert English text to IPA tokens with prosody information.
     *
     * English does not have prosody features (A1/A2/A3) like Japanese,
     * so this returns the same result as phonemize() -- prosody is always
     * a null array matching the token length.
     *
     * @param {string} text - Input English text.
     * @returns {{ tokens: string[], prosody: null[] }}
     */
    phonemizeWithProsody(text) {
        const { tokens } = this.phonemize(text);
        const prosody = tokens.map(() => ({ a1: 0, a2: 0, a3: 0 }));
        return { tokens, prosody };
    }
}
