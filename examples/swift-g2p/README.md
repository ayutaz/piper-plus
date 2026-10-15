# piper-plus Swift G2P Integration Example

Standalone Swift integration example for **PiperPlusG2P** — the G2P-only Swift product (Issue #387).

> **Pair with**: [`examples/swift/README.md`](../swift/README.md) covers the full **synthesis** engine (`PiperPlus`, requires ONNX Runtime). Use this directory only when you need text → IPA tokens **without** ONNX synthesis.

## What's here

| Path | Purpose |
|------|---------|
| `HelloG2P/Package.swift` | Minimal SPM consumer that depends on `https://github.com/ayutaz/piper-plus` (v2.0.1+). |
| `HelloG2P/Sources/HelloG2P/main.swift` | CLI demo — phonemizes a built-in sample set or `<lang>:<text>` arguments. |

## Quick Start (with published v2.0.1+)

```bash
cd examples/swift-g2p/HelloG2P
swift run HelloG2P
swift run HelloG2P "ja:今日はいい天気です" "fr:bonjour" "ko:안녕하세요"
```

Full setup, error handling, App Store checklist: [`docs/guides/platform/swift-g2p-integration.md`](../../docs/guides/platform/swift-g2p-integration.md).

## Local Development (when testing unreleased source changes)

The published `from: "2.0.1"` URL resolves the released xcframework. To exercise wrapper changes from the in-tree branch without relying on a future release asset:

1. **Build the xcframework locally** (one-time per branch). From the piper-plus repo root, mirror the steps in `.github/workflows/swift-g2p-ci.yml`:

   ```text
   cargo build --manifest-path src/rust/Cargo.toml -p piper-plus-g2p --target {aarch64,x86_64}-apple-darwin --release \
     --features all-languages,naist-jdic,bundled-dicts,ffi
   # → lipo + cbindgen + xcodebuild -create-xcframework
   ```

2. **Switch `HelloG2P/Package.swift` to local mode**:

   ```swift
   dependencies: [
       // .package(url: "https://github.com/ayutaz/piper-plus", from: "2.0.1"),
       .package(name: "piper-plus", path: "../../.."),
   ],
   ```

   With `path:`, SwiftPM uses the in-tree `Package.swift` at the piper-plus repo root. For source changes that are not in the published v2.0.1 asset, replace the binaryTarget with `.binaryTarget(name: "PiperPlusG2PBinary", path: "build-mac/piper_plus_g2p.xcframework")` for the duration of testing, or use `Package.ci.swift` (already wired for `path:`-based local resolution — see `swift-g2p-ci.yml` for how CI swaps it in).

3. **Run**:

   ```bash
   cd examples/swift-g2p/HelloG2P
   swift run HelloG2P
   ```

> The `path:` workaround is intentionally manual — it should not be committed back. For released consumers, depend on the public v2.0.1+ URL form.

## Why a separate example directory?

The synthesis engine (`PiperPlus`, in [`../swift/`](../swift/)) ships with **iOS-only** binaries and a hard ORT dependency. The G2P product is intentionally lighter:

- **No ORT** — pure Rust + bundled dictionaries. ~3–5 MB xcframework download vs ~30 MB synthesis xcframework + ORT.
- **iOS + macOS slices** — `swift run` from a Mac CLI works directly (the synthesis engine cannot, because the xcframework lacks a macOS slice).
- **Different release cadence** — G2P version (`g2pVersion`) bumps independently of synthesis version (`version`). See `Package.swift` at the repo root.

Splitting the examples mirrors that split: this directory is the on-ramp for callers who want only G2P; `examples/swift/` is the on-ramp for callers who want full TTS.

## Further Reading

- [Swift G2P Integration Guide](../../docs/guides/platform/swift-g2p-integration.md) — full usage, troubleshooting, App Store checklist.
- [Swift G2P Specification](../../docs/reference/swift-g2p.md) — design rationale.
- [piper-plus repo root Package.swift](../../Package.swift) — the canonical SPM manifest.
- [Issue #387](https://github.com/ayutaz/piper-plus/issues/387) — feature tracker.
