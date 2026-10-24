/**
 * @piper-plus/g2p - English G2P module
 *
 * English grapheme-to-phoneme conversion that follows Python's training-time
 * G2P (g2p_en + english.py) the way the Rust port does
 * (`src/rust/piper-plus-g2p/src/english.rs`):
 *
 *   1. normalize and tokenize the text like g2p_en (numbers spelled out,
 *      accents stripped, `i.e.` / `e.g.` expanded, nltk's TweetTokenizer);
 *      see `./normalize.js`
 *   2. look each word up in the bundled CMU Pronouncing Dictionary
 *      (`data/cmudict_data.json`, loaded on demand; see `./cmudict.js`), then
 *      try common suffixes (-ing, -ed, -s, -er, -ly, -est) on its stem
 *   3. read the remaining words without g2p_en's neural guesser, which is not
 *      ported: split them at `-` / `.`, retry without apostrophes, split at
 *      CamelCase boundaries and finally spell them letter by letter, so no
 *      word is dropped
 *   4. convert ARPAbet to IPA with Python's context rules, remove the stress
 *      of function words and put stress markers before stressed vowels.
 *
 * Pure JavaScript -- no external dependencies.
 */

import { getCmuDictSync, isCmuDictLoaded, loadCmuDict, toCmuDictMap } from "./cmudict.js";
import { normalizeAndTokenize, normalizeNumbers } from "./normalize.js";

export { isCmuDictLoaded, loadCmuDict, normalizeAndTokenize, normalizeNumbers };

// ---------------------------------------------------------------------------
// ARPAbet -> IPA mapping (matches Python english.py ARPABET_TO_IPA)
// ---------------------------------------------------------------------------

const ARPABET_TO_IPA = {
  AA: "\u0251", // ɑ
  AE: "\u00e6", // æ
  AH: "\u028c", // ʌ
  AO: "\u0254\u02d0", // ɔː
  AW: "a\u028a", // aʊ
  AY: "a\u026a", // aɪ
  B: "b",
  CH: "t\u0283", // tʃ
  D: "d",
  DH: "\u00f0", // ð
  EH: "\u025b", // ɛ
  ER: "\u025a", // ɚ  (unstressed default; stressed -> ɜː)
  EY: "e\u026a", // eɪ
  F: "f",
  G: "\u0261", // ɡ
  HH: "h",
  IH: "\u026a", // ɪ
  IY: "i\u02d0", // iː
  JH: "d\u0292", // dʒ
  K: "k",
  L: "l",
  M: "m",
  N: "n",
  NG: "\u014b", // ŋ
  OW: "o\u028a", // oʊ
  OY: "\u0254\u026a", // ɔɪ
  P: "p",
  R: "\u0279", // ɹ
  S: "s",
  SH: "\u0283", // ʃ
  T: "t",
  TH: "\u03b8", // θ
  UH: "\u028a", // ʊ
  UW: "u\u02d0", // uː
  V: "v",
  W: "w",
  Y: "j",
  Z: "z",
  ZH: "\u0292", // ʒ
};

// Unstressed AH -> schwa
const AH_UNSTRESSED_IPA = "\u0259"; // ə

// Punctuation characters
const PUNCTUATION = new Set([",", ".", ";", ":", "!", "?"]);

// ---------------------------------------------------------------------------
// Function words -- stress is removed to match espeak-ng behavior.
// ---------------------------------------------------------------------------

const FUNCTION_WORDS = new Set([
  // articles / determiners
  "a",
  "an",
  "the",
  // pronouns
  "i",
  "me",
  "my",
  "mine",
  "myself",
  "you",
  "your",
  "yours",
  "yourself",
  "he",
  "him",
  "his",
  "himself",
  "she",
  "her",
  "hers",
  "herself",
  "it",
  "its",
  "itself",
  "we",
  "us",
  "our",
  "ours",
  "ourselves",
  "they",
  "them",
  "their",
  "theirs",
  "themselves",
  // be-verbs
  "am",
  "is",
  "are",
  "was",
  "were",
  "be",
  "been",
  "being",
  // auxiliaries
  "have",
  "has",
  "had",
  "having",
  "do",
  "does",
  "did",
  "will",
  "would",
  "shall",
  "should",
  "can",
  "could",
  "may",
  "might",
  "must",
  // prepositions
  "at",
  "by",
  "for",
  "from",
  "in",
  "of",
  "on",
  "to",
  "with",
  "about",
  "after",
  "before",
  "between",
  "into",
  "through",
  "under",
  // conjunctions
  "and",
  "but",
  "or",
  "nor",
  "so",
  "yet",
  "if",
  "that",
  "than",
  "when",
  "while",
  "as",
  "because",
  "since",
  // others
  "not",
  "no",
]);

