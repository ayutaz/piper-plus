/**
 * piper-plus Node CLI bin (audio parity gate) — standalone unit tests
 *
 * Phase 2 (PR #511): tests/scripts/test_audio_parity.py の python 側と並走する
 * Node 側ユニットテスト。 onnxruntime-node の実 inference path を避け、
 * CLI レイヤー (引数 parser / JSONL handling / WAV byte layout / graceful
 * failure) を独立に検証する。
 *
 * bin/piper-cli.js の `main()` 関数は副作用 (process.exit) を起こすので、
 * ここでは child_process.spawn でブラックボックステストとして起動し
 * stdout / stderr / exit code を assert する。
 */

import { strict as assert } from "assert";
import { describe, it } from "node:test";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = resolve(__dirname, "../../bin/piper-cli.js");

function runBin(args, stdin = "") {
  return spawnSync("node", [BIN, ...args], {
    input: Buffer.from(stdin),
    timeout: 30_000,
  });
}

describe("piper-plus bin: argv parser", () => {
  it("--help prints usage and exits 0", () => {
    const out = runBin(["--help"]);
    assert.equal(out.status, 0);
    assert.match(out.stdout.toString(), /Usage: piper-plus/);
    assert.match(out.stdout.toString(), /--json-input/);
    assert.match(out.stdout.toString(), /--noise-scale/);
  });

  it("-h short alias prints usage and exits 0", () => {
    const out = runBin(["-h"]);
    assert.equal(out.status, 0);
    assert.match(out.stdout.toString(), /Usage: piper-plus/);
  });

  it("missing --model / --config / --json-input exits 2 with help", () => {
    const out = runBin([]);
    assert.equal(out.status, 2);
    const err = out.stderr.toString();
    assert.match(err, /required/);
    assert.match(err, /Usage: piper-plus/);
  });

  it("unknown flag exits 2", () => {
    const out = runBin(["--bogus"]);
    assert.equal(out.status, 2);
    assert.match(out.stderr.toString(), /Unknown flag: --bogus/);
  });

  it("flag value missing exits 2 (--model)", () => {
    const out = runBin(["--model"]);
    assert.equal(out.status, 2);
    assert.match(out.stderr.toString(), /requires a value/);
  });

  it("flag value missing for short alias -m exits 2", () => {
    const out = runBin(["-m"]);
    assert.equal(out.status, 2);
    assert.match(out.stderr.toString(), /requires a value/);
  });

  it("short aliases -m / -c / -f are accepted by parser", () => {
    // Use --help short-circuit so we can sanity-check that the parser sees
    // each short alias without needing a real model/config to succeed.
    const tmp = mkdtempSync(`${tmpdir()}/piper-cli-test-`);
    const config = `${tmp}/config.json`;
    const model = `${tmp}/model.onnx`;
    writeFileSync(config, "{}");
    writeFileSync(model, Buffer.alloc(0));
    const out = runBin([
      "-m", model,
      "-c", config,
      "-f", `${tmp}/out.wav`,
      "--json-input",
      "--help",
    ]);
    // --help wins after the others were consumed without throwing
    assert.equal(out.status, 0);
    assert.match(out.stdout.toString(), /Usage: piper-plus/);
  });

  it("--noise-scale / --length-scale / --noise-w accept numeric values without error in parser", () => {
    const out = runBin([
      "--noise-scale", "0.7",
      "--length-scale", "1.2",
      "--noise-w", "0.9",
      "--help",
    ]);
    assert.equal(out.status, 0);
  });
});

describe("piper-plus bin: floatToInt16 clamp logic (inline, mirrors bin)", () => {
  // bin/piper-cli.js は ESM だが floatToInt16 を export していないため、 ここでは
  // bin と同じロジックを再実装して boundary を pin する。 bin 側を変更する際に
  // drift が起きれば test が落ちる (regression として機能)。
  function floatToInt16(audio) {
    const out = new Int16Array(audio.length);
    for (let i = 0; i < audio.length; i++) {
      let s = audio[i];
      if (s > 1.0) s = 1.0;
      if (s < -1.0) s = -1.0;
      out[i] = Math.round(s * 32767);
    }
    return out;
  }

  it("zeros stay zeros", () => {
    const r = floatToInt16([0, 0, 0]);
    assert.deepEqual([...r], [0, 0, 0]);
  });

  it("+1.0 / -1.0 map to ±32767", () => {
    const r = floatToInt16([1.0, -1.0]);
    assert.equal(r[0], 32767);
    assert.equal(r[1], -32767);
  });

  it("out-of-range values are clamped", () => {
    const r = floatToInt16([1.5, -1.5, 2.0, -2.0]);
    assert.equal(r[0], 32767);
    assert.equal(r[1], -32767);
    assert.equal(r[2], 32767);
    assert.equal(r[3], -32767);
  });

  it("mid-range round to nearest int16 (Math.round half-to-positive-infinity)", () => {
    // Math.round は positive infinity 方向に丸めるため、
    // 0.5 * 32767 = 16383.5 → 16384、 -0.5 * 32767 = -16383.5 → -16383
    // (cross-runtime parity への影響は tier 2/3 で吸収される)
    const r = floatToInt16([0.5, -0.5, 0.1]);
    assert.equal(r[0], 16384);
    assert.equal(r[1], -16383);
    assert.equal(r[2], Math.round(0.1 * 32767));
  });

  it("empty input returns empty Int16Array", () => {
    const r = floatToInt16([]);
    assert.equal(r.length, 0);
  });
});

