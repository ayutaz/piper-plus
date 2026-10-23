import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import {
  PINNED_TEXT,
  observeErrors,
  observeFailedResponses,
  routeCdnToLocal,
  routeModelsToLocal,
  synthesizeWithReadmeImportmap,
} from "./fixtures.mjs";

async function localDistribution(page) {
  if (process.env.PIPER_PLUS_DEMO_URL) {
    return;
  }
  await routeCdnToLocal(page);
  await routeModelsToLocal(page);
}

test("CSS10 official demo synthesizes and plays all six languages", async ({ page }, info) => {
  const errors = observeErrors(page);
  await localDistribution(page);
  await page.goto("./");
  await expect(page.locator("#synthesizeBtn")).toBeEnabled();
  const texts = {
    ja: PINNED_TEXT.ja,
    en: "Hello world! This is a test of speech synthesis.",
    zh: PINNED_TEXT.zh,
    es: "Hola, el tiempo es hermoso, vamos a dar un paseo.",
    fr: "Bonjour, comment allez-vous aujourd'hui?",
    pt: "Olá, como você está hoje?",
  };
  for (const [language, text] of Object.entries(texts)) {
    await page.locator(`[data-lang="${language}"]`).click();
    await page.locator("#inputText").fill(text);
    await page.locator("#synthesizeBtn").click();
    await expect(page.locator("#synthesizeBtn")).toBeEnabled();
    await expect(page.locator("#status")).toHaveClass(/success/);
    const wav = await page.locator("#audioPlayer").evaluate(async (el) => {
      const bytes = new Uint8Array(await (await fetch(el.src)).arrayBuffer());
      const context = new AudioContext();
      const decoded = await context.decodeAudioData(bytes.slice().buffer);
      const pcm = decoded.getChannelData(0);
      const stats = {
        frames: decoded.length,
        rate: decoded.sampleRate,
        finite: pcm.every(Number.isFinite),
        nonzero: pcm.some((x) => x !== 0),
      };
      await context.close();
      await el.play();
      return { bytes: Array.from(bytes), stats };
    });
    const bytes = Buffer.from(wav.bytes);
    expect(bytes.toString("ascii", 0, 4)).toBe("RIFF");
    expect(bytes.toString("ascii", 8, 12)).toBe("WAVE");
    expect(bytes.readUInt32LE(24)).toBe(22050);
    expect(wav.stats.frames).toBeGreaterThan(0);
    expect(wav.stats.finite).toBe(true);
    expect(wav.stats.nonzero).toBe(true);
    if (language === "zh" || language === "ja") {
      // These pinned sentences collapse to <0.5s when their G2P silently falls
      // back (zh: missing pinyin dictionaries, ja: Rust WASM not loaded).
      expect(wav.stats.frames / wav.stats.rate).toBeGreaterThan(1);
    }
    await page.waitForFunction(() => document.querySelector("#audioPlayer").currentTime > 0);
    await page.locator("#audioPlayer").evaluate((el) => el.pause());
    await writeFile(info.outputPath(`css10-${language}.wav`), bytes);
    console.log(language, wav.stats);
  }
  await page.screenshot({ path: info.outputPath("demo.png"), fullPage: true });
  expect(errors).toEqual([]);
});

for (const [name, file] of [
  ["importmap", "readme.html"],
  ["Basic Usage", "basic.html"],
]) {
  test(`README ${name} initializes Tsukuyomi and plays real audio`, async ({ page }) => {
    const errors = observeErrors(page);
    await localDistribution(page);
    // Observe real WebAudio start without replacing inference or playback.
    await page.addInitScript(() => {
      const start = window.AudioBufferSourceNode.prototype.start;
      window.AudioBufferSourceNode.prototype.start = function (...args) {
        const samples = this.buffer.getChannelData(0);
        window.__playedAudio = {
          frames: this.buffer.length,
          finite: samples.every(Number.isFinite),
          nonzero: samples.some((x) => x !== 0),
        };
        return start.apply(this, args);
      };
    });
    await page.goto(`./${file}`);
    await page.waitForFunction(() => window.__playedAudio?.frames > 0);
    expect(await page.evaluate(() => window.__playedAudio)).toMatchObject({
      finite: true,
      nonzero: true,
    });
    expect(errors).toEqual([]);
  });
}

// The README example speaks English, which never needs the Rust WASM G2P.
// Japanese through the same importmap is what broke when jsDelivr refused
// the WASM (#818), so check its length, not only that some audio played.
test("README importmap synthesizes Japanese at full length", async ({ page }) => {
  const errors = observeErrors(page);
  const failed = observeFailedResponses(page);
  await localDistribution(page);
  await page.goto("./readme-importmap.html");
  const ja = await synthesizeWithReadmeImportmap(page, PINNED_TEXT.ja);
  expect(ja.error).toBeUndefined();
  expect(ja).toMatchObject({ finite: true, nonzero: true });
  expect(ja.seconds).toBeGreaterThan(1);
  expect(failed).toEqual([]);
  expect(errors).toEqual([]);
});

// When the WASM cannot be fetched, Japanese and Chinese must fail loudly
// while the languages served by the JS G2P keep working (#819).
test("WASM fetch failure rejects Japanese and Chinese but keeps English", async ({ page }) => {
  await localDistribution(page);
  // Registered last, so it runs before the CDN substitution.
  await page.route("**/piper_plus_wasm_bg.wasm", (route) =>
    route.fulfill({ status: 403, body: "File size exceeded the configured limit of 50 MB." })
  );
  await page.goto("./readme-importmap.html");
  for (const [language, text] of Object.entries(PINNED_TEXT)) {
    for (const hint of [language, undefined]) {
      const result = await synthesizeWithReadmeImportmap(page, text, hint);
      expect(result.error, `${language} (language: ${hint ?? "auto"})`).toMatch(
        new RegExp(`Cannot synthesize "${language}": the Rust WASM G2P failed to load`)
      );
    }
  }
  const en = await synthesizeWithReadmeImportmap(page, "Hello, world!", "en");
  expect(en.error).toBeUndefined();
  expect(en.seconds).toBeGreaterThan(0.3);
});
