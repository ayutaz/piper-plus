import { expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const models = JSON.parse(readFileSync(new URL("./models.json", import.meta.url), "utf8"));
// The zs-v1 base, CAM++ encoder and its config, pinned apart from models.json.
export const zeroShot = JSON.parse(
  readFileSync(new URL("./zero-shot-models.json", import.meta.url), "utf8")
);
const ortVersion = JSON.parse(
  readFileSync(new URL("../../node_modules/onnxruntime-web/package.json", import.meta.url), "utf8")
).version;

// Pinned sentences whose audio must last at least MIN_PINNED_SECONDS. Both
// collapse when their G2P silently falls back (zh: missing pinyin dictionaries,
// under 0.5 s; ja: Rust WASM not loaded, a few hundred samples).
export const PINNED_TEXT = {
  ja: "こんにちは、今日はとても良い天気ですね。",
  zh: "你好，今天天气非常好。",
};

// VITS samples durations, so correct audio varies between runs: the CSS10
// Chinese sentence measured 0.99 to 1.78 s in CI (2026-10-23). The threshold
// sits between that and the silent fallbacks above.
export const MIN_PINNED_SECONDS = 0.6;

/** Substitute pinned local bytes for CDN URLs; ORT.run and G2P stay real. */
export async function routeCdnToLocal(page) {
  const cdn = async (route) => {
    const url = new URL(route.request().url());
    let target;
    const ort = url.pathname.match(/\/onnxruntime-web@([^/]+)\/dist\/(.*)/);
    const piper = url.pathname.match(/\/piper-plus@[^/]+\/(.*)/);
    const g2p = url.pathname.match(/\/@piper-plus\/g2p@[^/]+\/(.*)/);
    if (ort) {
      expect(ort[1], "Demo/README runtime must match installed browser runtime").toBe(ortVersion);
      target = `/ort/${ort[2]}`;
    } else if (piper) {
      // jsDelivr refuses files over 50 MB, so the bundled G2P WASM would 403.
      expect(url.hostname, "piper-plus must not be loaded from jsDelivr").not.toBe(
        "cdn.jsdelivr.net"
      );
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
  };
  await page.route("https://cdn.jsdelivr.net/npm/**", cdn);
  await page.route("https://unpkg.com/**", cdn);
}

/** Serve the pinned public models from test/browser/models. */
export async function routeModelsToLocal(page) {
  await page.route("https://huggingface.co/**", async (route) => {
    const url = new URL(route.request().url());
    const zsPrefix = `/${zeroShot.repo}/resolve/${zeroShot.revision}/`;
    if (url.pathname.startsWith(zsPrefix)) {
      const file = zeroShot.files.find((f) => url.pathname === zsPrefix + f.remote);
      if (!file) {
        throw new Error(`Unexpected zero-shot request: ${url}`);
      }
      const response = await route.fetch({
        url: `http://127.0.0.1:4173/models/${zeroShot.key}/${file.local}`,
      });
      await route.fulfill({
        response,
        headers: { ...response.headers(), "access-control-allow-origin": "*" },
      });
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

/** CDN and model routing, unless PIPER_PLUS_DEMO_URL points at a deployed demo. */
export async function localDistribution(page) {
  if (process.env.PIPER_PLUS_DEMO_URL) {
    return;
  }
  await routeCdnToLocal(page);
  await routeModelsToLocal(page);
}

/**
 * Collect page errors, console errors and the piper-plus warning that means a
 * language was dropped. That warning used to be the only sign of the silent
 * Japanese fallback, so a passing test must not emit it.
 */
export function observeErrors(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") {
      errors.push(m.text());
    } else if (m.type() === "warning" && m.text().includes("[piper-plus] Rust WASM G2P failed")) {
      errors.push(m.text());
    }
  });
  return errors;
}

/** Record every HTTP response with status >= 400. */
export function observeFailedResponses(page) {
  const failed = [];
  page.on("response", (r) => {
    if (r.status() >= 400) {
      failed.push(`${r.status()} ${r.url()}`);
    }
  });
  return failed;
}

/**
 * On a page that only carries the README importmap, initialize Tsukuyomi and
 * synthesize `text`. Returns `{ seconds, finite, nonzero }` or `{ error }`.
 */
export async function synthesizeWithReadmeImportmap(page, text, language) {
  return page.evaluate(
    async ({ text, language }) => {
      try {
        const { PiperPlus } = await import("piper-plus");
        const ort = await import("onnxruntime-web");
        const piper = await PiperPlus.initialize({ model: "tsukuyomi", ort });
        try {
          const audio = await piper.synthesize(text, language ? { language } : {});
          const samples = audio.samples;
          return {
            seconds: samples.length / audio.sampleRate,
            finite: samples.every(Number.isFinite),
            nonzero: samples.some((x) => x !== 0),
          };
        } finally {
          piper.dispose();
        }
      } catch (error) {
        return { error: String(error?.message ?? error) };
      }
    },
    { text, language }
  );
}

/** Fetch an <audio> element's WAV and return its bytes and decoded stats. */
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
