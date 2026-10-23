/**
 * G2P golden parity for `@piper-plus/g2p` (runtime "js-g2p").
 *
 * Compares `G2P.encode(text, phonemeIdMap, { language })` with
 * `tests/fixtures/g2p/phoneme_test_cases_golden.json`, which Python's
 * `MultilingualPhonemizer` generates with the case language as the Latin
 * default. `encode()` is what the `piper-plus` npm package calls through its
 * JS G2P adapter: for English always, and for every language when the model
 * has neither Japanese nor Chinese (the Rust WASM G2P is not loaded then).
 * The browser path with the Rust WASM G2P is compared by the `wasm` runtime
 * test in `src/wasm/openjtalk-web/test/js/test-g2p-golden-parity.js`.
 *
 * The output is phoneme IDs, so the test gives every phoneme its own ID and
 * reads the tokens back from the IDs between the PAD separators. The IDs are
 * where this package applies the PUA encoding (`phonemize()` still spells
 * multi-codepoint phonemes such as `eː` out), so they are one PUA character
 * here and spelled out in the golden. Only the golden side is mapped with
 * `pua.json`, so output that forgets the PUA encoding still fails.
 *
 * Cases known to differ are listed in `tests/fixtures/g2p/known_divergences.json`
 * for the `js-g2p` runtime. A difference that is not listed fails, and so does a
 * listed case that now matches, so the list shrinks as the linked issues are
 * fixed. English words that must never phonemize to nothing are listed in
 * `tests/fixtures/g2p/english_no_drop_words.json` and follow the same rule.
 *
 * Nothing is skipped: an empty comparison fails. Japanese needs the OpenJTalk
 * WASM and Korean is absent from the golden, so both are left out.
 *
 * Run: node --test test/test-g2p-golden-parity.js
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { G2P } from "../src/index.js";

const RUNTIME = "js-g2p";
const LANGUAGES = ["en", "es", "fr", "pt", "sv", "zh"];
const NOT_SPOKEN = new Set([" ", ".", ",", "!", "?", ";", ":", "'", '"', "-"]);

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..", "..", "..");

function loadJson(relative) {
  return JSON.parse(readFileSync(join(REPO_ROOT, relative), "utf-8"));
}

/** Maps the golden spelling of multi-codepoint phonemes to their PUA character. */
function puaTable() {
  const doc = loadJson("src/python/g2p/piper_plus_g2p/data/pua.json");
  return new Map(
    doc.entries.map((e) => [e.token, String.fromCodePoint(parseInt(e.codepoint, 16))])
  );
}

const PUA = puaTable();
const PUA_SPELLING = new Map([...PUA].map(([token, ch]) => [ch, token]));

/**
 * Tokens are joined with one space; a word boundary token " " therefore
 * appears as three spaces (two empty parts when split).
 */
function splitPhonemes(s) {
  const tokens = [];
  if (!s) {
    return tokens;
  }
  let emptyParts = 0;
  for (const part of s.split(" ")) {
    if (part) {
      emptyParts = 0;
      tokens.push(part);
    } else if (++emptyParts === 2) {
      emptyParts = 0;
      tokens.push(" ");
    }
  }
  return tokens;
}

/** Spells PUA characters as the golden does, for readable failure messages. */
function spell(tokens) {
  return tokens.map((t) => PUA_SPELLING.get(t) ?? t).join(" ");
}

/**
 * A phoneme_id_map with one ID per character, wide enough that the encoder
 * does not drop a symbol the G2P emits (unknown symbols are skipped).
 */
function buildIdMap() {
  const map = { _: [0], "^": [1], $: [2] };
  const symbols = new Map([
    [0, "_"],
    [1, "^"],
    [2, "$"],
  ]);
  const add = (ch) => {
    if (!(ch in map)) {
      map[ch] = [symbols.size];
      symbols.set(symbols.size, ch);
    }
  };
  const ranges = [
    [0x20, 0x7e], // ASCII
    [0xa0, 0x36f], // Latin-1, Latin Extended, IPA, modifiers, combining marks
    [0x370, 0x3ff], // Greek (θ, β, χ)
    [0x1d00, 0x1dbf], // Phonetic extensions
    [0x2000, 0x206f], // General punctuation
    [0x3000, 0x303f], // CJK punctuation
    [0x4e00, 0x9fff], // CJK ideographs (character-level Chinese)
    [0xe000, 0xe0ff], // PUA phonemes
    [0xff00, 0xffef], // Fullwidth forms
  ];
  for (const [first, last] of ranges) {
    for (let cp = first; cp <= last; cp++) {
      add(String.fromCodePoint(cp));
    }
  }
  for (const ch of PUA.values()) {
    add(ch);
  }
  return { map, symbols };
}

