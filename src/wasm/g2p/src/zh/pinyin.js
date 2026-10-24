/**
 * Chinese text -> pinyin -> IPA, ported from the Rust `ChinesePhonemizer`
 * (`src/rust/piper-plus-g2p/src/chinese.rs`), which matches the Python
 * training-side G2P (`src/python/g2p/piper_plus_g2p/chinese.py`, pypinyin).
 *
 * Pipeline (same steps and order as Rust `phonemize_chinese_internal`):
 *   1. Text -> pinyin: longest phrase match (2-8 characters), then the first
 *      single-character reading.
 *   2. Pinyin normalisation (y/w spelling, v -> ü).
 *   3. Tone sandhi inside each run of Chinese characters (T3+T3, 一, 不).
 *   4. Pinyin -> IPA (initial + compound final + tone marker), erhua.
 *
 * Tokens are spelled out (e.g. `"tʂʰ"`, `"tone3"`), like the rest of this
 * package; `Encoder` maps the multi-codepoint ones to their PUA IDs, where
 * Rust maps them before returning.
 *
 * @module zh/pinyin
 */

/** Pinyin initial -> IPA. */
const INITIAL_TO_IPA = new Map([
  ["b", "p"],
  ["p", "pʰ"],
  ["m", "m"],
  ["f", "f"],
  ["d", "t"],
  ["t", "tʰ"],
  ["n", "n"],
  ["l", "l"],
  ["g", "k"],
  ["k", "kʰ"],
  ["h", "x"],
  ["j", "tɕ"],
  ["q", "tɕʰ"],
  ["x", "ɕ"],
  ["zh", "tʂ"],
  ["ch", "tʂʰ"],
  ["sh", "ʂ"],
  ["r", "ɻ"],
  ["z", "ts"],
  ["c", "tsʰ"],
  ["s", "s"],
]);

/** Pinyin final -> IPA (compound finals as one token). */
const FINAL_TO_IPA = new Map([
  // Simple vowels
  ["a", "a"],
  ["o", "o"],
  ["e", "ɤ"],
  ["i", "i"],
  ["u", "u"],
  ["ü", "y_vowel"],
  ["v", "y_vowel"],
  // Diphthongs
  ["ai", "aɪ"],
  ["ei", "eɪ"],
  ["ao", "aʊ"],
  ["ou", "oʊ"],
  // Nasal finals
  ["an", "an"],
  ["en", "ən"],
  ["ang", "aŋ"],
  ["eng", "əŋ"],
  ["ong", "uŋ"],
  // Retroflex final
  ["er", "ɚ"],
  // i-compound finals
  ["ia", "ia"],
  ["ie", "iɛ"],
  ["iao", "iaʊ"],
  ["iu", "iou"],
  ["iou", "iou"],
  ["ian", "iɛn"],
  ["in", "in"],
  ["iang", "iaŋ"],
  ["ing", "iŋ"],
  ["iong", "iuŋ"],
  // u-compound finals
  ["ua", "ua"],
  ["uo", "uo"],
  ["uai", "uaɪ"],
  ["ui", "ueɪ"],
  ["uei", "ueɪ"],
  ["uan", "uan"],
  ["un", "uən"],
  ["uen", "uən"],
  ["uang", "uaŋ"],
  ["ueng", "uəŋ"],
  // ü-compound finals
  ["üe", "yɛ"],
  ["ve", "yɛ"],
  ["üan", "yɛn"],
  ["van", "yɛn"],
  ["ün", "yn"],
  ["vn", "yn"],
  // Syllabic consonants (internal keys from splitPinyin)
  ["-i_retroflex", "ɻ̩"],
  ["-i_alveolar", "ɨ"],
]);

/** Consonant initials, two-letter ones first for prefix matching. */
const INITIALS_ORDER = [
  "zh",
  "ch",
  "sh",
  "b",
  "p",
  "m",
  "f",
  "d",
  "t",
  "n",
  "l",
  "g",
  "k",
  "h",
  "j",
  "q",
  "x",
  "r",
  "z",
  "c",
  "s",
];

