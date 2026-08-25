# ONNX Runtime Version Matrix

All runtimes in piper-plus use ONNX Runtime for inference.
This document records the concrete versions used by each implementation
so that version drift can be detected early.

> **Note:** The `ort` Rust crate uses its own versioning scheme that
> does not map 1:1 to upstream ONNX Runtime releases.  The "ORT
> version" column below refers to the upstream Microsoft ONNX Runtime
> version that the package wraps or depends on.

## Policy (Issue #372 Option C)

The C++ pipeline (`cmake/OnnxRuntime.cmake`) is the **canonical
version**. Other ecosystems are free to use *any version >= canonical*.
This trades bit-exact inference parity for ecosystem-native package
choices (e.g. C# / Go can stay on their latest stable instead of being
forced to downgrade).

Two enforcement modes are used by `scripts/check_ort_versions.py`:

| Group | Files | Rule |
|-------|-------|------|
| Exact-match | C++ pipeline (cmake + 7 workflows) + `docker/cpp-dev/Dockerfile` | Must equal canonical exactly |
| Floor-check | Each ecosystem's dependency manifest | Pin must satisfy `>= canonical` |

Out of scope:

* `src/rust/piper-core/Cargo.toml` (`ort = "2.0.0-rc.X"`) — `ort`'s
  versioning scheme does not map 1:1 to upstream, and a stable `ort`
  release is not yet available on crates.io (as of 2026-05). Tracked
  separately so the gate is not coupled to upstream `ort` cadence.
* `docs/` (history-bearing; reviewed by humans, not by the gate).

`scripts/check_ort_version_drift.py` (workflow `Model Quality Gate`) keeps
the `## Current versions` table below honest by comparing each row against
the real pin, per row. It covers only the rows this file does **not**
exempt: the `Rust` row is out of scope per the bullet above, and the C++ /
iOS / Android / Kotlin G2P rows belong to `check_ort_versions.py`'s
exact-match group.

## Current versions

