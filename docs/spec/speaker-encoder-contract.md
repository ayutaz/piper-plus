# Speaker Encoder Contract

Cross-runtime contract for the ECAPA-TDNN speaker encoder used by piper-plus
voice cloning (`--reference-audio` / `--speaker-embedding`).

This spec governs **two** layers of cross-runtime parity:

1. **Mel parity** — every runtime computes the *same* mel spectrogram from
   the *same* WAV samples (deterministic, reproducible without an ONNX model).
2. **E2E cosine gate** — every runtime, given the same mel + the same ONNX
   encoder, produces a 256-dim embedding within `cosine ≥ 0.999` of the
   Python reference (allows for ORT EP / float-precision drift, but rules out
   shape / axis / scaling bugs).

Byte-equality at layer 2 is **explicitly out of scope** because ONNX Runtime
execution providers introduce tiny float32 differences that vary by host
(CUDA EP vs CPU EP, AVX-512 vs ARM NEON, FP16 vs FP32, …). Cosine ≥ 0.999 is
the canonical cross-EP gate used by SpeechBrain and other ECAPA-TDNN consumers.

## Layer 1 — Mel parity (canonical)

| Parameter | Value | Locked at |
|---|---|---|
| `sample_rate` | 16000 | `test/generate_speaker_encoder_golden.py:27` |
| `n_fft` | 512 | `:28` |
| `hop_length` | 160 | `:29` |
| `n_mels` | 80 | `:30` |
| `fmin` | 20.0 | `:31` |
| `fmax` | 7600.0 | `:32` |
| Window | Hann | `hann_window` |
| Mel scale | HTK 2595·log10 | `hz_to_mel` |
| Filterbank center | always `≥ 1.0` | `create_mel_filterbank` |
| FFT semantics | manual DFT, **float32** | `compute_mel_spectrogram` |
| Resampling | linear interpolation, float32 | `resample_linear` |

Fixture: `test/fixtures/speaker_encoder_golden.json`. Includes:
- `hann_window` (length, first_5, last_5, mid_value, sha-256 checksum)
- `mel_filterbank` (shape, per-band sums, total sum, checksum)
- 4 deterministic test cases (sine 440Hz, sine 1000Hz, multitone, resample
  48k→16k) — each with mel checksum + sampled values + corner values

### Layer 1 — runtime status

| Runtime | Status | Test path |
|---|---|---|
| Python (canonical) | ✅ | `test/generate_speaker_encoder_golden.py` (also serves as the reference impl) |
| Rust | ✅ 16 tests | `src/rust/piper-core/tests/test_speaker_encoder_golden.rs` |
| Go | ✅ ~26 tests | `src/go/piperplus/speaker_encoder_test.go` |
| C# | ✅ ~23 facts | `src/csharp/PiperPlus.Core.Tests/SpeakerEncoderTests.cs` |
| WASM/JS | ⏳ stub exists at `src/wasm/openjtalk-web/src/speaker-encoder.js` — **parity test pending** |
| C/C++ | ⏳ symbol exists in C API — **parity test pending** |

## Layer 2 — E2E cosine gate

### Protocol

The fixture optionally contains an `e2e_cosine_gate` block:

```json
"e2e_cosine_gate": {
  "version": 1,
  "encoder_onnx": {
    "hf_repo": "ayousanz/piper-plus-speaker-encoder",
    "hf_filename": "encoder.onnx",
    "hf_revision": "v1.0.0",
    "sha256": "<sha256 of the pinned revision>"
  },
  "reference_wav": {
    "path": "test/fixtures/speaker_encoder/reference.wav",
    "sha256": "<sha256 of the WAV bytes>",
    "license": "CC0",
    "duration_s": 1.024,
    "sample_rate": 16000
  },
  "expected_embedding": {
    "dim": 256,
    "values": [/* 256 floats, L2-normalized */],
    "checksum": "<sha256 of the rounded embedding>"
  },
  "cosine_threshold": 0.999
}
```

