/**
 * English G2P with the bundled CMU Pronouncing Dictionary (Issue #828).
 *
 * `data/cmudict_data.json` is a byte copy of the canonical
 * `src/rust/piper-plus-g2p/data/cmudict_data.json` (also checked by
 * `scripts/check_cmudict_mirrors.py`). It is loaded lazily: importing the
 * package does not read it, `G2P.create()` reads it only when English is
 * enabled, and `EnglishG2P` reads it on `initialize()` or, where the file
 * system can be read synchronously (Node), on the first `phonemize()`.
 * Elsewhere (a browser) an uninitialised `EnglishG2P` throws instead of
 * reading English without its dictionary.
 *
 * The pipeline after the dictionary follows the Rust port
 * (`src/rust/piper-plus-g2p/src/english.rs`): morphological fallback, then
 * `-`/`.` split, apostrophe retry, CamelCase split and letter names, so no
 * word is dropped. The expected phonemes are Python's (the golden file).
 *
 * Run: node --test test/test-english-cmudict.js
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

import { EnglishG2P, loadCmuDict } from "../src/en/index.js";
import { G2P } from "../src/index.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = join(__dirname, "..");
const REPO_ROOT = join(PKG_ROOT, "..", "..", "..");
const EN_URL = pathToFileURL(join(PKG_ROOT, "src", "en", "index.js")).href;
const INDEX_URL = pathToFileURL(join(PKG_ROOT, "src", "index.js")).href;

/** "a b _ c": tokens separated by spaces, "_" standing for the word boundary " ". */
function tokens(s) {
  return s.split(" ").map((t) => (t === "_" ? " " : t));
}

/**
 * Runs an ES module snippet in a fresh Node process and returns the JSON on
 * the last line it prints (earlier lines may be log messages).
 */
function runIsolated(code) {
  const out = execFileSync(process.execPath, ["--input-type=module", "-e", code], {
    cwd: PKG_ROOT,
    encoding: "utf-8",
  });
  const lines = out.trim().split(/\r?\n/);
  return JSON.parse(lines[lines.length - 1] ?? "null");
}

describe("bundled CMU dictionary", () => {
  it("is a byte copy of the canonical cmudict_data.json", () => {
    const bundled = readFileSync(join(PKG_ROOT, "data", "cmudict_data.json"));
    const canonical = readFileSync(
      join(REPO_ROOT, "src", "rust", "piper-plus-g2p", "data", "cmudict_data.json")
    );
    assert.ok(bundled.equals(canonical), "data/cmudict_data.json differs from the canonical");
  });

  it("loadCmuDict() resolves to the dictionary and caches it", async () => {
    const dict = await loadCmuDict();
    assert.equal(dict.get("hello"), "HH AH0 L OW1");
    assert.equal(dict.get("brown"), "B R AW1 N");
    assert.equal(dict.size, 123455);
    assert.equal(await loadCmuDict(), dict, "second call returns the cached dictionary");
  });
});

describe("EnglishG2P reads words from the CMU dictionary", async () => {
  const en = await EnglishG2P.create();

  const cases = [
    ["The quick brown fox jumps.", "ð ə _ k w ˈ ɪ k _ b ɹ ˈ a ʊ n _ f ˈ ɑ k s _ d ʒ ˈ ʌ m p s ."],
    ["dog", "d ˈ ɔ ː ɡ"],
    ["bird", "b ˈ ɜ ː d"],
    ["knight", "n ˈ a ɪ t"],
    ["queue", "k j ˈ u ː"],
    ["colonel", "k ˈ ɜ ː n ə l"],
    ["Mississippi", "m ˌ ɪ s ɪ s ˈ ɪ p i ː"],
    ["She doesn't know.", "ʃ i ː _ d ˈ ʌ z ə n t _ n ˈ o ʊ ."],
    ["It's 3 o'clock.", "ˈ ɪ t s _ θ ɹ ˈ i ː _ ə k l ˈ ɑ k ."],
    ["100", "w ˈ ʌ n _ h ˈ ʌ n d ɹ ə d"],
    ["3.14", "θ ɹ ˈ i ː _ p ˈ ɔ ɪ n t _ f ˈ ɔ ː ɹ t ˈ i ː n"],
    ["e.g. and i.e.", "f ˈ ɔ ː ɹ _ ɪ ɡ z ˈ æ m p ə l _ ə n d _ ð æ t _ ˈ ɪ z"],
    ["café", "k ə f ˈ e ɪ"],
    ["naïve", "n ˌ a ɪ ˈ i ː v"],
    ["'quote'", "' _ k w ˈ o ʊ t _ '"],
    ["uh-huh", "ˈ ʌ h ˈ ʌ"],
  ];
  for (const [text, expected] of cases) {
    it(`${JSON.stringify(text)} matches Python`, () => {
      assert.deepEqual(en.phonemize(text).tokens, tokens(expected));
    });
  }

  it("phonemizeWithProsody gives Python's a2 (stress) and a3 (word length)", () => {
    // Python aligns function words with the source words before number
    // expansion: "three" takes the flag of "of", "of" that of "us".
    const { tokens: t, prosody } = en.phonemizeWithProsody("the 3 of us");
    assert.deepEqual(t, tokens("ð ə _ θ ɹ i ː _ ʌ v _ ˈ ʌ s"));
    assert.deepEqual(
      prosody.map((p) => p.a1),
      new Array(t.length).fill(0)
    );
    assert.deepEqual(
      prosody.map((p) => p.a2),
      [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0]
    );
    assert.deepEqual(
      prosody.map((p) => p.a3),
      [2, 2, 0, 4, 4, 4, 4, 0, 2, 2, 0, 2, 2, 2]
    );
  });

  it("phonemize() keeps null prosody", () => {
    const { tokens: t, prosody } = en.phonemize("hello world");
    assert.equal(prosody.length, t.length);
    assert.ok(prosody.every((p) => p === null));
  });
});

