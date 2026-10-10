# Piper Plus Go Examples

Example programs demonstrating piper-plus Go bindings usage.

## Prerequisites

1. ONNX Runtime shared library (set `ONNX_RUNTIME_SHARED_LIBRARY_PATH`)
2. A reference-free Piper Plus ONNX model, such as the canonical
   [Tsukuyomi-chan model](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)
   or [CSS10 Japanese model](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang)

For the experimental Zero-Shot base, download the pinned
[`zs-v1` bundle](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
and pass `releases/zs-v1/base.onnx` together with its `config.json`. Do not
use the legacy root `config.json` with that nested ONNX. The Go CLI accepts a
model URL for `--download-model`; the public `base` / `zero-shot-base-zs-v1`
aliases are not available in released Go binaries.

## Examples

| Directory | Description |
|-----------|-------------|
| `basic/` | Simple text-to-speech synthesis |
| `server/` | HTTP TTS server |
| `streaming/` | Streaming synthesis (sentence-by-sentence) |
| `batch/` | Batch processing from text file |
| `pool/` | Concurrent synthesis with VoicePool |

## Running

```bash
export ONNX_RUNTIME_SHARED_LIBRARY_PATH=/path/to/libonnxruntime.so

# Basic example
cd basic && go run . -model /path/to/model.onnx -text "Hello!"

# HTTP server
cd server && go run . -model /path/to/model.onnx -addr :8080

# Streaming
cd streaming && go run . -model /path/to/model.onnx -text "First. Second."

# Batch
cd batch && go run . -model /path/to/model.onnx -input texts.txt

# Pool
cd pool && go run . -model /path/to/model.onnx -concurrency 4
```
