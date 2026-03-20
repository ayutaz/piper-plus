# Piper Plus Go Examples

Example programs demonstrating piper-plus Go bindings usage.

## Prerequisites

1. ONNX Runtime shared library (set `ONNX_RUNTIME_SHARED_LIBRARY_PATH`)
2. A piper-plus ONNX model (e.g., from HuggingFace `ayousanz/piper-plus-base`)

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
