import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { localDistribution, observeErrors, readWav, zeroShot } from "./fixtures.mjs";

const LANGUAGES = ["ja", "en", "zh", "es", "fr", "pt"];
const ENCODER_URL = `https://huggingface.co/${zeroShot.repo}/resolve/${zeroShot.revision}/${
  zeroShot.files.find((f) => f.local === "campplus.onnx").remote
}`;

// Cosine between CAM++ embeddings of two WAV blobs, computed in the page with
// the same SpeakerEncoder the demo uses.
async function similarity(page, referenceUrl, outputUrl) {
  return page.evaluate(
    async ({ encoderUrl, referenceUrl, outputUrl }) => {
      if (!window.__zsCheckEncoder) {
        const { SpeakerEncoder } = await import("./src/index.js");
        window.__zsCheckEncoder = await SpeakerEncoder.initialize({
          modelUrl: encoderUrl,
          ort: globalThis.ort,
          frontEnd: "kaldi-fbank",
        });
      }
      async function embed(url) {
        const context = new AudioContext();
        const buffer = await context.decodeAudioData(await (await fetch(url)).arrayBuffer());
        await context.close();
        return window.__zsCheckEncoder.encode(buffer.getChannelData(0), buffer.sampleRate);
      }
      const [a, b] = [await embed(referenceUrl), await embed(outputUrl)];
      return a.reduce((sum, v, i) => sum + v * b[i], 0);
    },
    { encoderUrl: ENCODER_URL, referenceUrl, outputUrl }
  );
}

async function synthesize(page, language, text) {
  await page.locator("#zsLanguage").selectOption(language);
  if (text !== undefined) {
    await page.locator("#zsText").fill(text);
  }
  const previous = await page.locator("#zsAudio").getAttribute("src");
  await page.locator("#zsSynthesizeBtn").click();
  // The click handler disables the button before its first await.
  await expect(page.locator("#zsSynthesizeBtn")).toBeEnabled();
  return previous;
}

test("Zero-shot demo speaks six languages in the reference voice", async ({ page }, info) => {
  const errors = observeErrors(page);
  await localDistribution(page);
  await page.goto("./");
  await expect(page.locator("#synthesizeBtn")).toBeEnabled();

  // Reference: the CSS10 voice, synthesized by the main demo on the same page.
  await page.locator('[data-lang="ja"]').click();
  await page
    .locator("#inputText")
    .fill("こんにちは、今日はとても良い天気ですね。散歩に行きましょう。");
  await page.locator("#synthesizeBtn").click();
  await expect(page.locator("#synthesizeBtn")).toBeEnabled();
  await expect(page.locator("#status")).toHaveClass(/success/);
  const reference = await readWav(page.locator("#audioPlayer"));
  await writeFile(info.outputPath("reference.wav"), reference.bytes);

  await page.locator("#zsLoadBtn").click();
  await expect(page.locator("#zsControls")).toBeVisible();
  // The embedding must reach the model and steer it. Reference B is
  // reference A slowed to 70 %, a deeper voice; outputs conditioned on B must
  // be clearly closer to B than outputs conditioned on A are. Absolute
  // similarity varies with language and sampling noise (0.2-0.6 measured), so
  // the check compares against a fixed reference instead of thresholding.
  // Only B is a usable yardstick: zs-v1 cannot fully reach the deeper voice,
  // so B's outputs stay near A and "closer to A" failed 1 of 5 runs. Measured
  // margin toward B with three takes: 0.13-0.22 over five runs; 0.01 when the
  // demo does not pass the embedding. A is uploaded last so it stays loaded.
  const deeper = Buffer.from(reference.bytes);
  const deeperRate = Math.round(deeper.readUInt32LE(24) * 0.7);
  deeper.writeUInt32LE(deeperRate, 24);
  deeper.writeUInt32LE(deeperRate * deeper.readUInt16LE(32), 28);
  // Three takes per reference, averaged, with a longer sentence: single takes
  // swing by about 0.1 with sampling noise.
  const contrastText = "今日はとても良い天気ですね。公園まで散歩に行きましょう。";
  const refs = {};
  const outs = { A: [], B: [] };
  for (const [name, bytes] of [
    ["B", deeper],
    ["A", reference.bytes],
  ]) {
    await page
      .locator("#zsFile")
      .setInputFiles({ name: `${name}.wav`, mimeType: "audio/wav", buffer: bytes });
    await expect(page.locator("#zsStatus")).toHaveClass(/success/);
    refs[name] = await page.locator("#zsReferencePlayer").getAttribute("src");
    for (let take = 0; take < 3; take++) {
      await synthesize(page, "ja", contrastText);
      await expect(page.locator("#zsStatus")).toHaveClass(/success/);
      outs[name].push(await page.locator("#zsAudio").getAttribute("src"));
    }
  }
  const mean = async (ref, urls) => {
    let sum = 0;
    for (const url of urls) {
      sum += await similarity(page, ref, url);
    }
    return sum / urls.length;
  };
  const toB = { fromB: await mean(refs.B, outs.B), fromA: await mean(refs.B, outs.A) };
  console.log("speaker similarity to reference B", toB);
  expect(toB.fromB - toB.fromA, "conditioning on B moves the voice toward B").toBeGreaterThan(0.05);

  // Every language synthesizes with reference A loaded.
  for (const language of LANGUAGES) {
    const previous = await synthesize(page, language);
    await expect(page.locator("#zsStatus")).toHaveClass(/success/);
    const outputUrl = await page.locator("#zsAudio").getAttribute("src");
    expect(outputUrl, `${language}: no new audio`).not.toBe(previous);
    const wav = await readWav(page.locator("#zsAudio"));
    expect(wav.bytes.toString("ascii", 0, 4)).toBe("RIFF");
    expect(wav.bytes.readUInt32LE(24)).toBe(22050);
    expect(wav.stats.finite).toBe(true);
    expect(wav.stats.nonzero).toBe(true);
    const seconds = wav.stats.frames / wav.stats.rate;
    console.log(language, { seconds: seconds.toFixed(2) });
    // Each sample text takes 1.5-3.5 s; a missing dictionary collapses it.
    expect(seconds, `${language} duration`).toBeGreaterThan(1);
    expect(seconds, `${language} duration`).toBeLessThan(6);
    await writeFile(info.outputPath(`zero-shot-${language}.wav`), wav.bytes);
  }

  // zs-v1 never learned these; the demo stops with the reason instead of
  // dropping them silently.
  for (const [language, text, shown] of [
    ["pt", "Minha irmã chegou.", "ã"],
    ["fr", "Il fait nuit.", "ɥ"],
    ["ja", "안녕하세요", "안"],
  ]) {
    const previous = await synthesize(page, language, text);
    await expect(page.locator("#zsStatus")).toHaveClass(/error/);
    await expect(page.locator("#zsStatus")).toContainText(shown);
    expect(await page.locator("#zsAudio").getAttribute("src")).toBe(previous);
  }

  await page.screenshot({ path: info.outputPath("zero-shot.png"), fullPage: true });
  // The rejections above log nothing; only real failures reach the console.
  expect(errors).toEqual([]);
});
