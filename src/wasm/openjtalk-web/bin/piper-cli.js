#!/usr/bin/env node
/* eslint-env node */
/**
 * piper-plus Node CLI bin
 * =======================
 * Cross-runtime audio byte parity gate (M2.2 / PR #511) で 6 runtime の
 * 一員として「WASM (npm package) ランタイムの Node 推論パス」 を提供する
 * 最小 CLI。 onnxruntime-node を直接使い、 phoneme_ids JSONL 入力経路で
 * 動作する。 G2P は経由しないため Rust / Go / C# / C++ / Python の
 * `--json-input` 経路と入力契約が一致する。
 *
 * Browser 側の `src/index.js` は fetch / IndexedDB / globalThis.ort を
 * 前提とする設計のため Node 直接実行が難しい。 将来 src/index.js が
 * Node 対応した時点で本 bin の中身を差し替えれば API 変更なしで移行可能。
 *
 * CLI 仕様:
 *   piper-plus --model <onnx> --config <json> --json-input \
 *              --output-file <wav> < phoneme_ids.jsonl
 *
 * Flags:
 *   --model <path>         ONNX model file (required)
 *   --config <path>        config.json (required for sample_rate / num_languages)
 *   --json-input           Treat stdin as JSONL with phoneme_ids (required)
 *   --output-file <path>   Output WAV path (or "-" for stdout)
 *   --noise-scale <float>  Default 0.667
 *   --length-scale <float> Default 1.0
 *   --noise-w <float>      Default 0.8
 *   --help                 Print this help
 *
 * JSONL fields (per line):
 *   phoneme_ids: int[]   required
 *   speaker_id: int?     optional
 *   language_id: int?    optional
 *   output_file: str?    optional (overrides --output-file per line)
 */

import { argv, exit, stdin, stdout, stderr } from 'node:process';
import { readFileSync, writeFileSync } from 'node:fs';
import { createInterface } from 'node:readline';

const HELP = `Usage: piper-plus --model <onnx> --config <json> --json-input [--output-file <wav>]

Cross-runtime parity bin for piper-plus (Node, onnxruntime-node).
See docs/spec/audio-parity-contract.toml for the JSONL contract.

Flags:
  --model <path>          ONNX model file (required)
  --config <path>         config.json (required)
  --json-input            Treat stdin as JSONL with phoneme_ids (required)
  --output-file <path>    Output WAV path (or "-" for stdout)
  --noise-scale <float>   Default 0.667
  --length-scale <float>  Default 1.0
  --noise-w <float>       Default 0.8
  --help                  Print this help
`;

function parseArgs(args) {
  const opts = {
    model: null,
    config: null,
    jsonInput: false,
    outputFile: null,
    noiseScale: 0.667,
    lengthScale: 1.0,
    noiseW: 0.8,
    help: false,
  };
  for (let i = 0; i < args.length; i++) {
    const flag = args[i];
    const next = () => {
      const v = args[++i];
      if (v === undefined) {
        throw new Error(`${flag} requires a value`);
      }
      return v;
    };
    switch (flag) {
      case '--help':
      case '-h':
        opts.help = true;
        break;
      case '--model':
      case '-m':
        opts.model = next();
        break;
      case '--config':
      case '-c':
        opts.config = next();
        break;
      case '--json-input':
        opts.jsonInput = true;
        break;
      case '--output-file':
      case '-f':
        opts.outputFile = next();
        break;
      case '--noise-scale':
        opts.noiseScale = parseFloat(next());
        break;
      case '--length-scale':
        opts.lengthScale = parseFloat(next());
        break;
      case '--noise-w':
        opts.noiseW = parseFloat(next());
        break;
      default:
        throw new Error(`Unknown flag: ${flag}`);
    }
  }
  return opts;
}

function writeWav(samples, sampleRate, sink) {
  const numChannels = 1;
  const bitsPerSample = 16;
  const blockAlign = numChannels * (bitsPerSample / 8);
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length * blockAlign;
  const chunkSize = dataSize + 36;
  const header = Buffer.alloc(44);
  let o = 0;
  header.write('RIFF', o);
  o += 4;
  header.writeUInt32LE(chunkSize, o);
  o += 4;
  header.write('WAVE', o);
  o += 4;
  header.write('fmt ', o);
  o += 4;
  header.writeUInt32LE(16, o);
  o += 4;
  header.writeUInt16LE(1, o);
  o += 2;
  header.writeUInt16LE(numChannels, o);
  o += 2;
  header.writeUInt32LE(sampleRate, o);
  o += 4;
  header.writeUInt32LE(byteRate, o);
  o += 4;
  header.writeUInt16LE(blockAlign, o);
  o += 2;
  header.writeUInt16LE(bitsPerSample, o);
  o += 2;
  header.write('data', o);
  o += 4;
  header.writeUInt32LE(dataSize, o);
  const pcm = Buffer.alloc(dataSize);
  for (let i = 0; i < samples.length; i++) {
    pcm.writeInt16LE(samples[i], i * 2);
  }
  if (typeof sink === 'string') {
    writeFileSync(sink, Buffer.concat([header, pcm]));
  } else {
    sink.write(header);
    sink.write(pcm);
  }
}

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