const ID_MAP = buildIdMap();

/**
 * Read the tokens back from `BOS (ids PAD)* EOS`. A token the encoder could
 * not map shows as "∅".
 */
function decodeIds(phonemeIds) {
  const tokens = [];
  let current = "";
  for (const id of phonemeIds.slice(1, -1)) {
    if (id === 0) {
      tokens.push(current || "∅");
      current = "";
    } else {
      current += ID_MAP.symbols.get(id) ?? `<${id}>`;
    }
  }
  if (current) {
    tokens.push(current);
  }
  return tokens;
}

function listsRuntime(entry) {
  return Array.isArray(entry.runtimes) && entry.runtimes.includes(RUNTIME);
}

describe(`G2P golden parity: @piper-plus/g2p (runtime "${RUNTIME}")`, async () => {
  const g2p = await G2P.create({ languages: LANGUAGES });

  function phonemize(text, language) {
    return decodeIds(g2p.encode(text, ID_MAP.map, { language }).phonemeIds);
  }

  it("matches the Python golden except the cases in known_divergences.json", () => {
    const registry = loadJson("tests/fixtures/g2p/known_divergences.json");
    const golden = loadJson("tests/fixtures/g2p/phoneme_test_cases_golden.json");
    const known = new Set(
      registry.divergences.filter(listsRuntime).map((e) => JSON.stringify([e.language, e.input]))
    );

    let verified = 0;
    let knownCount = 0;
    const failures = [];
    for (const c of golden.test_cases) {
      if (!LANGUAGES.includes(c.language)) {
        continue;
      }
      const expected = splitPhonemes(c.expected_phonemes).map((t) => PUA.get(t) ?? t);
      let actual = null;
      let error = null;
      try {
        actual = phonemize(c.input, c.language);
      } catch (e) {
        error = e;
      }
      const matches = actual !== null && JSON.stringify(expected) === JSON.stringify(actual);
      verified++;

      const label = `[${c.language}] ${JSON.stringify(c.input)}`;
      const listed = known.has(JSON.stringify([c.language, c.input]));
      if (matches && listed) {
        failures.push(`${label} now matches; remove it from known_divergences.json`);
      } else if (!matches && listed) {
        knownCount++;
      } else if (!matches) {
        const got = error ? `(phonemize failed: ${error.message})` : spell(actual);
        failures.push(`${label}\n  expected: ${c.expected_phonemes}\n  actual:   ${got}`);
      }
    }

    assert.ok(verified > 0, "no golden case compared");
    assert.equal(
      failures.length,
      0,
      `${failures.length} failure(s), ${knownCount} known, ${verified} cases:\n${failures.join("\n")}`
    );
  });

  it("does not drop the English words in english_no_drop_words.json", () => {
    const list = loadJson("tests/fixtures/g2p/english_no_drop_words.json");
    const knownDrops = new Set(list.known_drops.filter(listsRuntime).map((e) => e.word));

    let checked = 0;
    const failures = [];
    for (const word of list.words) {
      let tokens = [];
      try {
        tokens = phonemize(word, "en");
      } catch {
        tokens = [];
      }
      const spoken = tokens.some((t) => !NOT_SPOKEN.has(t) && t !== "∅");
      checked++;
      const listed = knownDrops.has(word);
      if (spoken && listed) {
        failures.push(`'${word}' is now spoken; remove it from known_drops`);
      } else if (!spoken && !listed) {
        failures.push(`'${word}' produced no phoneme: '${spell(tokens)}'`);
      }
    }

    assert.ok(checked > 0, "english_no_drop_words.json has no words");
    assert.equal(failures.length, 0, failures.join("\n"));
  });
});