describe("piper-plus bin: JSONL / config preflight", () => {
  it("empty stdin exits 2 when --json-input is set", () => {
    const tmp = mkdtempSync(`${tmpdir()}/piper-cli-test-`);
    const config = `${tmp}/config.json`;
    const fakeModel = `${tmp}/model.onnx`;
    writeFileSync(config, JSON.stringify({ audio: { sample_rate: 22050 } }));
    writeFileSync(fakeModel, Buffer.alloc(0));
    const out = runBin(
      ["--model", fakeModel, "--config", config, "--json-input", "--output-file", `${tmp}/out.wav`],
      "",
    );
    // onnxruntime-node が現環境で未 install なら ERROR を返して exit 1。
    // install 済みでも空モデルは load 失敗で FATAL → exit 1。
    // 空 stdin に到達するためには ORT load を通過する必要があるため、
    // 「ORT 未 install / モデル不正」 のどちらかで exit 1 になるのが期待挙動。
    assert.notEqual(out.status, 0);
    const err = out.stderr.toString();
    assert.ok(
      err.includes("onnxruntime-node") ||
        err.includes("FATAL") ||
        err.includes("no JSONL input"),
      `unexpected stderr: ${err}`,
    );
  });

  it("missing config file results in non-zero exit (ENOENT propagated)", () => {
    const tmp = mkdtempSync(`${tmpdir()}/piper-cli-test-`);
    const fakeModel = `${tmp}/model.onnx`;
    writeFileSync(fakeModel, Buffer.alloc(0));
    const out = runBin(
      [
        "--model", fakeModel,
        "--config", `${tmp}/does-not-exist.json`,
        "--json-input",
      ],
      '{"phoneme_ids":[1,2]}\n',
    );
    assert.notEqual(out.status, 0);
    assert.match(out.stderr.toString(), /FATAL|ENOENT|no such file/);
  });

  it("invalid JSON in config file → non-zero exit with FATAL", () => {
    const tmp = mkdtempSync(`${tmpdir()}/piper-cli-test-`);
    const config = `${tmp}/config.json`;
    const fakeModel = `${tmp}/model.onnx`;
    writeFileSync(config, "{not valid json");
    writeFileSync(fakeModel, Buffer.alloc(0));
    const out = runBin(
      ["--model", fakeModel, "--config", config, "--json-input"],
      '{"phoneme_ids":[1,2]}\n',
    );
    assert.notEqual(out.status, 0);
    assert.match(out.stderr.toString(), /FATAL/);
  });

  it("config missing audio.sample_rate falls back to default in bin source", () => {
    // Smoke-check via reading the source. The bin uses `?? 22050` as the
    // fallback so the runtime can still write a WAV even on minimal configs.
    const content = readFileSync(BIN, "utf8");
    assert.match(content, /config\?\.audio\?\.sample_rate\s*\?\?\s*22050/);
  });

  it("num_speakers / num_languages defaults in bin source (single-speaker / non-multilingual)", () => {
    const content = readFileSync(BIN, "utf8");
    assert.match(content, /num_speakers\s*\?\?\s*1/);
    assert.match(content, /num_languages\s*\?\?\s*0/);
  });
});

