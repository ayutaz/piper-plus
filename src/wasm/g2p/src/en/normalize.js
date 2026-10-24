/**
 * English text normalization, ported from Python's g2p_en.
 *
 * Python's English G2P (`g2p_en.G2p.__call__`) rewrites the text before its
 * dictionary lookup. This module ports those steps, following the Rust port
 * (`src/rust/piper-plus-g2p/src/english_normalize.rs`) step for step, so the
 * JS phonemizer sees the same words:
 *
 * 1. `normalizeNumbers` spells numbers out the way inflect does
 *    (`123` -> `one hundred twenty-three`, `1984` -> `nineteen eighty-four`,
 *    `$5` -> `five dollars`, `2nd` -> `second`);
 * 2. accents are stripped (NFD, combining marks removed);
 * 3. every character other than `a-z A-Z ' . , ? ! -` and the ASCII space is
 *    removed, except that Unicode whitespace becomes a space (see below);
 * 4. `i.e.` / `e.g.` become `that is` / `for example` (case-insensitively);
 * 5. the subset of nltk's `TweetTokenizer` that this character set can reach
 *    splits the text into words.
 *
 * Python lowercases at step 2; the port keeps the case because the
 * out-of-dictionary fallback splits CamelCase words. Callers lowercase for
 * the dictionary lookup. `test/test-english-normalize.js` checks both steps
 * against `tests/fixtures/g2p/english_normalize_cases.json`, generated from
 * Python by `scripts/build_english_normalize_fixture.py`.
 *
 * Pure JavaScript, no dependencies.
 *
 * @module @piper-plus/g2p/en/normalize
 */

// ---------------------------------------------------------------------------
// Number expansion (g2p_en expand.py + inflect number_to_words)
// ---------------------------------------------------------------------------

const COMMA_NUMBER_RE = /([0-9][0-9,]+[0-9])/g;
const POUNDS_RE = /£([0-9,]*[0-9]+)/g;
const DOLLARS_RE = /\$([0-9.,]*[0-9]+)/g;
const DECIMAL_NUMBER_RE = /([0-9]+\.[0-9]+)/g;
const ORDINAL_RE = /[0-9]+(st|nd|rd|th)/g;
const NUMBER_RE = /[0-9]+/g;

// inflect's post-processing of the joined groups.
const WHITESPACES_COMMA_RE = /\s+,/g;
const COMMA_WORD_RE = /, (\S+)\s+$/;
const WHITESPACES_RE = /\s+/g;

const UNIT = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
const TEEN = [
  "ten",
  "eleven",
  "twelve",
  "thirteen",
  "fourteen",
  "fifteen",
  "sixteen",
  "seventeen",
  "eighteen",
  "nineteen",
];
const TEN = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];
/**
 * Group scales. inflect goes on to decillion; the port stops at quintillion
 * and reads longer digit runs digit by digit (as the Rust port does).
 */
const MILL = [
  " ",
  " thousand",
  " million",
  " billion",
  " trillion",
  " quadrillion",
  " quintillion",
];
const DIGIT_NAMES = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
];
/** Ordinal endings, tried at the end of the last word (inflect `ordinal`). */
const ORDINAL_SUFFIXES = [
  ["ty", "tieth"],
  ["one", "first"],
  ["two", "second"],
  ["three", "third"],
  ["five", "fifth"],
  ["eight", "eighth"],
  ["nine", "ninth"],
  ["twelve", "twelfth"],
];

/**
 * Expand numbers in `text` to English words, like g2p_en's
 * `normalize_numbers`. The regex substitutions run in Python's order.
 *
 * @param {string} text
 * @returns {string}
 */
export function normalizeNumbers(text) {
  let s = text.replace(COMMA_NUMBER_RE, (_m, n) => n.replace(/,/g, ""));
  s = s.replace(POUNDS_RE, "$1 pounds");
  s = s.replace(DOLLARS_RE, (_m, amount) => expandDollars(amount));
  s = s.replace(DECIMAL_NUMBER_RE, (_m, n) => n.replace(/\./g, " point "));
  s = s.replace(ORDINAL_RE, (m) => expandOrdinal(m));
  return s.replace(NUMBER_RE, (m) => expandNumber(m));
}

/**
 * The decimal digits of `s` without leading zeros ("0" when there are none).
 * Matches Python's `str(int(s))`; non-digits (a stray comma) are ignored.
 *
 * @param {string} s
 * @returns {string}
 */