// ---------------------------------------------------------------------------
// Words
// ---------------------------------------------------------------------------

/**
 * Words of the original text used to find function words.
 *
 * Mirrors Python `re.findall(r"[a-zA-Z']+", text.lower())`. Python takes
 * them from the text before number expansion and aligns them with the
 * spoken words in order, so `the 3 of us` gives `three` the function-word
 * flag of `of`. The training data was phonemized that way, so it is kept.
 *
 * @param {string} text
 * @returns {string[]}
 */
function sourceWords(text) {
  return (text.match(/[a-zA-Z']+/g) ?? []).map((w) => w.toLowerCase());
}

/**
 * A word made of one punctuation character (`,` `.` `;` `:` `!` `?`):
 * attached to the preceding word without a word boundary.
 *
 * @param {string} word
 * @returns {boolean}
 */
function isPunctuationWord(word) {
  return word.length === 1 && PUNCTUATION.has(word);
}

/** The name of each letter, used to spell words that cannot be read otherwise. */
const LETTER_NAMES = new Map([
  ["a", "EY1"],
  ["b", "B IY1"],
  ["c", "S IY1"],
  ["d", "D IY1"],
  ["e", "IY1"],
  ["f", "EH1 F"],
  ["g", "JH IY1"],
  ["h", "EY1 CH"],
  ["i", "AY1"],
  ["j", "JH EY1"],
  ["k", "K EY1"],
  ["l", "EH1 L"],
  ["m", "EH1 M"],
  ["n", "EH1 N"],
  ["o", "OW1"],
  ["p", "P IY1"],
  ["q", "K Y UW1"],
  ["r", "AA1 R"],
  ["s", "EH1 S"],
  ["t", "T IY1"],
  ["u", "Y UW1"],
  ["v", "V IY1"],
  ["w", "D AH1 B AH0 L Y UW0"],
  ["x", "EH1 K S"],
  ["y", "W AY1"],
  ["z", "Z IY1"],
]);

/** @param {string} c */
function isUpper(c) {
  return c >= "A" && c <= "Z";
}

/** @param {string} c */
function isLower(c) {
  return c >= "a" && c <= "z";
}

/**
 * Splits a word at CamelCase boundaries, like Python
 * `re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+", word)`:
 * `ChatGPT` -> `Chat` + `GPT`, `HTMLParser` -> `HTML` + `Parser`.
 *
 * @param {string} word
 * @returns {string[]}
 */
export function splitCamelCase(word) {
  /** @param {number} from @param {(c: string) => boolean} pred */
  const runEnd = (from, pred) => {
    let j = from;
    while (j < word.length && pred(word[j])) {
      j++;
    }
    return j;
  };
  const parts = [];
  let i = 0;
  while (i < word.length) {
    if (isUpper(word[i])) {
      const upperEnd = runEnd(i, isUpper);
      const lowerFollows = upperEnd < word.length && isLower(word[upperEnd]);
      if (lowerFollows && upperEnd - i >= 2) {
        // The last capital starts the next part.
        parts.push(word.slice(i, upperEnd - 1));
        i = upperEnd - 1;
      } else if (lowerFollows) {
        const end = runEnd(upperEnd, isLower);
        parts.push(word.slice(i, end));
        i = end;
      } else {
        parts.push(word.slice(i, upperEnd));
        i = upperEnd;
      }
    } else if (isLower(word[i])) {
      const end = runEnd(i, isLower);
      parts.push(word.slice(i, end));
      i = end;
    } else {
      i++;
    }
  }
  return parts;
}

// ---------------------------------------------------------------------------
// ARPAbet parsing and IPA conversion
// ---------------------------------------------------------------------------

/**
 * Parse an ARPAbet string: `"HH AH0 L OW1"` ->
 * `[["HH", -1], ["AH", 0], ["L", -1], ["OW", 1]]`.
 *
 * @param {string} arpa
 * @returns {[string, number][]}
 */
function parseArpabet(arpa) {
  return arpa
    .split(/\s+/)
    .filter((t) => t)
    .map((tok) => {
      const last = tok[tok.length - 1];
      if (tok.length > 1 && (last === "0" || last === "1" || last === "2")) {
        return [tok.slice(0, -1), Number(last)];
      }
      return [tok, -1];
    });
}

/**
 * Convert parsed ARPAbet to IPA with Python's context rules:
 * AA + R -> ɑːɹ, stressed ER -> ɜː, unstressed AH -> ə.
 * Unknown symbols are skipped (as in the Rust and C++ ports).
 *
 * @param {[string, number][]} tokens
 * @returns {[string, number][]} (ipa, stress) pairs
 */
function convertWordToIpa(tokens) {
  const result = [];
  let i = 0;
  while (i < tokens.length) {
    const [base, stress] = tokens[i];
    const next = tokens[i + 1];
    if (base === "AA" && next && next[0] === "R" && next[1] === -1) {
      result.push(["\u0251\u02d0\u0279", stress]); // ɑːɹ
      i += 2;
      continue;
    }
    if (base === "ER" && stress === 1) {
      result.push(["\u025c\u02d0", stress]); // ɜː
    } else if (base === "AH" && stress === 0) {
      result.push([AH_UNSTRESSED_IPA, stress]);
    } else if (Object.hasOwn(ARPABET_TO_IPA, base)) {
      result.push([ARPABET_TO_IPA[base], stress]);
    }
    i += 1;
  }
  return result;
}

// ---------------------------------------------------------------------------
// Morphological fallback for words missing from the dictionary
// (C++ tryMorphologicalFallback / Rust try_morphological_fallback)
// ---------------------------------------------------------------------------

/**
 * Strip a common suffix and look the stem up; returns the stem's ARPAbet
 * with the suffix's phonemes appended, or null.
 *
 * @param {string} word lowercase
 * @param {Map<string, string>} dict
 * @returns {string|null}
 */
function tryMorphologicalFallback(word, dict) {
  const len = word.length;
  /** @param {string} base @param {string} suffixArpa */
  const tryBase = (base, suffixArpa) => {
    const arpa = dict.get(base);
    return arpa === undefined ? null : `${arpa} ${suffixArpa}`;
  };
  /** @param {string} base */
  const doubled = (base) => base.length >= 2 && base[base.length - 1] === base[base.length - 2];

  // -ing (running->run, making->make, sitting->sit)
  if (len > 4 && word.endsWith("ing")) {
    const base = word.slice(0, -3);
    const r =
      tryBase(base, "IH0 NG") ??
      (doubled(base) ? tryBase(base.slice(0, -1), "IH0 NG") : null) ??
      tryBase(`${base}e`, "IH0 NG");
    if (r !== null) {
      return r;
    }
  }

  // -ed (walked->walk, stopped->stop, loved->love)
  if (len > 3 && word.endsWith("ed")) {
    const base = word.slice(0, -2);
    const r =
      tryBase(base, "D") ??
      (doubled(base) ? tryBase(base.slice(0, -1), "D") : null) ??
      tryBase(word.slice(0, -1), "D");
    if (r !== null) {
      return r;
    }
  }

  // -s / -es / -ies (cats->cat, boxes->box, countries->country)
  if (len > 2 && word.endsWith("s")) {
    const r =
      (len > 4 && word.endsWith("ies") ? tryBase(`${word.slice(0, -3)}y`, "Z") : null) ??
      (len > 3 && word.endsWith("es") ? tryBase(word.slice(0, -2), "IH0 Z") : null) ??
      tryBase(word.slice(0, -1), "Z");
    if (r !== null) {
      return r;
    }
  }

  // -er (faster->fast, runner->run)
  if (len > 3 && word.endsWith("er")) {
    const base = word.slice(0, -2);
    const r = tryBase(base, "ER0") ?? (doubled(base) ? tryBase(base.slice(0, -1), "ER0") : null);
    if (r !== null) {
      return r;
    }
  }

  // -ly / -ily (quickly->quick, happily->happy)
  if (len > 3 && word.endsWith("ly")) {
    const r =
      tryBase(word.slice(0, -2), "L IY0") ??
      (len > 4 && word[len - 3] === "i" ? tryBase(`${word.slice(0, -3)}y`, "L IY0") : null);
    if (r !== null) {
      return r;
    }
  }

  // -est (fastest->fast)
  if (len > 4 && word.endsWith("est")) {
    return tryBase(word.slice(0, -3), "AH0 S T");
  }

  return null;
}

// ---------------------------------------------------------------------------
// EnglishG2P class
// ---------------------------------------------------------------------------

const NOT_LOADED_MESSAGE =
  "EnglishG2P: the CMU dictionary is not loaded. Call `await englishG2P.initialize()` " +
  "(EnglishG2P.create() and G2P.create() do this) before phonemizing, or pass a " +
  "preloaded dictionary as `new EnglishG2P({ cmuDict })`.";

export class EnglishG2P {
  /**
   * Create an EnglishG2P instance.
   *
   * The CMU dictionary is not read here. Call `initialize()` (or use
   * `EnglishG2P.create()`) to load the bundled one; in Node it is also read
   * synchronously on the first `phonemize()` call.
   *
   * @param {Object} [options={}]
   * @param {Record<string, string>|Map<string, string>} [options.cmuDict]
   *   A dictionary to use instead of the bundled one: lowercase word ->
   *   ARPAbet string (`{ hello: "HH AH0 L OW1" }`).
   */
  constructor(options = {}) {
    this._options = options;
    /** @type {Map<string, string>|null} */
    this._dict = options.cmuDict ? toCmuDictMap(options.cmuDict) : null;
  }

  /**
   * Create an EnglishG2P instance with its dictionary loaded.
   *
   * @param {Object} [options={}]  See the constructor.
   * @returns {Promise<EnglishG2P>}
   */
  static async create(options = {}) {
    const g2p = new EnglishG2P(options);
    await g2p.initialize();
    return g2p;
  }

  /**
   * Load the bundled CMU dictionary unless this instance already has one.
   * Safe to call more than once.
   *
   * @returns {Promise<EnglishG2P>}
   */
  async initialize() {
    if (!this._dict) {
      this._dict = await loadCmuDict();
    }
    return this;
  }

  /** Whether this instance has its dictionary. */
  get isInitialized() {
    return this._dict !== null;
  }

  /**
   * The dictionary, loading it synchronously when that is possible.
   *
   * @returns {Map<string, string>}
   * @private
   */
  _requireDict() {
    if (!this._dict) {
      this._dict = getCmuDictSync();
      if (!this._dict) {
        throw new Error(NOT_LOADED_MESSAGE);
      }
    }
    return this._dict;
  }

  /**
   * The dictionary entry of `word`, or of its stem.
   *
   * @param {string} word
   * @returns {string|null}
   * @private
   */
  _lookup(word) {
    const dict = this._requireDict();
    const lower = word.toLowerCase();
    return dict.get(lower) ?? tryMorphologicalFallback(lower, dict);
  }

  /**
   * ARPAbet for a word; never null when the word has a letter.
   *
   * Python reads words missing from the dictionary with g2p_en's neural
   * guesser, which is not ported. Instead such a word is split at `-` and
   * `.`, retried without apostrophes, split at CamelCase boundaries, and
   * finally spelled letter by letter. The parts are joined into one word.
   *
   * @param {string} word
   * @returns {string|null}
   * @private
   */
  _wordArpabet(word) {
    const found = this._lookup(word);
    if (found !== null) {
      return found;
    }
    /** @param {string[]} parts */
    const join = (parts) => {
      const arpas = parts.map((p) => this._wordArpabet(p)).filter((a) => a !== null);
      return arpas.length > 0 ? arpas.join(" ") : null;
    };
    if (word.includes("-") || word.includes(".")) {
      return join(word.split(/[-.]/).filter((p) => p));
    }
    if (word.includes("'")) {
      return this._wordArpabet(word.replace(/'/g, ""));
    }
    const parts = splitCamelCase(word);
    if (parts.length > 1) {
      return join(parts);
    }
    const spelled = [...word.toLowerCase()]
      .map((c) => LETTER_NAMES.get(c))
      .filter((a) => a !== undefined);
    return spelled.length > 0 ? spelled.join(" ") : null;
  }

  /**
   * Phonemes and Python's prosody for `text`.
   *
   * @param {string} text
   * @returns {{ tokens: string[], prosody: {a1: number, a2: number, a3: number}[] }}
   * @private
   */
  _phonemize(text) {
    /** @type {string[]} */
    const tokens = [];
    /** @type {{a1: number, a2: number, a3: number}[]} */
    const prosody = [];
    if (!text || typeof text !== "string") {
      return { tokens, prosody };
    }
    const words = normalizeAndTokenize(text);
    const source = sourceWords(text);
    let needSpace = false;
    let srcIdx = 0;

    for (const word of words) {
      const isPunct = isPunctuationWord(word);

      // A word without a letter (`-`, `'`, `...`) is kept as it is, one
      // phoneme per character, as Python does.
      /** @type {[string, number][]} */
      let wordIpas;
      if (/[A-Za-z]/.test(word)) {
        const arpa = this._wordArpabet(word);
        if (arpa === null) {
          continue;
        }
        wordIpas = convertWordToIpa(parseArpabet(arpa));
      } else {
        wordIpas = [[word, -1]];
      }

      if (!isPunct) {
        // Function words are matched against the source words in order.
        if (srcIdx < source.length) {
          if (FUNCTION_WORDS.has(source[srcIdx])) {
            wordIpas = wordIpas.map(([ipa, stress]) => [ipa, stress >= 1 ? 0 : stress]);
          }
          srcIdx += 1;
        }
        // Punctuation attaches to the preceding word; other words get a
        // word boundary before them (except the first).
        if (needSpace) {
          tokens.push(" ");
          prosody.push({ a1: 0, a2: 0, a3: 0 });
        }
      }

      // A3 = total IPA character count for the word
      const a3 = wordIpas.reduce((n, [ipa]) => n + [...ipa].length, 0);

      for (const [ipa, stress] of wordIpas) {
        // stress -> A2: primary(1)->2, secondary(2)->1, others->0
        const a2 = stress === 1 ? 2 : stress === 2 ? 1 : 0;
        if (stress === 1) {
          tokens.push("\u02c8"); // ˈ primary stress
          prosody.push({ a1: 0, a2, a3 });
        } else if (stress === 2) {
          tokens.push("\u02cc"); // ˌ secondary stress
          prosody.push({ a1: 0, a2, a3 });
        }
        // Each IPA character becomes a separate token
        for (const ch of ipa) {
          tokens.push(ch);
          prosody.push({ a1: 0, a2, a3 });
        }
      }

      needSpace = true;
    }

    return { tokens, prosody };
  }

  /**
   * Convert English text to IPA tokens.
   *
   * Processing flow (as Python and the Rust port):
   *   1. normalize and tokenize like g2p_en
   *   2. look each word up in the CMU dictionary (then its stem)
   *   3. split / spell words missing from it
   *   4. convert ARPAbet to IPA, remove the stress of function words
   *   5. insert stress markers (ˈ / ˌ) before stressed vowels
   *   6. return a flat IPA token array with word-boundary spaces
   *
   * Needs the CMU dictionary: in Node it is read synchronously when
   * `initialize()` has not been called; elsewhere an uninitialised instance
   * throws for any text that has words.
   *
   * @param {string} text - Input English text.
   * @returns {{ tokens: string[], prosody: null[] }}
   */
  phonemize(text) {
    const { tokens } = this._phonemize(text);
    return { tokens, prosody: new Array(tokens.length).fill(null) };
  }

  /**
   * Convert English text to IPA tokens with Python's prosody features:
   * a1 = 0, a2 = stress (primary 2, secondary 1, none 0) and a3 = the
   * number of IPA characters of the word. Word boundaries get zeros.
   *
   * @param {string} text - Input English text.
   * @returns {{ tokens: string[], prosody: {a1: number, a2: number, a3: number}[] }}
   */
  phonemizeWithProsody(text) {
    return this._phonemize(text);
  }
}