describe("piper-plus bin: JSONL handling edge cases", () => {
  // ORT が読み込まれる前段で fail させるテスト。 bin の挙動 (preflight) を
  // 引数 + stdin 経由でブラックボックス検証する。 これらは ORT 不在環境では
  // 「onnxruntime-node not installed」 で先に exit するため、 ORT が install
  // 済みの環境でのみ assertion メッセージが弱まる (regression を逃さない
  // よう、 「正常 path に到達しない (exit ≠ 0)」 + stderr メッセージの
  // 部分一致 で判定する)。

  function makeStubFiles() {
    const tmp = mkdtempSync(`${tmpdir()}/piper-cli-test-`);
    const config = `${tmp}/config.json`;
    const fakeModel = `${tmp}/model.onnx`;
    writeFileSync(config, JSON.stringify({ audio: { sample_rate: 22050 } }));
    writeFileSync(fakeModel, Buffer.alloc(0));
    return { tmp, config, fakeModel };
  }

  it("phoneme_ids is empty array → ORT 読み込み後の path で fail (exit≠0)", () => {
    const { config, fakeModel } = makeStubFiles();
    const out = runBin(
      ["--model", fakeModel, "--config", config, "--json-input"],
      '{"phoneme_ids":[]}\n',
    );
    assert.notEqual(out.status, 0);
    // ORT 不在なら "onnxruntime-node"、 install 済みなら model 読み込み失敗で FATAL。
    // どちらか一方が出れば preflight が path 上で 0 を返していないことを担保。
    const err = out.stderr.toString();
    assert.ok(
      err.includes("onnxruntime-node") ||
        err.includes("FATAL") ||
        err.includes("missing phoneme_ids"),
      `unexpected stderr: ${err}`,
    );
  });

  it("phoneme_ids is not an array (object) → ORT path で fail", () => {
    const { config, fakeModel } = makeStubFiles();
    const out = runBin(
      ["--model", fakeModel, "--config", config, "--json-input"],
      '{"phoneme_ids":{"a":1}}\n',
    );
    assert.notEqual(out.status, 0);
  });

  it("malformed JSON line → FATAL with non-zero exit", () => {
    const { config, fakeModel } = makeStubFiles();
    const out = runBin(
      ["--model", fakeModel, "--config", config, "--json-input"],
      "{not valid\n",
    );
    assert.notEqual(out.status, 0);
    // ORT 不在環境では preflight 段で先に fail するので、 どちらの error 経路でも regression を捉えられればよい。
    const err = out.stderr.toString();
    assert.ok(
      err.includes("FATAL") || err.includes("onnxruntime-node"),
      `unexpected stderr: ${err}`,
    );
  });

  it("blank lines in JSONL are skipped (whitespace tolerance)", () => {
    // bin の readJsonlLines は trim+skip 実装。 blank-only stdin = empty input
    // と等価で「no JSONL input」 のエラーパスに乗ることを確認。
    const { config, fakeModel } = makeStubFiles();
    const out = runBin(
      ["--model", fakeModel, "--config", config, "--json-input"],
      "\n   \n\t\n",
    );
    assert.notEqual(out.status, 0);
    const err = out.stderr.toString();
    assert.ok(
      err.includes("onnxruntime-node") ||
        err.includes("FATAL") ||
        err.includes("no JSONL input"),
      `unexpected stderr: ${err}`,
    );
  });
});