describe("package entry point", () => {
  it("re-exports the English loader and normalizer", async () => {
    const root = await import("../src/index.js");
    const en = await import("../src/en/index.js");
    for (const name of [
      "EnglishG2P",
      "loadCmuDict",
      "isCmuDictLoaded",
      "normalizeNumbers",
      "normalizeAndTokenize",
    ]) {
      assert.equal(typeof root[name], "function", name);
      assert.equal(root[name], en[name], name);
    }
  });
});

describe("EnglishG2P with an injected dictionary", () => {
  it("accepts a plain object or a Map", () => {
    for (const cmuDict of [{ cat: "K AE1 T" }, new Map([["cat", "K AE1 T"]])]) {
      const en = new EnglishG2P({ cmuDict });
      assert.ok(en.isInitialized);
      assert.deepEqual(en.phonemize("cat").tokens, tokens("k ˈ æ t"));
    }
  });

  it("spells a word missing from the dictionary as one word", () => {
    const en = new EnglishG2P({ cmuDict: { hello: "HH AH0 L OW1" } });
    assert.deepEqual(
      en.phonemize("hello xyz").tokens,
      tokens("h ə l ˈ o ʊ _ ˈ ɛ k s w ˈ a ɪ z ˈ i ː")
    );
    assert.deepEqual(en.phonemize("TTS").tokens, tokens("t ˈ i ː t ˈ i ː ˈ ɛ s"));
  });

  it("does not read Object.prototype names as dictionary entries", () => {
    const en = new EnglishG2P({ cmuDict: {} });
    for (const word of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
      const { tokens: t } = en.phonemize(word);
      assert.ok(t.length > 0, word);
      assert.ok(
        t.every((x) => typeof x === "string" && [...x].length === 1),
        `${word}: ${JSON.stringify(t)}`
      );
    }
  });

  it("uses the morphological fallback before spelling", () => {
    const en = new EnglishG2P({
      cmuDict: { run: "R AH1 N", make: "M EY1 K", cat: "K AE1 T", walk: "W AO1 K" },
    });
    assert.deepEqual(en.phonemize("running").tokens, tokens("ɹ ˈ ʌ n ɪ ŋ"));
    assert.deepEqual(en.phonemize("making").tokens, tokens("m ˈ e ɪ k ɪ ŋ"));
    assert.deepEqual(en.phonemize("cats").tokens, tokens("k ˈ æ t z"));
    assert.deepEqual(en.phonemize("walked").tokens, tokens("w ˈ ɔ ː k d"));
  });

  it("splits at - and ., retries without apostrophes and splits CamelCase", () => {
    const en = new EnglishG2P({
      cmuDict: {
        foo: "F UW1",
        bar: "B AA1 R",
        rocknroll: "R AA1 K N R OW1 L",
        chat: "CH AE1 T",
        phone: "F OW1 N",
        i: "AY1",
      },
    });
    assert.deepEqual(en.phonemize("foo-bar").tokens, tokens("f ˈ u ː b ˈ ɑ ː ɹ"));
    assert.deepEqual(en.phonemize("foo.bar").tokens, tokens("f ˈ u ː b ˈ ɑ ː ɹ"));
    assert.deepEqual(en.phonemize("rock'n'roll").tokens, tokens("ɹ ˈ ɑ k n ɹ ˈ o ʊ l"));
    assert.deepEqual(en.phonemize("ChatGPT").tokens, tokens("t ʃ ˈ æ t d ʒ ˈ i ː p ˈ i ː t ˈ i ː"));
    assert.deepEqual(en.phonemize("iPhone").tokens, tokens("ˈ a ɪ f ˈ o ʊ n"));
  });

  it("speaks symbol-only words one character per phoneme", () => {
    const en = new EnglishG2P({ cmuDict: { wait: "W EY1 T", now: "N AW1" } });
    const { tokens: t, prosody } = en.phonemizeWithProsody("wait . . . now");
    assert.deepEqual(t, tokens("w ˈ e ɪ t _ . _ . _ . _ n ˈ a ʊ"));
    assert.deepEqual(
      prosody.map((p) => p.a3),
      [4, 4, 4, 4, 4, 0, 5, 5, 5, 5, 5, 0, 3, 3, 3, 3]
    );
  });
});