async function loadOrt() {
  try {
    return await import('onnxruntime-node');
  } catch (err) {
    stderr.write(
      'ERROR: onnxruntime-node not installed. Install with `npm i onnxruntime-node`.\n',
    );
    stderr.write(`(import failed: ${err.message})\n`);
    exit(1);
  }
}

async function readJsonlLines(input) {
  const lines = [];
  const rl = createInterface({ input, crlfDelay: Infinity });
  for await (const raw of rl) {
    const line = raw.trim();
    if (line) lines.push(line);
  }
  return lines;
}

async function main() {
  let opts;
  try {
    opts = parseArgs(argv.slice(2));
  } catch (err) {
    stderr.write(`ERROR: ${err.message}\n\n${HELP}`);
    exit(2);
  }
  if (opts.help) {
    stdout.write(HELP);
    return 0;
  }
  if (!opts.model || !opts.config || !opts.jsonInput) {
    stderr.write('ERROR: --model, --config and --json-input are required.\n\n');
    stderr.write(HELP);
    exit(2);
  }

  const config = JSON.parse(readFileSync(opts.config, 'utf8'));
  const sampleRate = config?.audio?.sample_rate ?? 22050;
  const numSpeakers = config?.num_speakers ?? 1;
  const numLanguages = config?.num_languages ?? 0;

  const ort = await loadOrt();
  const session = await ort.InferenceSession.create(opts.model);
  const inputNames = new Set(session.inputNames);

  const lines = await readJsonlLines(stdin);
  if (lines.length === 0) {
    stderr.write('ERROR: no JSONL input received on stdin.\n');
    exit(2);
  }

  let wroteAny = false;
  for (const line of lines) {
    const entry = JSON.parse(line);
    const phonemeIds = entry.phoneme_ids;
    if (!Array.isArray(phonemeIds) || phonemeIds.length === 0) {
      stderr.write(`ERROR: line missing phoneme_ids: ${line}\n`);
      exit(2);
    }
    const ids = BigInt64Array.from(phonemeIds.map((n) => BigInt(n)));
    const feeds = {
      input: new ort.Tensor('int64', ids, [1, phonemeIds.length]),
      input_lengths: new ort.Tensor('int64', BigInt64Array.from([BigInt(phonemeIds.length)]), [1]),
      scales: new ort.Tensor(
        'float32',
        Float32Array.from([opts.noiseScale, opts.lengthScale, opts.noiseW]),
        [3],
      ),
    };
    if (inputNames.has('sid') && numSpeakers > 1) {
      const sid = entry.speaker_id ?? 0;
      feeds.sid = new ort.Tensor('int64', BigInt64Array.from([BigInt(sid)]), [1, 1]);
    }
    if (inputNames.has('lid') && numLanguages > 0) {
      const lid = entry.language_id ?? 0;
      feeds.lid = new ort.Tensor('int64', BigInt64Array.from([BigInt(lid)]), [1]);
    }
    if (inputNames.has('prosody_features')) {
      const pf = new Int32Array(phonemeIds.length * 3); // zeros
      feeds.prosody_features = new ort.Tensor('int64',
        BigInt64Array.from(Array.from(pf, (v) => BigInt(v))),
        [1, phonemeIds.length, 3],
      );
    }
    if (inputNames.has('speaker_embedding')) {
      const dim = 256;
      feeds.speaker_embedding = new ort.Tensor(
        'float32', new Float32Array(dim), [1, dim],
      );
      feeds.speaker_embedding_mask = new ort.Tensor(
        'int64', BigInt64Array.from([0n]), [1, 1],
      );
    }

    const outputs = await session.run(feeds);
    const audioName = session.outputNames.includes('output')
      ? 'output' : session.outputNames[0];
    const audioFloat = outputs[audioName].data;
    const audio = floatToInt16(audioFloat);

    const sink = entry.output_file ?? opts.outputFile;
    if (!sink || sink === '-') {
      writeWav(audio, sampleRate, stdout);
    } else {
      writeWav(audio, sampleRate, sink);
      stderr.write(`Wrote ${sink}\n`);
    }
    wroteAny = true;
  }
  return wroteAny ? 0 : 1;
}

main().then(
  (rc) => exit(rc ?? 0),
  (err) => {
    stderr.write(`FATAL: ${err.stack ?? err.message ?? err}\n`);
    exit(1);
  },
);
