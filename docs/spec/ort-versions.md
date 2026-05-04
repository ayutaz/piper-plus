# ONNX Runtime Version Matrix

All runtimes in piper-plus use ONNX Runtime for inference.
This document records the concrete versions used by each implementation
so that version drift can be detected early.

> **Note:** The `ort` Rust crate uses its own versioning scheme that
> does not map 1:1 to upstream ONNX Runtime releases.  The "ORT
> version" column below refers to the upstream Microsoft ONNX Runtime
> version that the package wraps or depends on.

| Runtime  | ORT Version  | Package / Source |
|----------|-------------|------------------|
| Python   | >=1.17.0    | `onnxruntime` (PyPI) |
| Rust     | 2.0.0-rc.12 (`ort` crate) | `ort` (crates.io) |
| C#       | 1.24.3      | `Microsoft.ML.OnnxRuntime` (NuGet) |
| Go       | 1.27.0      | `github.com/yalue/onnxruntime_go` |
| C++      | 1.17.0      | source build via CMake |
| iOS      | 1.17.0      | xcframework (Microsoft CDN: `download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip`, sha256 `1623e1150507d9e5...db871`, 検証日 2026-05-04) |
| Android (release) | 1.17.0 | AAR (Maven Central) |
| Android (PR CI)   | 1.17.0 | AAR (Maven Central) |
| JS/WASM  | >=1.21.0    | `onnxruntime-web` (npm, peerDependency) |

## CI Workflow References

| Workflow | Variable | Used By |
|----------|----------|---------|
| `release-shared-lib.yml` | `env.ONNXRUNTIME_VERSION` (top-level) | iOS + Android release builds |
| `android-build.yml` | `env.ONNXRUNTIME_VERSION` (job-level) | Android PR CI builds |

## Updating

When bumping the ONNX Runtime version for a specific runtime:

1. Update the package reference in the relevant build file.
2. Update this table.
3. For iOS/Android release builds, change the top-level `env.ONNXRUNTIME_VERSION` in `release-shared-lib.yml`.
