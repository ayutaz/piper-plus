import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { localDistribution, models, observeErrors } from "./harness.js";

// Python (pypinyin) output for the shared G2P fixture. Only Rust compared
// against it, so the browser shipped tone-mark dictionaries that turned every
// syllable into tone 5 while every structural test passed.
const golden = JSON.parse(
  readFileSync(
    new URL("../../../../../tests/fixtures/g2p/phoneme_test_cases_golden.json", import.meta.url),
    "utf8"
  )
);
// Latin letters and digits go through the ZH-EN / number handling instead.
const zhCases = golden.test_cases
  .filter((c) => c.language === "zh" && !/[A-Za-z0-9]/.test(c.input))
  .map((c) => ({ input: c.input, expected: c.expected_phonemes.split(/\s+/).filter(Boolean) }));
const css10 = models.find((m) => m.key === "css10");

test("G2P parity: browser Chinese matches Python and English uses the JS G2P", async ({ page }) => {
  const errors = observeErrors(page);
  await localDistribution(page);
  await page.goto("./");
  // The demo's own initialization finishes first, so the two do not race.
  await expect(page.locator("#synthesizeBtn")).toBeEnabled();

  const result = await page.evaluate(
    async ({ repo, zhCases }) => {
      const { PiperPlus } = await import("./src/index.js");
      const { JsG2pAdapter } = await import("./src/phonemizer/js-g2p-adapter.js");
      const { unmapToken } = await import("@piper-plus/g2p");
      const piper = await PiperPlus.initialize({ model: repo, ort: globalThis.ort });
      try {
        const idToToken = new Map();
        for (const [token, ids] of Object.entries(piper._config.phoneme_id_map)) {
          idToToken.set(ids[0], unmapToken(token));
        }
        const skipped = new Set(["^", "_", "$", " ", ".", ",", "!", "?", ";", ":"]);
        const decode = (ids) =>
          Array.from(ids, (id) => idToToken.get(id) ?? `#${id}`).filter((t) => !skipped.has(t));

        const zh = [];
        for (const { input } of zhCases) {
          const { phonemeIds } = await piper._phonemizer.encode(input, "zh");
          zh.push(decode(phonemeIds));
        }

        // English must not go to the Rust WASM bundle, which has no English
        // dictionary and tokenizes letter by letter.
        const englishText = "Hello world, this is a test.";
        const routed = await piper._phonemizer.encode(englishText, "en");
        const js = await JsG2pAdapter.create(["en"], piper._config.phoneme_id_map);
        const direct = await js.encode(englishText, "en");
        js.dispose?.();
        return {
          zh,
          en: {
            routed: Array.from(routed.phonemeIds),
            direct: Array.from(direct.phonemeIds),
            tokens: decode(routed.phonemeIds),
          },
        };
      } finally {
        piper.dispose();
      }
    },
    { repo: css10.repo, zhCases }
  );

  const mismatches = zhCases
    .map((c, i) => ({ input: c.input, expected: c.expected, actual: result.zh[i] }))
    .filter((c) => c.actual.join(" ") !== c.expected.join(" "));
  expect(mismatches, "zh output differs from the Python golden").toEqual([]);
  expect(zhCases.length).toBeGreaterThan(40);

  expect(result.en.routed, "en must come from the JS G2P").toEqual(result.en.direct);
  expect(result.en.tokens.some((t) => /^[A-Z]$/.test(t)), result.en.tokens.join(" ")).toBe(false);
  expect(errors).toEqual([]);
});
