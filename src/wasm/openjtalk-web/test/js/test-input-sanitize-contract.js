/**
 * PiperPlus strips control characters first, before SSML detection, the
 * language detection and sentence splitting.
 *
 * Contract: docs/spec/input-sanitize-contract.toml (runtime "npm").
 * Cases: tests/fixtures/g2p/input_sanitize_cases.json, read here directly.
 *
 * Regression focus: a control character before `<speak>` made SSML read as
 * plain text (tags and all), one inside "och" hid Swedish from the language
 * detection, and the Rust WASM G2P (ja / zh) got the text unstripped. The
 * phonemizer and the ONNX session are mocks: these tests record the text
 * that reaches them.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

globalThis.ort = {
  Tensor: class {
    constructor(type, data, dims) {
      this.type = type;
      this.data = data;
      this.dims = dims;
    }
  },
};

const { PiperPlus, stripControlChars } = await import("../../src/index.js");

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(
  readFileSync(
    join(
      __dirname,
      "..",
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

/** A PiperPlus whose phonemizer and session record what they are given. */
function recordingInstance() {
  const seen = [];
  const instance = new PiperPlus();
  instance._config = {
    audio: { sample_rate: 22050 },
    inference: { noise_scale: 0.4, length_scale: 1.0, noise_w: 0.5 },
    phoneme_id_map: { _: [0], "^": [1], $: [2], a: [3] },
  };
  instance._phonemizer = {
    detectLanguage: (text) => {
      seen.push(["detect", text]);
      return "es";
    },
    dispose: () => {},
    supportedLanguages: ["es"],
  };
  instance._textToPhonemeIds = async (text, language) => {
    seen.push(["phonemize", text, language]);
    return { phonemeIds: [1, 3, 3, 3, 2], prosodyFeatures: null, droppedSymbols: [] };
  };
  instance._infer = async () => ({ audio: new Float32Array(256), durations: null });
  instance._ort = globalThis.ort;
  instance._initialized = true;
  return { instance, seen };
}

const EMBEDDING = new Float32Array(192).fill(0.1);

/** Every public method that takes a text, called the same way. */
const METHODS = {
  synthesize: (p, text) => p.synthesize(text),
  synthesizeSsml: (p, text) => p.synthesizeSsml(text),
  synthesizeWithVoiceCloning: (p, text) => p.synthesizeWithVoiceCloning(text, EMBEDDING),
  synthesizeFromReferenceAudio: (p, text) =>
    p.synthesizeFromReferenceAudio({
      text,
      referenceWav: new Float32Array(16000),
      encoder: { encode: async () => EMBEDDING },
    }),
  findDroppedSymbols: (p, text) => p.findDroppedSymbols(text),
  synthesizeStreaming: (p, text) => p.synthesizeStreaming(text),
};

async function record(method, text) {
  const { instance, seen } = recordingInstance();
  await METHODS[method](instance, text);
  return seen;
}

describe("PiperPlus input sanitizing", () => {
  it("exports the rule and matches every strip case", () => {
    for (const c of FIXTURE.strip_cases) {
      assert.equal(stripControlChars(c.input), c.expected, c.name);
    }
  });

  it("lists every public method that takes a text", () => {
    const methods = Object.getOwnPropertyNames(PiperPlus.prototype).filter(
      (name) => /^(synthesize|find)/.test(name) && typeof PiperPlus.prototype[name] === "function"
    );
    assert.deepEqual(methods.sort(), Object.keys(METHODS).sort(), "add new methods to METHODS");
  });

  for (const method of Object.keys(METHODS)) {
    it(`${method} reads a dirty text like the clean one`, async () => {
      const cases = [
        ...FIXTURE.word_cases.filter((c) => c.language !== "ja"),
        ...FIXTURE.pipeline_cases,
        { clean: "Hola. Adiós.", dirty: "Hola. \u0000Adiós.", control: "after a full stop" },
        { clean: "3.5 metros.", dirty: "3.\u00005 metros.", control: "in a decimal" },
      ];
      assert.ok(cases.length > 30);
      for (const c of cases) {
        const label = `${c.control ?? c.name} ${JSON.stringify(c.dirty)}`;
        const clean = await record(method, c.clean);
        assert.ok(clean.length > 0, label);
        assert.deepEqual(await record(method, c.dirty), clean, label);
      }
    });
  }

  it("synthesize detects SSML after a control character", async () => {
    const clean = await record("synthesize", "<speak>Hola</speak>");
    assert.deepEqual(
      clean.filter(([kind]) => kind === "phonemize").map(([, text]) => text),
      ["Hola"]
    );
    for (const dirty of ["\u0007<speak>Hola</speak>", "\u0000 <speak>Ho\u0000la</speak>"]) {
      assert.deepEqual(await record("synthesize", dirty), clean, JSON.stringify(dirty));
    }
  });

  it("strips the control characters a character reference puts in an SSML segment", async () => {
    // parseSsml decodes &#0; and &#x0C;, after the text was stripped.
    for (const method of ["synthesize", "synthesizeSsml"]) {
      const clean = await record(method, "<speak>hola adiós</speak>");
      for (const dirty of ["<speak>ho&#0;la adiós</speak>", "<speak>hola&#x0C;adiós</speak>"]) {
        assert.deepEqual(await record(method, dirty), clean, `${method} ${dirty}`);
      }
    }
  });

  it("a text of only control characters is an empty text", async () => {
    for (const method of Object.keys(METHODS)) {
      const { instance } = recordingInstance();
      await assert.rejects(
        METHODS[method](instance, "\u0000\u0001\u007f\u009f"),
        /is required/,
        method
      );
    }
  });

  it("synthesizeFromReferenceAudio does not encode the reference for a text of only control characters", async () => {
    const { instance } = recordingInstance();
    let encoded = 0;
    const encoder = {
      encode: async () => {
        encoded += 1;
        return EMBEDDING;
      },
    };
    await assert.rejects(
      instance.synthesizeFromReferenceAudio({
        text: "\u0000\u0001",
        referenceWav: new Float32Array(16000),
        encoder,
      }),
      /text is required/
    );
    assert.equal(encoded, 0);
  });

  it("has the same rule as @piper-plus/g2p", async () => {
    // piper-plus keeps its own copy (see src/sanitize.js); CI links the
    // @piper-plus/g2p of this repository, which exports the original.
    const g2p = await import("@piper-plus/g2p");
    assert.equal(typeof g2p.stripControlChars, "function", "link the local @piper-plus/g2p");
    for (let cp = 0; cp <= 0xffff; cp += 1) {
      const text = `a${String.fromCharCode(cp)}b`;
      assert.equal(stripControlChars(text), g2p.stripControlChars(text), `U+${cp.toString(16)}`);
    }
  });
});
