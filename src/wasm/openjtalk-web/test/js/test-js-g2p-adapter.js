/**
 * JsG2pAdapter dropped-symbol reporting.
 *
 * The npm package depends on `@piper-plus/g2p` by semver range, so a consumer
 * can get a release whose encode() predates `droppedSymbols` (0.4.2 and
 * earlier). findDroppedSymbols() then threw for every JS G2P language, which
 * broke the zero-shot demo only in the installed-tarball run of CI. The
 * adapter works the symbols out itself, so this must hold for both shapes.
 *
 * Run: node --test test/js/test-js-g2p-adapter.js
 */

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import { PUA_MAP } from "@piper-plus/g2p";
import { JsG2pAdapter } from "../../src/phonemizer/js-g2p-adapter.js";

const PHONEME_ID_MAP = {
  _: [0],
  "^": [1],
  $: [2],
  h: [3],
  a: [4],
  [PUA_MAP["tʃ"]]: [5],
};

// The public surface of @piper-plus/g2p 0.4.2: encode() has no
// droppedSymbols, phonemizeWithProsody() returns the tokens.
function g2pLike042(tokens) {
  return {
    phonemizeWithProsody: () => ({ tokens, prosody: tokens.map(() => null), language: "en" }),
    encode: () => ({ phonemeIds: [1, 3, 0, 2], prosodyFlat: null }),
    dispose() {},
  };
}

describe("JsG2pAdapter droppedSymbols", () => {
  it("reports symbols missing from the map with a g2p that predates droppedSymbols", () => {
    const adapter = new JsG2pAdapter(g2pLike042(["h", "ɥ", "a", "ɥ", "ã"]), PHONEME_ID_MAP, ["en"]);
    const { phonemeIds, droppedSymbols } = adapter.encode("ignored", "en");
    assert.deepEqual(droppedSymbols, ["ɥ", "ã"]);
    assert.deepEqual(phonemeIds, [1, 3, 0, 2]);
  });

  it("treats a token whose PUA form is in the map as known", () => {
    const adapter = new JsG2pAdapter(g2pLike042(["tʃ", "a"]), PHONEME_ID_MAP, ["en"]);
    assert.deepEqual(adapter.encode("ignored", "en").droppedSymbols, []);
  });

  it("uses the g2p's own report when it has one", () => {
    const g2p = {
      ...g2pLike042(["h"]),
      encode: () => ({ phonemeIds: [1, 2], prosodyFlat: null, droppedSymbols: ["ʁ"] }),
    };
    const adapter = new JsG2pAdapter(g2p, PHONEME_ID_MAP, ["fr"]);
    assert.deepEqual(adapter.encode("ignored", "fr").droppedSymbols, ["ʁ"]);
  });

  it("matches the real G2P for English", async () => {
    const adapter = await JsG2pAdapter.create(["en"], PHONEME_ID_MAP);
    try {
      const { droppedSymbols } = adapter.encode("Hello world", "en");
      assert.ok(droppedSymbols.includes(" "), droppedSymbols.join(" "));
      assert.ok(!droppedSymbols.includes("h"), droppedSymbols.join(" "));
    } finally {
      adapter.dispose();
    }
  });
});
