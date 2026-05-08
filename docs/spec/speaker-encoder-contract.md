# Speaker Encoder Cross-Runtime Parity Contract

The Speaker Encoder is split across two layers:

1. **Mel feature extraction** — STFT + Hann window + mel filterbank, fully
   deterministic and pure (no learned weights). Every runtime that supports
   voice cloning re-implements this layer in its native language.
2. **ECAPA-TDNN inference** — A learned 256-dim L2-normalised embedding,
   served via an ONNX model. All runtimes load the same `.onnx` file.

The first layer is the only place where independent re-implementation is
possible (and therefore where parity drift can hide). This document pins the
canonical fixture and tracks per-runtime coverage.

## Source of truth

- **Generator**: `test/generate_speaker_encoder_golden.py` (Python torchaudio)
- **Fixture**: `test/fixtures/speaker_encoder_golden.json`
- **Mel parameters** (must be identical in every runtime):
  - `sample_rate = 16000`
  - `n_fft = 512`
  - `hop_length = 160`
  - `n_mels = 80`
  - `fmin = 20.0`
  - `fmax = 7600.0`
  - Window: Hann, `length = 512`
  - Mel filterbank shape: `[80, 257]`, slaney-norm (each band sums to 1.0)

The fixture stores:
- A `hann_window` block (first/last 5 samples + checksum) so each runtime can
  detect a wrong window function.
- A `mel_filterbank` block (band sums + checksums) so each runtime can detect
  a wrong filterbank construction (slaney vs HTK, mismatched fmax, etc.).
- An `audio_input` block (deterministic reference samples) and an
  `expected_mel` block so the full STFT → mel pipeline can be byte-checked.

## Per-runtime coverage (as of this commit)

| Runtime | Mel parity test | Fixture path | Notes |
|---------|-----------------|--------------|-------|
| Python (canonical) | ✓ — generator itself runs in `test/test_speaker_encoder.py` | `test/fixtures/speaker_encoder_golden.json` | torchaudio reference; treated as source of truth |
| Rust (`piper-core`) | ✓ `tests/test_speaker_encoder_golden.rs` (16 tests) | same | mel/window/filterbank parity verified |
| Go (`piperplus`) | ✓ `speaker_encoder_test.go` (~26 tests) | same | mel/window/filterbank parity verified |
| C# (`PiperPlus.Core`) | ✓ `SpeakerEncoderTests.cs` (~23 facts) | same | mel/window/filterbank parity verified |
| **WASM/JS** (`openjtalk-web`) | ✗ **not implemented** | — | `src/wasm/openjtalk-web/src/speaker-encoder.js` exists but no parity test reads the fixture |
| **C/C++** (`libpiper_plus`) | ✗ **not implemented** | — | C API exposes `piper_plus_speaker_encoder_*` symbols but no parity test |

## End-to-end (ECAPA-TDNN) parity

The fully-loaded `reference WAV → 256-dim L2-normalised embedding` round trip
is **not** pinned by an in-repo fixture. Reasons:

1. The ECAPA-TDNN ONNX model itself is large (~14 MB) and is not committed to
   the repository — runtimes download it on first use.
2. The 256-dim output is sensitive to ONNX Runtime version and execution
   provider differences (CPU vs CoreML vs CUDA), so byte-equality is not
   guaranteed even between identical Python / Rust runs without further
   pinning.

The mel parity above is the strongest fixture-based gate currently feasible.
A future PR can extend coverage by:

- Generating an `expected_embedding` field next to `expected_mel` using a
  pinned ONNX Runtime + CPU EP only, and asserting `cosine ≥ 0.999` (rather
  than byte-equality) in each runtime.
- Re-using the existing reference WAV in `test/fixtures/`.

## Follow-up items (out of this commit's scope)

- **WASM/JS speaker-encoder mel parity test** — Should mirror the Rust/Go/C#
  shape: load the JSON fixture, run STFT + mel through `speaker-encoder.js`,
  compare per-band sums and Hann samples within `1e-5` tolerance.
- **C/C++ speaker-encoder mel parity test** — Same shape, in
  `src/cpp/tests/test_speaker_encoder_parity.cpp`. Requires linking against
  the C API, so likely lives next to `test_c_api*.cpp`.
- **End-to-end ECAPA-TDNN cosine gate** — As described above; needs ONNX
  model availability decision (vendor in repo vs download script).