### Test semantics (every runtime)

```
if fixture has no e2e_cosine_gate block:
    skip                      # mel parity only — gate not yet activated
elif encoder ONNX is not locally available (env var or download cache):
    skip                      # opt-in test, do not block CI
else:
    compute embedding from reference_wav using local encoder
    cos = dot(actual, expected) / (norm(actual) * norm(expected))
    assert cos >= cosine_threshold
```

The skip path keeps the gate **opt-in** so it does not break PR CI before
the ONNX is actually published. Once published, CI lanes opt in via:

- **Python**: `PIPER_SPEAKER_ENCODER_E2E=1 pytest test/test_speaker_encoder_e2e.py`
- **Rust**: `PIPER_SPEAKER_ENCODER_E2E=1 cargo test --test test_speaker_encoder_e2e`
- **Go**: `PIPER_SPEAKER_ENCODER_E2E=1 go test ./piperplus -run TestSpeakerEncoderE2ECosine`
- **C#**: `PIPER_SPEAKER_ENCODER_E2E=1 dotnet test --filter SpeakerEncoderE2ECosine`

The path to a locally-cached encoder ONNX may be supplied via
`PIPER_SPEAKER_ENCODER_ONNX_PATH` (overrides the HF download). This is the
canonical way to run the gate against a *different* encoder without
modifying the fixture.

### ONNX distribution policy

The encoder ONNX is **not** committed to the repo (Git LFS quota, ~14MB).
Distribution is via Hugging Face Hub at `ayousanz/piper-plus-speaker-encoder`,
pinned by `revision` tag (e.g. `v1.0.0`) so the test is reproducible. Each
revision corresponds to a `[encoder_onnx].sha256` field in the fixture so a
silent upstream replacement cannot drift the gate.

This mirrors the TTS model alias pattern (`hf_hub_download` in
`src/python/piper_train/model_manager.py`).

### Layer 2 — runtime status

| Runtime | Status | Test path |
|---|---|---|
| Python (canonical) | ⏳ scaffold (skips when fixture lacks block) | `test/test_speaker_encoder_e2e.py` |
| Rust | ⏳ scaffold (skips when env var unset) | `src/rust/piper-core/tests/test_speaker_encoder_e2e.rs` |
| Go | ⏳ scaffold | `src/go/piperplus/speaker_encoder_e2e_test.go` |
| C# | ⏳ scaffold | `src/csharp/PiperPlus.Core.Tests/SpeakerEncoderE2ETests.cs` |
| WASM/JS | ❌ not started — depends on layer 1 first |
| C/C++ | ❌ not started — depends on layer 1 first |

## Remaining work (out of scope for the present PR)

The following are intentionally deferred, with each decision pinned here so
the gap is explicit rather than implicit:

1. **WASM/JS layer 1 mel parity** — `speaker-encoder.js` predates the
   golden fixture; needs a `test-speaker-encoder-golden.js` test that loads
   `test/fixtures/speaker_encoder_golden.json` and verifies the JS mel
   output against the same checksums.
2. **C/C++ layer 1 mel parity** — same, in `src/cpp/tests/`.
3. **HF publication** — the actual `ayousanz/piper-plus-speaker-encoder`
   HF repo + revision tag must be created and the fixture's `sha256` /
   `expected_embedding` populated by running
   `python test/generate_speaker_encoder_golden.py --encoder-onnx <path>
    --reference-wav <path>`.
4. **CI lanes** — once (3) is done, each runtime CI workflow gains a
   conditional step that downloads the encoder via HF and sets
   `PIPER_SPEAKER_ENCODER_E2E=1`. Caching key:
   `speaker-encoder-onnx-${{ hashfiles('test/fixtures/speaker_encoder_golden.json') }}`.
5. **WASM/C++ layer 2 E2E** — depends on (1) and (2).

The skip semantics in step (2) of "Test semantics" guarantee none of the
above blocks merging this scaffolding.