describe("lazy loading", () => {
  it("importing the package does not load the dictionary", () => {
    const result = runIsolated(`
      const en = await import(${JSON.stringify(EN_URL)});
      await import(${JSON.stringify(INDEX_URL)});
      console.log(JSON.stringify({ loaded: en.isCmuDictLoaded() }));
    `);
    assert.deepEqual(result, { loaded: false });
  });

  it("G2P.create() loads it only when English is enabled", () => {
    const result = runIsolated(`
      const en = await import(${JSON.stringify(EN_URL)});
      const { G2P } = await import(${JSON.stringify(INDEX_URL)});
      await G2P.create({ languages: ["es", "fr"] });
      const withoutEn = en.isCmuDictLoaded();
      const g2p = await G2P.create({ languages: ["en"] });
      const withEn = en.isCmuDictLoaded();
      console.log(JSON.stringify({ withoutEn, withEn, tokens: g2p.phonemize("dog", { language: "en" }).tokens }));
    `);
    assert.deepEqual(result, { withoutEn: false, withEn: true, tokens: tokens("d ˈ ɔ ː ɡ") });
  });

  it("G2P.create() passes an injected cmuDict to English", async () => {
    const g2p = await G2P.create({ languages: ["en"], cmuDict: { dog: "D AA1 G" } });
    assert.deepEqual(g2p.phonemize("dog", { language: "en" }).tokens, tokens("d ˈ ɑ ɡ"));
  });

  it("in Node, an uninitialised EnglishG2P reads the dictionary on first use", () => {
    const result = runIsolated(`
      const en = await import(${JSON.stringify(EN_URL)});
      const g = new en.EnglishG2P();
      const before = { initialized: g.isInitialized, loaded: en.isCmuDictLoaded() };
      const t = g.phonemize("dog").tokens;
      console.log(JSON.stringify({ before, tokens: t, after: g.isInitialized }));
    `);
    assert.deepEqual(result, {
      before: { initialized: false, loaded: false },
      tokens: tokens("d ˈ ɔ ː ɡ"),
      after: true,
    });
  });

  it("without synchronous file access, an uninitialised EnglishG2P throws until initialize()", () => {
    // A browser has no process.getBuiltinModule: phonemize() cannot read the
    // dictionary synchronously, so it must fail loudly rather than read
    // English without it.
    const result = runIsolated(`
      delete process.getBuiltinModule;
      const en = await import(${JSON.stringify(EN_URL)});
      const g = new en.EnglishG2P();
      let error = null;
      try { g.phonemize("dog"); } catch (e) { error = e.message; }
      await g.initialize();
      console.log(JSON.stringify({ error, tokens: g.phonemize("dog").tokens }));
    `);
    assert.match(result.error ?? "", /CMU dictionary is not loaded/);
    assert.match(result.error ?? "", /initialize\(\)/);
    assert.deepEqual(result.tokens, tokens("d ˈ ɔ ː ɡ"));
  });

  it("empty input needs no dictionary", () => {
    const result = runIsolated(`
      delete process.getBuiltinModule;
      const en = await import(${JSON.stringify(EN_URL)});
      const g = new en.EnglishG2P();
      console.log(JSON.stringify({ a: g.phonemize("").tokens, b: g.phonemize(null).tokens }));
    `);
    assert.deepEqual(result, { a: [], b: [] });
  });
});