function canonicalDigits(s) {
  const trimmed = s.replace(/[^0-9]/g, "").replace(/^0+/, "");
  return trimmed === "" ? "0" : trimmed;
}

/** `$D.C` -> `D dollar(s), C cent(s)` (g2p_en `_expand_dollars`). */
function expandDollars(amount) {
  const parts = amount.split(".");
  if (parts.length > 2) {
    return `${amount} dollars`; // Unexpected format
  }
  const dollars = canonicalDigits(parts[0] ?? "");
  const cents = canonicalDigits(parts[1] ?? "");
  const dollarUnit = dollars === "1" ? "dollar" : "dollars";
  const centUnit = cents === "1" ? "cent" : "cents";
  if (dollars !== "0" && cents !== "0") {
    return `${dollars} ${dollarUnit}, ${cents} ${centUnit}`;
  }
  if (dollars !== "0") {
    return `${dollars} ${dollarUnit}`;
  }
  if (cents !== "0") {
    return `${cents} ${centUnit}`;
  }
  return "zero dollars";
}

/** `21st` -> `twenty-first` (inflect `number_to_words` with an ordinal suffix). */
function expandOrdinal(matched) {
  return toOrdinal(numberWords(canonicalDigits(matched.slice(0, -2)), "and"));
}

/** Cardinal numbers, read as years between 1001 and 2999 (g2p_en `_expand_number`). */
function expandNumber(matched) {
  const digits = canonicalDigits(matched);
  if (digits.length === 4) {
    const n = Number(digits);
    if (n > 1000 && n < 3000) {
      return yearWords(n);
    }
  }
  return numberWords(digits, "");
}

/** @param {number} n 1001..2999 */
function yearWords(n) {
  if (n === 2000) {
    return "two thousand";
  }
  if (n > 2000 && n < 2010) {
    return `two thousand ${numberWords(String(n % 100), "and")}`;
  }
  if (n % 100 === 0) {
    return `${numberWords(String(n / 100), "and")} hundred`;
  }
  // inflect group=2 with zero="oh": two digits at a time.
  const low = n % 100;
  const lowWords =
    low < 10 ? `oh ${UNIT[low]}` : tensWords(Math.floor(low / 10), low % 10, 0).trimEnd();
  const high = Math.floor(n / 100);
  return `${tensWords(Math.floor(high / 10), high % 10, 0).trimEnd()} ${lowWords}`;
}

/** inflect `tenfn`: 0-99 followed by the scale of group `mill`. */
function tensWords(tens, units, mill) {
  if (tens === 1) {
    return `${TEEN[units]}${MILL[mill]}`;
  }
  const hyphen = tens > 0 && units > 0 ? "-" : "";
  return `${TEN[tens]}${hyphen}${UNIT[units]}${MILL[mill]}`;
}

/** inflect `hundfn`: one full group of three digits. */
function hundredsWords(hundreds, tens, units, mill, and) {
  if (hundreds > 0) {
    const andword = tens > 0 || units > 0 ? ` ${and} ` : "";
    return `${UNIT[hundreds]} hundred${andword}${tensWords(tens, units, 0)}${MILL[mill]}, `;
  }
  if (tens > 0 || units > 0) {
    return `${tensWords(tens, units, 0)}${MILL[mill]}, `;
  }
  return "";
}

/**
 * inflect `number_to_words(digits, andword=and)` for a canonical digit
 * string. Groups are joined with ", " except that a last group of 1-99 is
 * joined with `and` (` ` when `and` is empty): `one million one`.
 *
 * @param {string} digits
 * @param {string} and
 * @returns {string}
 */
function numberWords(digits, and) {
  if (digits === "0") {
    return "zero";
  }
  if (digits === "1") {
    return "one";
  }
  const d = [...digits].map((c) => c.charCodeAt(0) - 48);
  if (d.length > 3 * MILL.length) {
    // Beyond quintillion: read each digit.
    return d.map((x) => DIGIT_NAMES[x]).join(" ");
  }

  const groups = Math.floor(d.length / 3);
  const lead = d.length % 3;
  let s = "";
  if (lead === 2) {
    s += `${tensWords(d[0], d[1], groups)}, `;
  } else if (lead === 1) {
    s += `${UNIT[d[0]]}${MILL[groups]}, `;
  }
  for (let g = 0; g < groups; g++) {
    const i = lead + 3 * g;
    s += hundredsWords(d[i], d[i + 1], d[i + 2], groups - 1 - g, and);
  }

  if (s.endsWith(", ")) {
    s = s.slice(0, -2);
  }
  s = s.replace(WHITESPACES_COMMA_RE, ",");
  s = s.replace(COMMA_WORD_RE, (_m, word) => ` ${and} ${word}`);
  return s.replace(WHITESPACES_RE, " ").trim();
}

