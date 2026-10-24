/**
 * G2P golden parity for the `piper-plus` npm package (runtime "wasm").
 *
 * Compares the phonemes a browser user gets from `piper-plus` with
 * `tests/fixtures/g2p/phoneme_test_cases_golden.json`, which Python's
 * `MultilingualPhonemizer` generates with the case language as the Latin
 * default.
 *
 * What is compared is the browser path itself: `PiperPlus.initialize()` with
 * a model whose `language_id_map` holds all eight languages, the Rust WASM G2P
 * loaded from `dist/rust-wasm/` by its default URL, the pinyin dictionaries
 * fetched from `assets/`, and then `_textToPhonemeIds(text, language)` -- the
 * call `synthesize({ language })` makes before inference. Only `fetch` (served
 * from the package files on disk) and the ONNX session are stand-ins. With
 * such a model the package routes `en` to the JS G2P (`@piper-plus/g2p`) and
 * the other languages to the Rust WASM G2P; the routing is asserted below so
 * the record in `known_divergences.json` keeps describing the same code. The
 * zh cases with digits ("0", "100", "123") also check that the Rust WASM gets
 * the CMU dictionary of `@piper-plus/g2p` for the English segment it splits
 * out of Chinese text, instead of reading it digit by digit (#847).
 *
 * The output is phoneme IDs, so the test gives every phoneme its own ID and
 * reads the tokens back from the IDs between the PAD separators. The IDs are
 * where both G2Ps apply the PUA encoding, so multi-codepoint phonemes (rr, tʃ,
 * tone3) are one PUA character here and spelled out in the golden. Only the
 * golden side is mapped with `pua.json`, so output that forgets the PUA
 * encoding still fails.
 *
 * Cases known to differ are listed in `tests/fixtures/g2p/known_divergences.json`
 * for the `wasm` runtime. A difference that is not listed fails, and so does a
 * listed case that now matches, so the list shrinks as the linked issues are
 * fixed. English words that must never phonemize to nothing are listed in
 * `tests/fixtures/g2p/english_no_drop_words.json` and follow the same rule.
 *
 * Nothing is skipped: a missing WASM build, a missing dictionary or an empty
 * comparison fails. Build the WASM first with `npm run build:wasm:multilingual`
 * (CI: the `npm-package-tests` job of ci.yml). Japanese needs the OpenJTalk
 * dictionary and Korean is absent from the golden, so both are left out.
 *
 * Run: node --test test/js/test-g2p-golden-parity.js
 */

import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { PiperPlus } from "../../src/index.js";
import { RustWasmAdapter } from "../../src/phonemizer/rust-wasm-adapter.js";
import { JsG2pAdapter } from "../../src/phonemizer/js-g2p-adapter.js";

const RUNTIME = "wasm";
const LANGUAGES = ["en", "es", "fr", "pt", "sv", "zh"];
/** Which phonemizer the package uses for each compared language. */
const EXPECTED_ROUTING = {
  en: JsG2pAdapter,
  es: RustWasmAdapter,
  fr: RustWasmAdapter,
  pt: RustWasmAdapter,
  sv: RustWasmAdapter,
  zh: RustWasmAdapter,
};
const NOT_SPOKEN = new Set([" ", ".", ",", "!", "?", ";", ":", "'", '"', "-"]);

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..", "..", "..", "..");
const WASM_DIR = join(__dirname, "..", "..", "dist", "rust-wasm");

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

/**
 * A phoneme_id_map with one ID per character, wide enough that neither G2P
 * drops a symbol it emits (both skip symbols missing from the map).
 */
function buildIdMap(pua) {
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
    [0x4e00, 0x9fff], // CJK ideographs (character-level fallback)
    [0xe000, 0xe0ff], // PUA phonemes
    [0xff00, 0xffef], // Fullwidth forms
  ];
  for (const [first, last] of ranges) {
    for (let cp = first; cp <= last; cp++) {
      add(String.fromCodePoint(cp));
    }
  }
  for (const ch of pua.values()) {
    add(ch);
  }
  return { map, symbols };
}

/**
 * Read the tokens back from `BOS [PAD] (ids PAD)* EOS`. The Rust encoder
 * writes a PAD after BOS and the JS encoder does not; a token whose symbols
 * were all dropped shows as "∅".
 */
function decodeIds(phonemeIds, symbols, padAfterBos) {
  const body = phonemeIds.slice(padAfterBos ? 2 : 1, -1);
  const tokens = [];
  let current = "";
  for (const id of body) {
    if (id === 0) {
      tokens.push(current || "∅");
      current = "";
    } else {
      current += symbols.get(id) ?? `<${id}>`;
    }
  }
  if (current) {
    tokens.push(current);
  }
  return tokens;
}

