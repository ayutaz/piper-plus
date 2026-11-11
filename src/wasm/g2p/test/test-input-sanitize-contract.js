/**
 * Control characters are stripped before a text is read.
 *
 * Contract: docs/spec/input-sanitize-contract.toml (runtime "npm").
 * Cases: tests/fixtures/g2p/input_sanitize_cases.json, read here directly.
 *
 * Regression focus: #934 (2026-11) stripped control characters in the
 * Python G2P only. Here a NUL inside "hola" split the word in two, a NUL
 * inside "och" or a form feed between two words hid Swedish from the
 * language detection, and a NUL inside "Python" between Chinese text made
 * it spelled out letter by letter.
 *
 * Japanese needs the OpenJTalk WASM, which these tests do not load: the
 * JapaneseG2P case records the text that reaches OpenJTalk instead.
 */

import { describe, it, before } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import * as pkg from "../src/index.js";

const { G2P, JapaneseG2P, ChineseG2P, stripControlChars } = pkg;

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(
  readFileSync(
    join(
      __dirname,
      "..",
      "..",
      "..",
      "..",
      "tests",
      "fixtures",
      "g2p",
      "input_sanitize_cases.json"
    ),
    "utf8"
  )
);

/** Every exported class with a phonemize method, and the language it reads. */
const CLASS_LANGUAGES = {
  JapaneseG2P: "ja",
  EnglishG2P: "en",
  ChineseG2P: "zh",
  KoreanG2P: "ko",
  SpanishG2P: "es",
  FrenchG2P: "fr",
  PortugueseG2P: "pt",
  EuropeanPortugueseG2P: "pt-PT",
  SwedishG2P: "sv",
};

const FACADE_LANGUAGES = ["en", "zh", "ko", "es", "fr", "pt", "pt-PT", "sv"];

// G2P.phonemize() throws for pt-PT whatever the text: EuropeanPortugueseG2P
// .phonemize() returns a token array, not { tokens }. A separate bug; its
// phonemizeWithProsody() is tested for pt-PT.
const PHONEMIZE_BROKEN = new Set(["pt-PT"]);

function wordCases(language) {
  return FIXTURE.word_cases.filter((c) => c.language === language);
}

describe("stripControlChars", () => {
  it("matches every strip case", () => {
    assert.ok(FIXTURE.strip_cases.length > 10);
    for (const c of FIXTURE.strip_cases) {
      assert.equal(stripControlChars(c.input), c.expected, c.name);
    }
  });

  it("is idempotent", () => {
    for (const c of FIXTURE.strip_cases) {
      const once = stripControlChars(c.input);
      assert.equal(stripControlChars(once), once, c.name);
    }
  });

  it("keeps lone surrogates and passes a non-string through", () => {
    assert.equal(stripControlChars("a\uD800\u0000b"), "a\uD800b");
    assert.equal(stripControlChars(undefined), undefined);
    assert.equal(stripControlChars(null), null);
  });
});