/** inflect `_sub_ord`: the ordinal of the last word. */
function toOrdinal(words) {
  for (const [suffix, replacement] of ORDINAL_SUFFIXES) {
    if (words.endsWith(suffix)) {
      return words.slice(0, -suffix.length) + replacement;
    }
  }
  return `${words}th`;
}

// ---------------------------------------------------------------------------
// Accent stripping and character filter
// ---------------------------------------------------------------------------

/**
 * Base letter of each code point in U+00C0..U+024F whose NFD form is an
 * ASCII letter followed by combining marks; `-` where there is none.
 * Generated with Python's `unicodedata` (same table as the Rust port).
 */
const LATIN_BASE_00C0 =
  "AAAAAA-CEEEEIIII-NOOOOO--UUUUY--aaaaaa-ceeeeiiii-nooooo--uuuuy-y" +
  "AaAaAaCcCcCcCcDd--EeEeEeEeEeGgGgGgGgHh--IiIiIiIiI---JjKk-LlLlLl-" +
  "---NnNnNn---OoOoOo--RrRrRrSsSsSsSsTtTt--UuUuUuUuUuUuWwYyYZzZzZz-" +
  "--------------------------------Oo-------------Uu---------------" +
  "-------------AaIiOoUuUuUuUuUu-AaAa----GgKkOoOo--j---Gg--NnAa----" +
  "AaAaEeEeIiIiOoOoRrRrUuUuSsTt--Hh------AaEeOoOoOoOoYy------------" +
  "----------------";

/** The same for U+1E00..U+1EFF (Latin Extended Additional). */
const LATIN_BASE_1E00 =
  "AaBbBbBbCcDdDdDdDdDdEeEeEeEeEeFfGgHhHhHhHhHhIiIiKkKkKkLlLlLlLlMm" +
  "MmMmNnNnNnNnOoOoOoOoPpPpRrRrRrRrSsSsSsSsSsTtTtTtTtUuUuUuUuUuVvVv" +
  "WwWwWwWwWwXxXxYyZzZzZzhtwy------AaAaAaAaAaAaAaAaAaAaAaAaEeEeEeEe" +
  "EeEeEeEeIiIiOoOoOoOoOoOoOoOoOoOoOoOoUuUuUuUuUuUuUuYyYyYyYy------";

/**
 * Unicode White_Space (Rust's `char::is_whitespace`). JS `\s` differs: it
 * matches U+FEFF and misses U+0085.
 */
