/** Real ORT Web WASM + PiperPlus inference; shared IDs deliberately bypass G2P. */
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { createHash } from "node:crypto";
import * as ort from "onnxruntime-web";
import { PiperPlus } from "../src/index.js";

const workspace = resolve(process.argv[2]);
const config = JSON.parse(readFileSync(join(workspace, "base.onnx.json"), "utf8"));
const record = JSON.parse(readFileSync(join(workspace, "inputs.json"), "utf8"));
const cases = JSON.parse(readFileSync(join(workspace, "cases.json"), "utf8"));
const outputDir = join(workspace, "wasm");
mkdirSync(outputDir);
ort.env.wasm.numThreads = 1;
const piper = new PiperPlus();
piper._ort = ort;
piper._config = config;
piper._session = await ort.InferenceSession.create(
  readFileSync(join(workspace, "base.onnx")),
  { executionProviders: ["wasm"] },
);
const results = [];
try {
  for (const entry of cases) {
    const { audio } = await piper._infer(entry.phoneme_ids, entry.prosody_features, {
      language: entry.language,
      speakerEmbedding: Float32Array.from(entry.speaker_embedding),
      noiseScale: 0,
      noiseW: 0,
      lengthScale: 1,
    });
    if (!audio.every(Number.isFinite) || !audio.some((x) => x !== 0) ||
        audio.length < config.audio.sample_rate / 10) {
      throw new Error(`Invalid WASM audio: ${entry.key}`);
    }
    const wav = Buffer.alloc(44 + audio.length * 2);
    wav.write("RIFF", 0);
    wav.writeUInt32LE(wav.length - 8, 4);
    wav.write("WAVEfmt ", 8);
    wav.writeUInt32LE(16, 16);
    wav.writeUInt16LE(1, 20);
    wav.writeUInt16LE(1, 22);
    wav.writeUInt32LE(config.audio.sample_rate, 24);
    wav.writeUInt32LE(config.audio.sample_rate * 2, 28);
    wav.writeUInt16LE(2, 32);
    wav.writeUInt16LE(16, 34);
    wav.write("data", 36);
    wav.writeUInt32LE(audio.length * 2, 40);
    let squareSum = 0;
    let peak = 0;
    for (let i = 0; i < audio.length; i++) {
      const sample = Math.round(Math.max(-1, Math.min(1, audio[i])) * 32767);
      wav.writeInt16LE(sample, 44 + i * 2);
      squareSum += sample * sample;
      peak = Math.max(peak, Math.abs(sample));
    }
    writeFileSync(join(outputDir, `${entry.key}.wav`), wav);
    results.push({
      key: entry.key,
      language: entry.language,
      sha256: createHash("sha256").update(wav).digest("hex"),
      frames: audio.length,
      sample_rate: config.audio.sample_rate,
      seconds: audio.length / config.audio.sample_rate,
      rms: Math.sqrt(squareSum / audio.length) / 32768,
      peak: peak / 32768,
      raw_float_finite: true,
    });
  }
} finally {
  await piper._session.release();
}
if (results[0].sha256 !== results.at(-2).sha256) {
  throw new Error("Zero-noise WASM inference was not repeatable");
}
if (results[0].sha256 === results.at(-1).sha256) {
  throw new Error("Changing the speaker embedding had no effect in WASM");
}
const report = {
  ...record,
  runtime: "wasm",
  provider: "ORT Web WASM (Node host, one thread); browser UI and native G2P not tested",
  ort_version: ort.env.versions.web,
  cases: results,
  conditioning_changes_audio: true,
};
writeFileSync(join(outputDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