const RETROFLEX_INITIALS = new Set(["zh", "ch", "sh", "r"]);
const ALVEOLAR_INITIALS = new Set(["z", "c", "s"]);

/** Chinese punctuation -> ASCII. */
const ZH_PUNCT_TO_ASCII = new Map([
  ["。", "."], // 。
  ["，", ","], // ，
  ["！", "!"], // ！
  ["？", "?"], // ？
  ["、", ","], // 、
  ["；", ";"], // ；
  ["：", ":"], // ：
  ["…", "."], // …
  ["—", ","], // —
  ["“", '"'], // “
  ["”", '"'], // ”
  ["‘", "'"], // ‘
  ["’", "'"], // ’
]);

/** Punctuation kept as it is (Rust `is_zh_punctuation` minus the mapped ones). */
const ZH_PUNCTUATION = new Set([",", ".", ";", ":", "!", "?", ...ZH_PUNCT_TO_ASCII.keys()]);

const WHITESPACE_RE = /^\p{White_Space}$/u;
const ALPHABETIC_RE = /^\p{Alphabetic}$/u;
const ASCII_DIGIT_RE = /^[0-9]$/;

/**
 * CJK Unified Ideographs and Extension A (Rust `is_cjk`).
 *
 * @param {number} code
 * @returns {boolean}
 */
function isCjk(code) {
  return (code >= 0x4e00 && code <= 0x9fff) || (code >= 0x3400 && code <= 0x4dbf);
}

/**
 * Normalise pinyin y/w spelling and v -> ü.
 *
 * @param {string} py  Pinyin without tone digit.
 * @returns {string}
 */
export function normalizePinyin(py) {
  const s = py.replaceAll("v", "ü");
  if (s.startsWith("yu")) {
    return `ü${s.slice(2)}`;
  }
  if (s.startsWith("y")) {
    const rest = s.slice(1);
    return rest.startsWith("i") ? rest : `i${rest}`;
  }
  if (s.startsWith("w")) {
    const rest = s.slice(1);
    return rest.startsWith("u") ? rest : `u${rest}`;
  }
  return s;
}

/**
 * Split normalised pinyin into [initial, final].
 *
 * @param {string} pinyin
 * @returns {[string, string]}
 */
export function splitPinyin(pinyin) {
  for (const init of INITIALS_ORDER) {
    if (pinyin.startsWith(init)) {
      let finalPart = pinyin.slice(init.length);
      // Syllabic consonant: bare "i" after retroflex or alveolar initials
      if (finalPart === "i") {
        if (RETROFLEX_INITIALS.has(init)) {
          return [init, "-i_retroflex"];
        }
        if (ALVEOLAR_INITIALS.has(init)) {
          return [init, "-i_alveolar"];
        }
      }
      // After j/q/x, u represents ü
      if ((init === "j" || init === "q" || init === "x") && finalPart.startsWith("u")) {
        finalPart = `ü${finalPart.slice(1)}`;
      }
      return [init, finalPart];
    }
  }
  return ["", pinyin];
}

/**
 * Convert one pinyin syllable (no tone digit) to IPA tokens.
 *
 * @param {string} syllable
 * @param {number} tone  1-5
 * @returns {string[]}
 */
export function pinyinToIpa(syllable, tone) {
  const [initial, finalPart] = splitPinyin(syllable);
  const tokens = [];
  if (initial !== "") {
    const ipa = INITIAL_TO_IPA.get(initial);
    if (ipa !== undefined) {
      tokens.push(ipa);
    }
  }
  if (finalPart !== "") {
    const ipa = FINAL_TO_IPA.get(finalPart);
    if (ipa !== undefined) {
      tokens.push(ipa);
    } else {
      // Unknown final: decompose letter by letter (ASCII lowercase only).
      for (const ch of finalPart) {
        if (ch >= "a" && ch <= "z") {
          tokens.push(FINAL_TO_IPA.get(ch) ?? ch);
        }
      }
    }
  }
  if (tone >= 1 && tone <= 5) {
    tokens.push(`tone${tone}`);
  }
  return tokens;
}

