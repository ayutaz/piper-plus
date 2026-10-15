# piper-plus-cli

Rust command-line inference for piper-plus. The binary is named
`piper-plus-cli` in a Cargo checkout; release archives may provide a renamed
`piper-plus` executable.

## Build

From the repository root:

```bash
cargo build --release -p piper-plus-cli
```

The CLI needs ONNX Runtime as configured by the workspace build. Run
`piper-plus-cli --help` for the complete option list.

## Synthesize from a local model

```bash
printf 'こんにちは。\n' | \
  cargo run --release -p piper-plus-cli -- \
  --model models/tsukuyomi-chan-6lang-fp16.onnx \
  --config models/config.json \
  --output-file output.wav
```

Useful alternatives are `--text` for direct input, `--output-dir` for JSONL
batch output, `--speaker`, `--language`, `--device`, `--stream`, `--timing
json|tsv|srt`, `--output-raw`, and `--test-mode`. `--list-devices` and
`--list-models` do not require a model. `--download-model NAME` uses the
built-in name registry; use `--list-models` to see names available in the
binary.

The CLI resolves a config beside the model when `--config` is omitted. A
`PIPER_PLUS_DEFAULT_MODEL`, `PIPER_PLUS_DEFAULT_CONFIG`, or
`PIPER_PLUS_MODEL_DIR` environment variable can provide the corresponding
default.

## Public `zs-v1` bundle

For the experimental v7 epoch32 reference-conditioned bundle, download the
matching files from the pinned revision and keep the nested bundle together:

```bash
ZS_REV=3620ed788667cb76f08bd6cf2db8152c1f4c8bd1
ZS_URL="https://huggingface.co/ayousanz/piper-plus-base/resolve/${ZS_REV}/releases/zs-v1"
mkdir -p models/zs-v1
curl -L "${ZS_URL}/base.onnx" -o models/zs-v1/base.onnx
curl -L "${ZS_URL}/base.onnx.json" -o models/zs-v1/base.onnx.json
curl -L "${ZS_URL}/config.json" -o models/zs-v1/config.json
curl -L "${ZS_URL}/campplus.onnx" -o models/zs-v1/campplus.onnx
```

The public bundle uses a CAM++ 192-dimensional embedding. Follow the
[published `zs-v1` README](https://huggingface.co/ayousanz/piper-plus-base/blob/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1/README.md)
for reference-audio preprocessing and embedding generation, then pass the
resulting raw float32 file:

```bash
piper-plus-cli --model models/zs-v1/base.onnx \
  --config models/zs-v1/base.onnx.json \
  --speaker-embedding embedding.bin \
  --text "Reference-conditioned example." \
  --output-file cloned.wav
```

`--reference-audio` additionally requires `--speaker-encoder-model` and lets
the CLI compute the embedding. A precomputed embedding is preferred when the
published preprocessing bundle is used. The model's ONNX metadata determines
the required dimension; legacy models may use a different encoder.

The published reference-conditioned example was verified with PyPI
`piper-plus==2.0.0`. CI run `38189966578` reports six-runtime inference from
shared Python phoneme IDs; native G2P and listening quality were excluded, and
quality approval remains false. These checks do not constitute approval of
audio quality.

## JSONL and batch input

Without `--text`, the CLI reads JSONL from stdin. Each record can contain
`text`, `speaker`, `language`, and the synthesis parameters accepted by the
runtime. Use `--batch FILE` for one utterance per line. `--timing FORMAT`
adds phoneme timing output when the loaded model exposes duration data.

## Language and dictionary behavior

The current CLI supports `ja`, `en`, `zh`, `ko`, `es`, `fr`, `pt`, and `sv`.
Use `--language` to override detection. Japanese requires the OpenJTalk
dictionary available to the workspace or release archive; custom entries can
be loaded with one or more `--custom-dict PATH` options.