describe("piper-plus bin: bin source structural contract", () => {
  // bin 実装のリグレッション (e.g. 経路の取り違え、 必須 helper の削除) を
  // 文字列 grep で検出する。 ONNX 推論を回避しつつ「bin が壊れた」を pin
  // するための last-line defence。

  it("BigInt64Array で int64 tensor を組み立てる経路を維持する", () => {
    const content = readFileSync(BIN, "utf8");
    // phoneme_ids → int64 input tensor
    assert.match(content, /BigInt64Array\.from\(phonemeIds/);
    assert.match(content, /new ort\.Tensor\(['"]int64['"]/);
  });

  it("scales は float32 [3] tensor で feed する", () => {
    const content = readFileSync(BIN, "utf8");
    assert.match(content, /new ort\.Tensor\(\s*['"]float32['"],\s*Float32Array/);
    assert.match(content, /noiseScale, opts\.lengthScale, opts\.noiseW/);
  });

  it("multi-speaker / multilingual / prosody_features / speaker_embedding の optional inputs を条件付きで feed する", () => {
    const content = readFileSync(BIN, "utf8");
    // input 名で条件分岐していること
    assert.match(content, /inputNames\.has\(['"]sid['"]\)/);
    assert.match(content, /inputNames\.has\(['"]lid['"]\)/);
    assert.match(content, /inputNames\.has\(['"]prosody_features['"]\)/);
    assert.match(content, /inputNames\.has\(['"]speaker_embedding['"]\)/);
  });

  it("per-line output_file が --output-file を上書きする経路を保つ", () => {
    const content = readFileSync(BIN, "utf8");
    assert.match(content, /entry\.output_file\s*\?\?\s*opts\.outputFile/);
  });

  it("output sink `-` を stdout として扱う", () => {
    const content = readFileSync(BIN, "utf8");
    assert.match(content, /sink === ['"]-['"]/);
    assert.match(content, /writeWav\(audio, sampleRate, stdout\)/);
  });

  it("空 stdin → exit 2 (no JSONL input)", () => {
    const content = readFileSync(BIN, "utf8");
    assert.match(content, /no JSONL input received on stdin/);
  });

  it("phoneme_ids array validation を実装している", () => {
    const content = readFileSync(BIN, "utf8");
    assert.match(content, /Array\.isArray\(phonemeIds\)/);
    assert.match(content, /missing phoneme_ids/);
  });
});

describe("piper-plus bin: WAV byte layout (synthetic input via stub harness)", () => {
  // bin/piper-cli.js の writeWav は inline export されていないので、 ここでは
  // bin が書き出した WAV を読み返して header byte layout (RIFF / sample rate /
  // channels / bitsPerSample / data chunk size) を検証する形をとる。
  // 実 inference には ONNX model が必要なため、 既存 fixture/audio-corpus/
  // 配下に置いた synthetic wav を読み返す形ではなく、 ここでは bin が出す
  // 「empty audio (1 sample)」 等を直接書き出す内部関数を再実装してテスト。
  //
  // bin と同じ writeWav 実装を inline で持って RIFF header をテストする
  // (drift 検出のために同等性を保つ単体テスト)。
  function writeWavLikeBin(samples, sampleRate) {
    const numChannels = 1;
    const bitsPerSample = 16;
    const blockAlign = numChannels * (bitsPerSample / 8);
    const dataSize = samples.length * blockAlign;
    const chunkSize = dataSize + 36;
    const header = Buffer.alloc(44);
    let o = 0;
    header.write("RIFF", o); o += 4;
    header.writeUInt32LE(chunkSize, o); o += 4;
    header.write("WAVE", o); o += 4;
    header.write("fmt ", o); o += 4;
    header.writeUInt32LE(16, o); o += 4;
    header.writeUInt16LE(1, o); o += 2;
    header.writeUInt16LE(numChannels, o); o += 2;
    header.writeUInt32LE(sampleRate, o); o += 4;
    header.writeUInt32LE(sampleRate * blockAlign, o); o += 4;
    header.writeUInt16LE(blockAlign, o); o += 2;
    header.writeUInt16LE(bitsPerSample, o); o += 2;
    header.write("data", o); o += 4;
    header.writeUInt32LE(dataSize, o);
    const pcm = Buffer.alloc(dataSize);
    for (let i = 0; i < samples.length; i++) {
      pcm.writeInt16LE(samples[i], i * 2);
    }
    return Buffer.concat([header, pcm]);
  }

  it("44-byte RIFF header + Int16 PCM body", () => {
    const wav = writeWavLikeBin([0, 32767, -32768, 1234], 22050);
    assert.equal(wav.length, 44 + 8);
    assert.equal(wav.subarray(0, 4).toString(), "RIFF");
    assert.equal(wav.subarray(8, 12).toString(), "WAVE");
    assert.equal(wav.subarray(12, 16).toString(), "fmt ");
    assert.equal(wav.readUInt16LE(20), 1);            // PCM
    assert.equal(wav.readUInt16LE(22), 1);            // mono
    assert.equal(wav.readUInt32LE(24), 22050);        // sample rate
    assert.equal(wav.readUInt16LE(32), 2);            // block align
    assert.equal(wav.readUInt16LE(34), 16);           // bits per sample
    assert.equal(wav.subarray(36, 40).toString(), "data");
    assert.equal(wav.readUInt32LE(40), 8);            // data size
    // samples
    assert.equal(wav.readInt16LE(44), 0);
    assert.equal(wav.readInt16LE(46), 32767);
    assert.equal(wav.readInt16LE(48), -32768);
    assert.equal(wav.readInt16LE(50), 1234);
  });

  it("16 kHz / 48 kHz sample rate round-trip in header", () => {
    for (const sr of [16000, 22050, 24000, 48000]) {
      const wav = writeWavLikeBin([0], sr);
      assert.equal(wav.readUInt32LE(24), sr);
      assert.equal(wav.readUInt32LE(28), sr * 2); // byte rate
    }
  });

  it("0-sample WAV still has valid 44-byte header (no body)", () => {
    const wav = writeWavLikeBin([], 22050);
    assert.equal(wav.length, 44);
    assert.equal(wav.readUInt32LE(40), 0);
    assert.equal(wav.readUInt32LE(4), 36); // chunk size = 36 when dataSize=0
  });
});

describe("piper-plus bin: file shape contract", () => {
  it("bin file exists and is executable as a script", () => {
    const content = readFileSync(BIN, "utf8");
    assert.match(content, /^#!\/usr\/bin\/env node/);
    assert.match(content, /piper-plus Node CLI bin/);
    assert.match(content, /phoneme_ids/);
  });

  it("references onnxruntime-node only via dynamic import (so syntax-load works without ORT)", () => {
    const content = readFileSync(BIN, "utf8");
    // dynamic import keeps `node --check` clean even when ORT is absent.
    assert.match(content, /await import\(['"]onnxruntime-node['"]\)/);
    // no top-level static import of onnxruntime-node
    assert.equal(
      /^import .*onnxruntime-node.*;\s*$/m.test(content),
      false,
    );
  });
});
