// Shared Playwright helpers: serve pinned local bytes for CDN and Hugging Face
// URLs (ORT.run and G2P stay real), and collect page errors.
import { expect } from "@playwright/test";
import { readFileSync } from "node:fs";

export const models = JSON.parse(readFileSync(new URL("./models.json", import.meta.url), "utf8"));
export const zeroShot = JSON.parse(
  readFileSync(new URL("./zero-shot-models.json", import.meta.url), "utf8")
);
const ortVersion = JSON.parse(
  readFileSync(new URL("../../node_modules/onnxruntime-web/package.json", import.meta.url), "utf8")
).version;

async function fulfillLocal(route, target) {
  const response = await route.fetch({ url: `http://127.0.0.1:4173${target}` });
  await route.fulfill({
    response,
    headers: { ...response.headers(), "access-control-allow-origin": "*" },
  });
}

export async function localDistribution(page) {
  if (process.env.PIPER_PLUS_DEMO_URL) {
    return;
  }
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
    await fulfillLocal(route, target);
  });
  await page.route("https://huggingface.co/**", async (route) => {
    const url = new URL(route.request().url());
    const zsPrefix = `/${zeroShot.repo}/resolve/${zeroShot.revision}/`;
    if (url.pathname.startsWith(zsPrefix)) {
      const file = zeroShot.files.find((f) => url.pathname === zsPrefix + f.remote);
      if (!file) {
        throw new Error(`Unexpected zero-shot request: ${url}`);
      }
      await fulfillLocal(route, `/models/${zeroShot.key}/${file.local}`);
      return;
    }
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
      await fulfillLocal(route, `/models/${model.key}/${file}`);
    }
  });
}

export function observeErrors(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") {
      errors.push(m.text());
    }
  });
  return errors;
}

// Fetch an <audio> element's WAV and return its bytes and decoded stats.
export async function readWav(locator) {
  const wav = await locator.evaluate(async (el) => {
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
    return { bytes: Array.from(bytes), stats };
  });
  return { bytes: Buffer.from(wav.bytes), stats: wav.stats };
}
