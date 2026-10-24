/**
 * ZH-EN code-switching: English in Chinese text read as Mandarin pinyin
 * (Issue #384). Port of Rust `phonemize_embedded_english_with_prosody`
 * (`src/rust/piper-plus-g2p/src/chinese.rs`) and Python
 * `ChinesePhonemizer.phonemize_embedded_english`.
 *
 * `data/zh_en_loanword.json` is byte-identical to the Python canonical
 * (CI gate: `scripts/check_loanword_consistency.py`). It is about 5 KB, so it
 * is imported with the module.
 *
 * @module zh/loanword
 */

import loanwordJson from "../../data/zh_en_loanword.json" with { type: "json" };
import { phonemizePinyinSyllables } from "./pinyin.js";

/**
 * @typedef {{
 *   acronyms: Map<string, string[]>,
 *   loanwords: Map<string, string[]>,
 *   letterFallback: Map<string, string[]>,
 * }} ParsedLoanwordData
 */

/** @returns {ParsedLoanwordData} */
function emptyData() {
  return { acronyms: new Map(), loanwords: new Map(), letterFallback: new Map() };
}

/**
 * Parse loanword JSON like Rust `parse_loanword_json`: missing sections are
 * empty and unknown top-level fields are ignored (forward compatibility), but
 * a section that is not an object, or an entry that is not a list of strings,
 * makes the whole file unusable. Then, as Rust's `load_default_loanword_data`
 * does, the data is treated as empty so English falls through to the normal
 * path instead of failing.
 *
 * @param {unknown} data
 * @returns {ParsedLoanwordData}
 */
export function parseLoanwordData(data) {
  const out = emptyData();
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    return out;
  }
  const sections = [
    ["acronyms", out.acronyms],
    ["loanwords", out.loanwords],
    ["letter_fallback", out.letterFallback],
  ];
  for (const [name, target] of sections) {
    const section = /** @type {Record<string, unknown>} */ (data)[name];
    if (section === undefined) {
      continue;
    }
    if (section === null || typeof section !== "object" || Array.isArray(section)) {
      return emptyData();
    }
    for (const [key, value] of Object.entries(section)) {
      if (!Array.isArray(value) || !value.every((s) => typeof s === "string")) {
        return emptyData();
      }
      target.set(key, value);
    }
  }
  return out;
}

/** Bundled default data. */
export const DEFAULT_LOANWORD_DATA = parseLoanwordData(loanwordJson);

/**
 * ASCII alphanumeric runs (Python `[A-Za-z0-9]+`); everything else separates
 * tokens and is dropped.
 *
 * @param {string} text
 * @returns {string[]}
 */
function tokenizeAlnum(text) {
  return text.match(/[A-Za-z0-9]+/g) ?? [];
}

/**
 * Read English text embedded in Chinese as Mandarin pinyin. Lookup order:
 * case-sensitive `loanwords`, then uppercase `acronyms`, then `letter_fallback`
 * letter by letter on the uppercased token (digits are dropped unless listed).
 *
 * @param {string} text
 * @param {ParsedLoanwordData} [data]
 * @returns {{ tokens: string[], prosody: { a1: number, a2: number, a3: number }[] }}
 */
export function phonemizeEmbeddedEnglish(text, data = DEFAULT_LOANWORD_DATA) {
  const syllables = [];
  for (const token of tokenizeAlnum(typeof text === "string" ? text : "")) {
    const loanword = data.loanwords.get(token);
    if (loanword) {
      syllables.push(...loanword);
      continue;
    }
    const upper = token.toUpperCase();
    const acronym = data.acronyms.get(upper);
    if (acronym) {
      syllables.push(...acronym);
      continue;
    }
    for (const ch of upper) {
      const letter = data.letterFallback.get(ch);
      if (letter) {
        syllables.push(...letter);
      }
    }
  }
  return phonemizePinyinSyllables(syllables);
}
