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
| WASM/JS | ✅ 6 tests (`Math.fround` f32 narrowing + 2% L2 tol) | `src/wasm/openjtalk-web/test/js/test-speaker-encoder-golden.js` |
| C/C++ | ✅ 5 tests (inline mel port, 2% L2 tol) | `src/cpp/tests/test_speaker_encoder_golden.cpp` |

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
| Python (canonical) | ✅ scaffold (skips when fixture lacks block) | `test/test_speaker_encoder_e2e.py` |
| Rust | ✅ scaffold (skips when env var unset) | `src/rust/piper-core/tests/test_speaker_encoder_e2e.rs` |
| Go | ✅ scaffold | `src/go/piperplus/speaker_encoder_e2e_test.go` |
| C# | ✅ scaffold | `src/csharp/PiperPlus.Core.Tests/SpeakerEncoderE2ETests.cs` |
| WASM/JS | ✅ scaffold (uses `onnxruntime-node` when active) | `src/wasm/openjtalk-web/test/js/test-speaker-encoder-e2e.js` |
| C/C++ | ✅ scaffold (uses `Ort::Session` directly; the C API stub remains documented as EXPERIMENTAL) | `src/cpp/tests/test_speaker_encoder_e2e.cpp` |

All 6 runtimes share the same skip semantics:

1. Skip when fixture lacks `e2e_cosine_gate` block.
2. Skip when `PIPER_SPEAKER_ENCODER_ONNX_PATH` is unset (and Python's
   `PIPER_SPEAKER_ENCODER_E2E=1` HF download path is also unset).
3. Skip when reference WAV not locally available.
4. Otherwise: verify encoder ONNX sha256, run inference, assert
   `cosine(actual, expected) >= cosine_threshold`.

## Activation procedure

Once the encoder ONNX is published:

1. **Generate fixture data**:

   ```bash
   uv run python test/generate_speaker_encoder_golden.py \
     --encoder-onnx /local/path/to/encoder.onnx \
     --reference-wav /local/path/to/reference.wav \
     --hf-repo ayousanz/piper-plus-speaker-encoder \
     --hf-revision v1.0.0
   ```

   Commit the updated `test/fixtures/speaker_encoder_golden.json`.

2. **Reference WAV** — commit a CC0 short reference WAV (mono 16kHz,
   ~1 second) at `test/fixtures/speaker_encoder/reference.wav` (path
   referenced by the fixture).

3. **CI lane activation** — add to each runtime workflow:

   ```yaml
   - name: Download speaker encoder ONNX (cached)
     uses: actions/cache@v4
     with:
       path: ~/.cache/piper-plus/speaker-encoder.onnx
       key: speaker-encoder-onnx-${{ hashFiles('test/fixtures/speaker_encoder_golden.json') }}
   - name: Fetch encoder if cache miss
     run: |
       if [ ! -f ~/.cache/piper-plus/speaker-encoder.onnx ]; then
         huggingface-cli download ayousanz/piper-plus-speaker-encoder \
           encoder.onnx --revision v1.0.0 \
           --local-dir ~/.cache/piper-plus/
       fi
     env:
       HF_HUB_DISABLE_TELEMETRY: 1
   - name: Run E2E gate
     env:
       PIPER_SPEAKER_ENCODER_ONNX_PATH: ~/.cache/piper-plus/speaker-encoder.onnx
     run: <runtime-specific test command>
   ```

   Until that lane is added, the gate stays opt-in — local devs can run it
   by setting the env var, and PR CI continues to pass via the skip path.

## Closing notes

The two-layer split (mel parity is mandatory; E2E cosine gate is opt-in)
is intentional: layer 1 catches algorithm bugs without any external
dependency, while layer 2 catches the harder shape/axis/scaling drifts
that only manifest end-to-end with the real ONNX. Together they form the
complete cross-runtime contract for the speaker encoder.