/**
 * Split a trailing tone digit 1-5 off a syllable; no digit means tone 5.
 *
 * @param {string} syllable
 * @returns {[string, number]}
 */
export function extractTone(syllable) {
  const last = syllable.charCodeAt(syllable.length - 1);
  if (last >= 0x31 && last <= 0x35) {
    return [syllable.slice(0, -1), last - 0x30];
  }
  return [syllable, 5];
}

/**
 * Mandarin tone sandhi on one run of syllables, in place:
 *   1. T3 + T3 -> T2 + T3
 *   2. 一 (normalised "i") T1 + T4 -> T2
 *   3. 一 T1 + T1/T2/T3 -> T4
 *   4. 不 (bu) T4 + T4 -> T2
 *
 * @param {{ syllable: string, tone: number }[]} run
 */
export function applyToneSandhi(run) {
  for (let i = 0; i + 1 < run.length; i++) {
    const tone = run[i].tone;
    const next = run[i + 1].tone;
    if (tone === 3 && next === 3) {
      run[i].tone = 2;
      continue;
    }
    if (run[i].syllable === "i" && tone === 1) {
      if (next === 4) {
        run[i].tone = 2;
      } else if (next >= 1 && next <= 3) {
        run[i].tone = 4;
      }
      continue;
    }
    if (run[i].syllable === "bu" && tone === 4 && next === 4) {
      run[i].tone = 2;
    }
  }
}

/**
 * Character index -> [position in run, run length] for runs of CJK characters.
 *
 * @param {string[]} chars
 * @returns {Map<number, [number, number]>}
 */
function buildWordInfo(chars) {
  const info = new Map();
  let group = [];
  const flush = () => {
    group.forEach((idx, pos) => info.set(idx, [pos + 1, group.length]));
    group = [];
  };
  chars.forEach((ch, i) => {
    if (isCjk(ch.codePointAt(0))) {
      group.push(i);
    } else if (group.length > 0) {
      flush();
    }
  });
  if (group.length > 0) {
    flush();
  }
  return info;
}

/**
 * @typedef {{ isChinese: boolean, syllable: string, tone: number }} CharPinyin
 */

/**
 * One entry per character: the phrase or single-character reading.
 *
 * @param {string[]} chars
 * @param {import('./pinyin-dict.js').PinyinDictionary} dict
 * @returns {CharPinyin[]}
 */
function textToPinyin(chars, dict) {
  /** @type {CharPinyin[]} */
  const result = [];
  let i = 0;
  while (i < chars.length) {
    if (!isCjk(chars[i].codePointAt(0))) {
      result.push({ isChinese: false, syllable: "", tone: 0 });
      i++;
      continue;
    }

    // Longest phrase match, 8 down to 2 characters.
    let matched = false;
    for (let len = Math.min(chars.length - i, 8); len >= 2; len--) {
      const readings = dict.lookupPhrase(chars.slice(i, i + len).join(""));
      if (readings) {
        for (let j = 0; j < len; j++) {
          const [base, tone] = j < readings.length ? extractTone(readings[j]) : ["", 5];
          result.push({ isChinese: true, syllable: normalizePinyin(base), tone });
        }
        i += len;
        matched = true;
        break;
      }
    }
    if (matched) {
      continue;
    }

    const reading = dict.lookupChar(chars[i].codePointAt(0));
    if (reading !== null) {
      const [base, tone] = extractTone(reading);
      result.push({ isChinese: true, syllable: normalizePinyin(base), tone });
    } else {
      // Unknown CJK character
      result.push({ isChinese: false, syllable: "", tone: 0 });
    }
    i++;
  }
  return result;
}