/** Spells PUA characters as the golden does, for readable failure messages. */
function spell(tokens) {
  return tokens.map((t) => PUA_SPELLING.get(t) ?? t).join(" ");
}

function listsRuntime(entry) {
  return Array.isArray(entry.runtimes) && entry.runtimes.includes(RUNTIME);
}

// ---------------------------------------------------------------------------
// Browser stand-ins: package files served from disk, a fake ONNX session.
// ---------------------------------------------------------------------------

const MODEL_URL = "https://golden-parity.invalid/model.onnx";
const PUA = puaTable();
const PUA_SPELLING = new Map([...PUA].map(([token, ch]) => [ch, token]));
const ID_MAP = buildIdMap(PUA);
const CONFIG = {
  audio: { sample_rate: 22050 },
  inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
  phoneme_type: "multilingual",
  num_speakers: 1,
  num_languages: 8,
  // extended_language_id_map (Python id_maps.py): the 8-language layout.
  language_id_map: { ja: 0, en: 1, zh: 2, es: 3, fr: 4, pt: 5, sv: 6, ko: 7 },
  phoneme_id_map: ID_MAP.map,
};

async function servePackageFiles(input) {
  const url = new URL(typeof input === "object" && input.url ? input.url : String(input));
  if (url.href === `${MODEL_URL}.json`) {
    return new globalThis.Response(JSON.stringify(CONFIG), {
      headers: { "content-type": "application/json" },
    });
  }
  if (url.protocol === "file:") {
    try {
      const bytes = await readFile(fileURLToPath(url));
      const type = url.pathname.endsWith(".wasm") ? "application/wasm" : "application/octet-stream";
      return new globalThis.Response(bytes, { headers: { "content-type": type } });
    } catch {
      return new globalThis.Response(null, { status: 404, statusText: "Not Found" });
    }
  }
  throw new Error(`unexpected fetch in G2P golden parity test: ${url.href}`);
}

const fakeOrt = {
  InferenceSession: {
    create: async () => ({
      inputNames: ["input", "input_lengths", "scales", "lid"],
      outputNames: ["output"],
      release: async () => {},
    }),
  },
  Tensor: class {
    constructor(type, data, dims) {
      this.type = type;
      this.data = data;
      this.dims = dims;
    }
  },
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe(`G2P golden parity: piper-plus npm (runtime "${RUNTIME}")`, () => {
  let piper;
  const warnings = [];
  const origFetch = globalThis.fetch;
  const origWarn = console.warn;

  before(async () => {
    assert.ok(
      existsSync(join(WASM_DIR, "piper_plus_wasm.js")) &&
        existsSync(join(WASM_DIR, "piper_plus_wasm_bg.wasm")),
      `Rust WASM G2P is not built in ${WASM_DIR}; run npm run build:wasm:multilingual`
    );
    globalThis.fetch = servePackageFiles;
    console.warn = (...args) => warnings.push(args.join(" "));
    try {
      piper = await PiperPlus.initialize({ model: MODEL_URL, ort: fakeOrt });
    } finally {
      console.warn = origWarn;
    }
  });

  after(() => {
    globalThis.fetch = origFetch;
    piper?.dispose();
  });

  it("loads the Rust WASM G2P and the pinyin dictionaries without warnings", () => {
    assert.deepEqual(warnings, []);
    assert.equal(piper._unavailableLanguages.size, 0);
  });

  it("routes each compared language to the expected phonemizer", () => {
    for (const [language, adapter] of Object.entries(EXPECTED_ROUTING)) {
      const phonemizer = piper._phonemizer._phonemizers.get(language);
      assert.ok(
        phonemizer instanceof adapter,
        `${language} is phonemized by ${phonemizer?.constructor?.name}, not ${adapter.name}`
      );
    }
  });

  async function phonemize(text, language) {
    const phonemizer = piper._phonemizer._phonemizers.get(language);
    const { phonemeIds } = await piper._textToPhonemeIds(text, language);
    return decodeIds(phonemeIds, ID_MAP.symbols, phonemizer instanceof RustWasmAdapter);
  }

  it("matches the Python golden except the cases in known_divergences.json", async () => {
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
        actual = await phonemize(c.input, c.language);
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

  it("does not drop the English words in english_no_drop_words.json", async () => {
    const list = loadJson("tests/fixtures/g2p/english_no_drop_words.json");
    const knownDrops = new Set(list.known_drops.filter(listsRuntime).map((e) => e.word));

    let checked = 0;
    const failures = [];
    for (const word of list.words) {
      let tokens = [];
      try {
        tokens = await phonemize(word, "en");
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