describe("input sanitizing", () => {
  let g2p;
  before(async () => {
    g2p = await G2P.create({ languages: FACADE_LANGUAGES });
  });

  it("lists every exported phonemizer class", () => {
    const classes = Object.entries(pkg)
      .filter(([, v]) => typeof v === "function" && typeof v.prototype?.phonemize === "function")
      .map(([name]) => name)
      .filter((name) => name !== "G2P"); // the facade, tested below
    assert.ok(classes.length >= 9, `found only ${classes}`);
    const missing = classes.filter((name) => !(name in CLASS_LANGUAGES));
    assert.deepEqual(missing, [], "add these classes to CLASS_LANGUAGES");
  });

  it("each language class reads a dirty word like the clean one", () => {
    for (const [name, language] of Object.entries(CLASS_LANGUAGES)) {
      if (language === "ja") continue; // below, without OpenJTalk
      const instance = g2p._phonemizers.get(language);
      assert.ok(instance, `${name} (${language}) is not loaded`);
      assert.equal(instance.constructor.name, name);
      const cases = wordCases(language);
      assert.ok(cases.length > 0, language);
      for (const c of cases) {
        const label = `${name} ${c.control}`;
        assert.deepEqual(instance.phonemize(c.dirty), instance.phonemize(c.clean), label);
        assert.deepEqual(
          instance.phonemizeWithProsody(c.dirty),
          instance.phonemizeWithProsody(c.clean),
          label
        );
      }
    }
  });

  it("JapaneseG2P hands the stripped text to OpenJTalk", () => {
    const ja = new JapaneseG2P();
    const seen = [];
    ja._synthesizeLabelsAndExtract = (text) => {
      seen.push(text);
      return { tokens: ["a"], prosody: [null] };
    };
    for (const c of wordCases("ja")) {
      ja.phonemize(c.dirty);
      ja.phonemizeWithProsody(c.dirty);
      assert.deepEqual(seen.splice(0), [c.clean, c.clean], c.control);
    }
  });

  it("G2P reads a dirty text like the clean one", () => {
    const cases = [
      ...FIXTURE.word_cases.filter(
        (c) => FACADE_LANGUAGES.includes(c.language) || c.language === "multilingual"
      ),
      ...FIXTURE.pipeline_cases,
    ];
    assert.ok(cases.length > 30);
    for (const c of cases) {
      const options = c.language === "multilingual" ? {} : { language: c.language };
      const label = `${c.language} ${c.control ?? c.name} ${JSON.stringify(c.clean)}`;
      if (!PHONEMIZE_BROKEN.has(c.language)) {
        assert.deepEqual(g2p.phonemize(c.dirty, options), g2p.phonemize(c.clean, options), label);
      }
      assert.deepEqual(
        g2p.phonemizeWithProsody(c.dirty, options),
        g2p.phonemizeWithProsody(c.clean, options),
        label
      );
      assert.equal(g2p.detectLanguage(c.dirty), g2p.detectLanguage(c.clean), label);
      assert.deepEqual(g2p.segmentText(c.dirty), g2p.segmentText(c.clean), label);
    }
  });

  it("G2P detects Swedish in the stripped text", async () => {
    const sv = await G2P.create({ languages: ["en", "sv"] });
    for (const [clean, dirty] of [
      ["och", "o\u0000ch"],
      ["hello och", "hello\foch"],
      ["hello och", "hello\u0085och"],
    ]) {
      const label = JSON.stringify(dirty);
      assert.equal(sv.detectLanguage(clean), "sv", label);
      assert.equal(sv.detectLanguage(dirty), "sv", label);
      assert.deepEqual(sv.segmentText(dirty), sv.segmentText(clean), label);
      assert.deepEqual(sv.phonemize(dirty), sv.phonemize(clean), label);
      assert.deepEqual(sv.phonemizeWithProsody(dirty), sv.phonemizeWithProsody(clean), label);
    }
  });

  it("reads a text of only control characters like an empty text", () => {
    for (const language of FACADE_LANGUAGES) {
      assert.deepEqual(
        g2p.phonemizeWithProsody("\u0000\u0001\u007f\u009f", { language }),
        g2p.phonemizeWithProsody("", { language }),
        language
      );
    }
  });

  it("ChineseG2P reads the English run between Chinese text in the stripped text", () => {
    const zh = g2p._phonemizers.get("zh");
    assert.ok(zh instanceof ChineseG2P);
    const clean = zh.phonemizeEmbeddedEnglish("Python");
    assert.ok(clean.tokens.length > 0);
    for (const dirty of ["Py\u0000thon", "\u0007Python\u001b", "Pyth\u009fon"]) {
      assert.deepEqual(zh.phonemizeEmbeddedEnglish(dirty), clean, JSON.stringify(dirty));
      assert.deepEqual(
        zh.phonemizeEmbeddedEnglishWithProsody(dirty),
        zh.phonemizeEmbeddedEnglishWithProsody("Python"),
        JSON.stringify(dirty)
      );
    }
  });
});