const WHITESPACE_RE =
  /^[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/;

/** ASCII characters the filter keeps (g2p_en `[^ a-z'.,?!\-]`, case kept). */
const KEPT_RE = /^[A-Za-z '.,?!-]$/;

/**
 * The ASCII letter left after NFD and removing combining marks, for a
 * non-ASCII character, or null.
 *
 * @param {number} cp
 * @returns {string|null}
 */
function foldAccent(cp) {
  let base = "-";
  if (cp >= 0x00c0 && cp <= 0x024f) {
    base = LATIN_BASE_00C0[cp - 0x00c0] ?? "-";
  } else if (cp >= 0x1e00 && cp <= 0x1eff) {
    base = LATIN_BASE_1E00[cp - 0x1e00] ?? "-";
  } else if (cp === 0x212a) {
    base = "K"; // KELVIN SIGN
  } else if (cp === 0x212b) {
    base = "A"; // ANGSTROM SIGN
  }
  return base === "-" ? null : base;
}

/**
 * Steps 2-3: strip accents and keep `a-z A-Z ' . , ? ! -` and the ASCII
 * space. The result is ASCII. Unlike g2p_en, any whitespace (tab, newline,
 * no-break space, ...) becomes a space instead of being removed: removing it
 * joins the words around it, and Python reads the joined word with a neural
 * predictor this port does not have.
 *
 * @param {string} text
 * @returns {string}
 */
function stripAccentsAndFilter(text) {
  let out = "";
  for (const ch of text) {
    let c = ch;
    if (WHITESPACE_RE.test(ch)) {
      c = " ";
    } else {
      const cp = ch.codePointAt(0) ?? 0;
      if (cp > 0x7f) {
        c = foldAccent(cp) ?? "";
      }
    }
    if (c && KEPT_RE.test(c)) {
      out += c;
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// TweetTokenizer subset
// ---------------------------------------------------------------------------

/** @param {string} c one character */
function isLetter(c) {
  return (c >= "a" && c <= "z") || (c >= "A" && c <= "Z");
}

/** @param {string} c one character */
function isAlnum(c) {
  return isLetter(c) || (c >= "0" && c <= "9");
}

/** nltk `HANG_RE`: 4+ copies of a non-letter, non-digit character become 3. */
function shortenHang(text) {
  let out = "";
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    let j = i + 1;
    while (j < text.length && text[j] === c) {
      j++;
    }
    out += c.repeat(isAlnum(c) ? j - i : Math.min(j - i, 3));
    i = j;
  }
  return out;
}

function letterRunEnd(b, start) {
  let j = start;
  while (j < b.length && isLetter(b[j])) {
    j++;
  }
  return j;
}

/**
 * Naked domain: `[a-z]+([.-][a-z]+){0,126}\.[a-z]{2,13}` not followed by a
 * letter. Like the backtracking regex, it takes the most labels for which
 * the next separator is '.' and the label after it has 2-13 letters.
 *
 * @returns {number|null} end index
 */
function matchDomain(b, start) {
  let pos = letterRunEnd(b, start);
  if (pos === start) {
    return null;
  }
  /** @type {[string, number, number][]} separator, label start, label end */
  const labels = [];
  while (pos + 1 < b.length && (b[pos] === "." || b[pos] === "-") && isLetter(b[pos + 1])) {
    const end = letterRunEnd(b, pos + 1);
    labels.push([b[pos], pos + 1, end]);
    pos = end;
  }
  for (let k = Math.min(labels.length - 1, 126); k >= 0; k--) {
    const [sep, s, e] = labels[k];
    if (sep === "." && e - s >= 2 && e - s <= 13) {
      return e;
    }
  }
  return null;
}

/** Word with apostrophes or dashes: `[a-z]([a-z]|['-])+[a-z]`. */
function matchHyphenatedWord(b, start) {
  if (!isLetter(b[start])) {
    return null;
  }
  let end = start + 1;
  while (end < b.length && (isLetter(b[end]) || b[end] === "'" || b[end] === "-")) {
    end++;
  }
  for (let i = end - 1; i >= start + 2; i--) {
    if (isLetter(b[i])) {
      return i + 1;
    }
  }
  return null;
}

/** Ellipsis: `\.( *\.)+`. */
function matchEllipsis(b, start) {
  if (b[start] !== ".") {
    return null;
  }
  let end = null;
  let j = start + 1;
  for (;;) {
    let k = j;
    while (k < b.length && b[k] === " ") {
      k++;
    }
    if (k < b.length && b[k] === ".") {
      end = k + 1;
      j = k + 1;
    } else {
      return end;
    }
  }
}

/**
 * The part of nltk's `TweetTokenizer` that the filtered character set
 * (`a-z A-Z ' . , ? ! -` and space) can reach. At each position the first
 * matching alternative wins, in nltk's order; spaces only separate words.
 *
 * @param {string} input ASCII text
 * @returns {string[]}
 */
function tweetTokenize(input) {
  const b = shortenHang(input);
  const words = [];
  let i = 0;
  while (i < b.length) {
    if (b[i] === " ") {
      i++;
      continue;
    }
    let end = matchDomain(b, i) ?? matchHyphenatedWord(b, i);
    if (end === null) {
      const run = letterRunEnd(b, i);
      end = run > i ? run : (matchEllipsis(b, i) ?? i + 1);
    }
    words.push(b.slice(i, end));
    i = end;
  }
  return words;
}

/**
 * All of g2p_en's preprocessing: number expansion, accent stripping, the
 * character filter, the i.e./e.g. replacement and tokenization. The words
 * keep their case; Python's are these words lowercased.
 *
 * @param {string} text
 * @returns {string[]}
 */
export function normalizeAndTokenize(text) {
  let s = stripAccentsAndFilter(normalizeNumbers(text));
  s = s.replace(/i\.e\./gi, "that is");
  s = s.replace(/e\.g\./gi, "for example");
  return tweetTokenize(s);
}
