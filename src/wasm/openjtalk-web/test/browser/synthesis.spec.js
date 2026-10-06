import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { writeFile } from "node:fs/promises";
const models = JSON.parse(readFileSync(new URL("./models.json", import.meta.url), "utf8"));
const ortVersion = JSON.parse(
  readFileSync(new URL("../../node_modules/onnxruntime-web/package.json", import.meta.url), "utf8")
).version;

async function localDistribution(page) {
  if (process.env.PIPER_PLUS_DEMO_URL) {
    return;
  }
  // Substitute pinned local bytes for network URLs; ORT.run and G2P stay real.
  await page.route("https://cdn.jsdelivr.net/npm/**", async (route) => {
    const url = new URL(route.request().url());
    let target;
    const ort = url.pathname.match(/\/onnxruntime-web@([^/]+)\/dist\/(.*)/);
    const piper = url.pathname.match(/\/piper-plus@[^/]+\/(.*)/);
    const g2p = url.pathname.match(/\/@piper-plus\/g2p@[^/]+\/(.*)/);
    if (ort) {
      expect(ort[1], "Demo/README runtime must match installed browser runtime").toBe(ortVersion);
      target = `/ort/${ort[2]}`;
    } else if (piper) {
      target = `/${piper[1]}`;
    } else if (g2p) {
      target = `/g2p/${g2p[1]}`;
    } else {
      throw new Error(`Unexpected CDN import: ${url}`);
    }
    const response = await route.fetch({ url: `http://127.0.0.1:4173${target}` });
    await route.fulfill({
      response,
      headers: { ...response.headers(), "access-control-allow-origin": "*" },
    });
  });
  await page.route("https://huggingface.co/**", async (route) => {
    const url = new URL(route.request().url());
    const model = models.find((m) => url.pathname.includes(m.repo));
    if (!model) {
      throw new Error(`Unexpected model request: ${url}`);
    }
    if (url.pathname.startsWith("/api/models/")) {
      await route.fulfill({
        json: { siblings: [{ rfilename: model.onnx }, { rfilename: "config.json" }] },
      });
    } else {
      const file = url.pathname.endsWith(".json") ? "model.onnx.json" : "model.onnx";
      const response = await route.fetch({
        url: `http://127.0.0.1:4173/models/${model.key}/${file}`,
      });
      await route.fulfill({
        response,
        headers: { ...response.headers(), "access-control-allow-origin": "*" },
      });
    }
  });
}

function observeErrors(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") {
      errors.push(m.text());
    }
  });
  return errors;
}

test("CSS10 official demo synthesizes and plays all six languages", async ({ page }, info) => {
  const errors = observeErrors(page);
  await localDistribution(page);
  await page.goto("./");
  await expect(page.locator("#synthesizeBtn")).toBeEnabled();
  const texts = {
    ja: "こんにちは、今日はとても良い天気ですね。",
    en: "Hello world! This is a test of speech synthesis.",
    zh: "你好，今天天气非常好。",
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
    if (language === "zh") {
      // This pinned sentence collapses to <0.5s when the pinyin dictionaries
      // are missing and Chinese silently falls back to character passthrough.
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