/**
 * Apply tone sandhi to each run of consecutive Chinese characters.
 *
 * @param {CharPinyin[]} list
 */
function applyToneSandhiToRuns(list) {
  let i = 0;
  while (i < list.length) {
    if (!list[i].isChinese) {
      i++;
      continue;
    }
    const start = i;
    while (i < list.length && list[i].isChinese) {
      i++;
    }
    if (i - start >= 2) {
      applyToneSandhi(list.slice(start, i));
    }
  }
}

/**
 * @typedef {{ a1: number, a2: number, a3: number }} Prosody
 */

/**
 * Phonemize Chinese text with the pinyin dictionaries.
 *
 * Prosody per token: Chinese syllables carry a1 = tone (after sandhi),
 * a2 = position in the run of Chinese characters, a3 = run length; spaces
 * {0,0,0}; letters and digits {0,0,1}; punctuation null. Other characters are
 * dropped.
 *
 * @param {string} text
 * @param {import('./pinyin-dict.js').PinyinDictionary} dict
 * @returns {{ tokens: string[], prosody: (Prosody|null)[] }}
 */
export function phonemizeChinese(text, dict) {
  const chars = Array.from(text);
  const wordInfo = buildWordInfo(chars);
  const pinyins = textToPinyin(chars, dict);
  applyToneSandhiToRuns(pinyins);

  const tokens = [];
  /** @type {(Prosody|null)[]} */
  const prosody = [];

  pinyins.forEach((py, idx) => {
    const ch = chars[idx];
    if (!py.isChinese) {
      const mapped = ZH_PUNCT_TO_ASCII.get(ch);
      if (mapped !== undefined) {
        tokens.push(mapped);
        prosody.push(null);
      } else if (ZH_PUNCTUATION.has(ch)) {
        tokens.push(ch);
        prosody.push(null);
      } else if (WHITESPACE_RE.test(ch)) {
        tokens.push(" ");
        prosody.push({ a1: 0, a2: 0, a3: 0 });
      } else if (ASCII_DIGIT_RE.test(ch) || ALPHABETIC_RE.test(ch)) {
        tokens.push(ch);
        prosody.push({ a1: 0, a2: 0, a3: 1 });
      }
      // Other characters are skipped.
      return;
    }

    let syllable = py.syllable;
    // Erhua: a trailing r that is not the syllable "er" itself
    const erhua = syllable.length > 1 && syllable !== "er" && syllable.endsWith("r");
    if (erhua) {
      syllable = syllable.slice(0, -1);
    }
    const ipa = pinyinToIpa(syllable, py.tone);
    if (erhua && ipa.length > 0) {
      if (ipa[ipa.length - 1].startsWith("tone")) {
        ipa.splice(ipa.length - 1, 0, "ɚ");
      } else {
        ipa.push("ɚ");
      }
    }

    const [pos, len] = wordInfo.get(idx) ?? [1, 1];
    for (const token of ipa) {
      tokens.push(token);
      prosody.push({ a1: py.tone, a2: pos, a3: len });
    }
  });

  return { tokens, prosody };
}

/**
 * IPA tokens for a list of pinyin syllables with tone digits, as spoken (no
 * tone sandhi). Prosody: a1 = tone, a2 = a3 = 1.
 *
 * @param {string[]} syllables  e.g. `["ji4", "pi4", "ai1", "si4"]`
 * @returns {{ tokens: string[], prosody: Prosody[] }}
 */
export function phonemizePinyinSyllables(syllables) {
  const tokens = [];
  const prosody = [];
  for (const s of syllables) {
    const [base, tone] = extractTone(s);
    for (const token of pinyinToIpa(normalizePinyin(base), tone)) {
      tokens.push(token);
      prosody.push({ a1: tone, a2: 1, a3: 1 });
    }
  }
  return { tokens, prosody };
}
