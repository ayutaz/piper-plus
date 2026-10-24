/**
 * CJK punctuation contract (Issue #823) for `@piper-plus/g2p`.
 *
 * Reads `tests/fixtures/g2p/cjk_punctuation_cases.json`, which
 * `scripts/build_cjk_punctuation_fixture.py` builds from
 * `docs/spec/cjk-punctuation-contract.toml`. Every runtime has the same test,
 * so a detector or Latin-segment rewrite that drifts from the contract fails in
 * the runtime that drifted.
 *
 * `G2P` phonemizes a whole text with one language, so the Latin-segment
 * rewrite applies to the text `G2P.phonemize()` hands to a Latin-script G2P.
 * The Chinese cases are checked on the segmentation (their phonemes are
 * compared with the Python golden in test-g2p-golden-parity.js): the sentence
 * stays one Chinese segment, and the Chinese segment sits right before the
 * English one, which is what the ZH-EN loanword dispatch needs.
 * Japanese needs the OpenJTalk WASM, so the `G2P` instance leaves it out.
 *
 * Run: node --test test/test-cjk-punctuation-contract.js
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { G2P, UnicodeLanguageDetector, normalizeCjkPunctuationForLatin } from "../src/index.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
// test/ -> g2p/ -> wasm/ -> src/ -> repo
const REPO_ROOT = join(__dirname, "..", "..", "..", "..");
const FIXTURE = JSON.parse(
  readFileSync(join(REPO_ROOT, "tests", "fixtures", "g2p", "cjk_punctuation_cases.json"), "utf-8")
);

function makeDetector() {
  return new UnicodeLanguageDetector(FIXTURE.detector_languages, {
    defaultLatinLanguage: FIXTURE.default_latin,
  });
}

describe("CJK punctuation contract: fixture", () => {
  it("is not empty", () => {
    assert.ok(FIXTURE.neutral.length > 100);
    assert.equal(FIXTURE.fullwidth_latin.length, 52);
  });
});

describe("CJK punctuation contract: UnicodeLanguageDetector", () => {
  const detector = makeDetector();

  for (const contextHasKana of [false, true]) {
    it(`classifies every neutral code point as neutral (contextHasKana=${contextHasKana})`, () => {
      const wrong = FIXTURE.neutral
        .map((c) => [c.code_point, detector.detectChar(c.char, contextHasKana)])
        .filter(([, lang]) => lang !== null);
      assert.deepEqual(wrong, []);
    });
  }

  it("keeps the fullwidth Latin letters Latin", () => {
    const wrong = FIXTURE.fullwidth_latin
      .filter((c) => detector.detectChar(c.char) !== FIXTURE.default_latin)
      .map((c) => c.code_point);
    assert.deepEqual(wrong, []);
  });

  it("keeps a Chinese sentence in one Chinese segment", () => {
    assert.deepEqual(detector.segmentText("你好，今天天气很好。"), [
      { language: "zh", text: "你好，今天天气很好。" },
    ]);
    assert.deepEqual(detector.segmentText("北京欢迎你。"), [
      { language: "zh", text: "北京欢迎你。" },
    ]);
  });

  it("puts the Chinese segment right before English after a Chinese comma", () => {
    // The ZH-EN dispatch needs the Chinese segment right before the English
    // one; a Japanese segment for "，" used to sit between them.
    assert.deepEqual(detector.segmentText("你好，GPS"), [
      { language: "zh", text: "你好，" },
      { language: "en", text: "GPS" },
    ]);
  });
});

describe("CJK punctuation contract: normalizeCjkPunctuationForLatin", () => {
  it("rewrites every neutral code point as the fixture says", () => {
    const wrong = FIXTURE.neutral
      .map((c) => [c.code_point, normalizeCjkPunctuationForLatin(c.char), c.latin])
      .filter(([, got, want]) => got !== want);
    assert.deepEqual(wrong, []);
  });

  it("leaves everything else alone, the fullwidth Latin letters included", () => {
    for (const text of ["Hello, world!", "café", "ＡＢＣ", "你好", "こんにちは", ""]) {
      assert.equal(normalizeCjkPunctuationForLatin(text), text);
    }
  });
});

describe("CJK punctuation contract: G2P", async () => {
  const g2p = await G2P.create({
    languages: FIXTURE.detector_languages.filter((lang) => lang !== "ja"),
  });

  // g2p_en and its ports delete characters they do not know, which used to
  // join "Hello，world" into one word.
  const cases = [
    ["Hello，world", "Hello,world", {}],
    ["Hello、world。", "Hello,world.", {}],
    ["Hola，amigo！", "Hola,amigo!", {}],
    ["Hola，amigo！", "Hola,amigo!", { language: "es" }],
    ["I have ３ cats．", "I have 3 cats.", {}],
  ];
  for (const [cjk, ascii, options] of cases) {
    it(`reads ${JSON.stringify(cjk)} like ${JSON.stringify(ascii)} ${JSON.stringify(options)}`, () => {
      assert.deepEqual(g2p.phonemize(cjk, options), g2p.phonemize(ascii, options));
      assert.deepEqual(
        g2p.phonemizeWithProsody(cjk, options),
        g2p.phonemizeWithProsody(ascii, options)
      );
    });
  }
});