| Runtime  | ORT Version  | Floor (Issue #372) | Package / Source |
|----------|-------------|--------------------|------------------|
| Python (training) | `>=1.26.0` (gpu extra: `onnxruntime-gpu>=1.20.1,<1.26`) | `>=1.20.0` ✓ | `src/python/pyproject.toml` extras (train / inference / inference-gpu) |
| Python (runtime) | `>=1.26.0` (gpu: `onnxruntime-gpu>=1.20.1,<1.26`) | `>=1.20.0` ✓ | `src/python_run/requirements.txt` + `requirements_gpu.txt` |
| Rust     | 2.0.0-rc.13 (`ort` crate, wraps ORT 1.28.0) | exempt (no stable upstream) | `ort` (crates.io) |
| C#       | 1.24.3      | `>=1.20.0` ✓ | `Microsoft.ML.OnnxRuntime{,.Managed}` (NuGet) — 5 csproj files |
| Go       | 1.27.0      | `>=1.20.0` ✓ | `github.com/yalue/onnxruntime_go` |
| C++ (canonical) | **1.20.0** | — | `cmake/OnnxRuntime.cmake` (source of truth) |
| C++ (Linux/macOS source build) | 1.20.0 | exact ✓ | `build-piper.yml`, `_build-test-cpp.yml` |
| C++ (Windows pre-built) | 1.20.0 | exact ✓ | `cmake/find_onnxruntime_windows.cmake` |
| C++ (CPU dev image) | 1.20.0 | exact ✓ | `docker/cpp-dev/Dockerfile` (Issue #372) |
| iOS      | 1.20.0      | exact ✓ | xcframework (Microsoft CDN: `download.onnxruntime.ai/pod-archive-onnxruntime-c-1.20.0.zip`, sha256 `50891a8aadd17d48...50ff`, 検証日 2026-05-09) |
| Android (release) | 1.20.0 | exact ✓ | AAR (Maven Central) |
| Android (PR CI)   | 1.20.0 | exact ✓ | AAR (Maven Central) |
| Kotlin G2P (release/CI) | 1.20.0 | exact ✓ | `release-kotlin-g2p.yml`, `kotlin-g2p-ci.yml` |
| JS/WASM  | `>=1.21.0`  | `>=1.20.0` ✓ | `onnxruntime-web` (npm, peerDependency) |

## CI Workflow References

| Workflow | Variable | Used By |
|----------|----------|---------|
| `release-shared-lib.yml` | `env.ONNXRUNTIME_VERSION` (top-level) | iOS + Android release builds |
| `android-build.yml` | `env.ONNXRUNTIME_VERSION` (job-level) | Android PR CI builds |
| `release-kotlin-g2p.yml` | `env.ONNXRUNTIME_VERSION` (top-level) | Kotlin G2P AAR release |
| `kotlin-g2p-ci.yml` | `env.ONNXRUNTIME_VERSION` (top-level) | Kotlin G2P PR CI |
| `ort-version-sync.yml` | (gate; runs `scripts/check_ort_versions.py`) | All exact-match + floor-check files |

## Updating

When bumping the C++ canonical ORT version (e.g. 1.20.0 → 1.22.0):

1. Update `set(ONNXRUNTIME_VERSION ...)` in `cmake/OnnxRuntime.cmake`.
2. Update `cmake/find_onnxruntime_windows.cmake` to match.
3. Update `env.ONNXRUNTIME_VERSION` in all 4 workflow files
   (release-shared-lib / android-build / release-kotlin-g2p /
   kotlin-g2p-ci).
4. Update the hard-coded URLs in `build-piper.yml` and
   `_build-test-cpp.yml` (Linux/macOS/Windows).
5. Update the hard-coded URL in `docker/cpp-dev/Dockerfile`.
6. Re-verify the iOS pod-archive sha256 (the CDN zip changes per
   release; see `release-shared-lib.yml` `ORT_IOS_SHA256` env).
7. If the new canonical is *higher* than any ecosystem's pin, raise
   that pin too:
   * Python: `pyproject.toml` (3 extras) + `requirements*.txt` +
     `setup.py`.
   * C#: 5 csproj files (`PiperPlus.{Core,Cli,Cli.Tests,Core.Tests,Bench}`).
   * Go: `src/go/go.mod`.
   * WASM: `src/wasm/openjtalk-web/package.json` peerDependencies.
8. Update this table.
9. Run `python scripts/check_ort_versions.py --verbose` locally to
   confirm. The CI gate (`ort-version-sync.yml`) runs the same check
   on PR / push.

## Rust `ort` exemption (Issue #372 follow-up)

The Rust ecosystem currently relies on the `ort` crate at
`2.0.0-rc.13` (RC). Reasons it is exempt from the floor check:

* `ort`'s 2.x line redesigns the API and has not shipped a stable
  release as of 2026-08. The pre-release (`2.0.0-rc.13`) wraps ORT
  1.28.0 internally (`ort-sys` の `build/download/dist.tsv`), but
  exposing this in the gate would couple CI to upstream `ort` cadence.
* `ort 1.x` stable exists but uses a different API; downgrading would
  require rewriting `piper-core` / `piper-cli` / `piper-python` /
  `piper-wasm` for negligible compatibility gain.

Because Rust is exempt, the bundled ORT (1.28.0) is intentionally
allowed to run ahead of the C++ canonical (1.20.0). This is a
divergence the gate does not police — it is a documented consequence
of the exemption, not a drift to be "fixed" by bumping C++.

### EP feature gating (`ort` >= 2.0.0-rc.13)

From `2.0.0-rc.13` the EP structs (`ort::ep::{CUDA, CoreML, DirectML,
TensorRT}`) are gated behind `ort`'s own Cargo features; until
`rc.12` they were unconditionally `pub use`d. `piper-core` therefore
forwards its EP features to `ort` using weak-dependency syntax:

```toml
cuda     = ["ort?/cuda"]
coreml   = ["ort?/coreml"]
directml = ["ort?/directml"]
tensorrt = ["ort?/tensorrt"]
```

The `ort?/` form keeps these a no-op when the `onnx` feature is off
(i.e. when `ort` is not in the dependency graph at all).

Two consequences worth knowing:

* **CUDA 13 only.** `ort-sys` `rc.13` ships prebuilt distributions
  tagged `cuda13` — there is no `cuda12` entry. Consumers enabling the
  `cuda` feature need a CUDA 13 runtime.
* **`--all-features` does not link.** No prebuilt distribution carries
  `cuda` + `coreml` + `directml` + `tensorrt` at once, so a local
  `cargo build --all-features` fails in `ort-sys` at link time. CI's
  `cargo check` / `cargo clippy --all-features` are unaffected because
  neither links. Build with a single EP (e.g. `--features onnx,cuda`).

Action items tracked separately:

* Migrate to `ort 2.x stable` as soon as it lands on crates.io.
* Until then, document the wrapped ORT version in this table and
  re-evaluate at each `ort` release.
