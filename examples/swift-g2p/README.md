# piper-plus Swift G2P Integration Example

Standalone Swift integration example for **PiperPlusG2P** — the G2P-only Swift product (Issue #387).

> **Pair with**: [examples/swift/README.md](../swift/README.md) covers the full **synthesis** engine (`PiperPlus`, requires ONNX Runtime). Use this directory only when you need text → IPA tokens **without** ONNX synthesis.

## What's here

| Path | Purpose |
|------|---------|
| `HelloG2P/Package.swift` | Minimal SPM consumer that depends on `https://github.com/ayutaz/piper-plus` (v1.14.0+). |
| `HelloG2P/Sources/HelloG2P/main.swift` | CLI demo — phonemizes a built-in sample set or `<lang>:<text>` arguments. |

## Quick Start (once v1.14.0 is published)

```bash
cd examples/swift-g2p/HelloG2P
swift run HelloG2P
```

Expected output (token strings will vary across releases as G2P rules evolve):

```
Registered: en, ja, zh

[ja] こんにちは、世界。
  tokens (12): k o N n i ch i w a 、 s e ...

[en] Hello, world!
  tokens (10): h ə ˈl oʊ   ˈw ɝː l d !

[zh] 你好，世界。
  tokens (8): n i ˧˩˧ x a ʊ̯ ˨˩˦ ...
```

Pass custom inputs as `<lang>:<text>` arguments (lang ∈ `ja`/`en`/`zh`/`ko`/`es`/`fr`/`pt`/`sv`):

```bash
swift run HelloG2P "ja:今日はいい天気です" "fr:bonjour" "ko:안녕하세요"
```

## Local Development (before v1.14.0 is tagged)

The published `from: "1.14.0"` URL won't resolve until the maintainer pushes the v1.14.0 tag and updates `Package.swift`'s `g2pChecksum`. To exercise the wrapper from the in-tree branch:

1. **Build the xcframework locally** (one-time per branch). From the piper-plus repo root:

   ```bash
   # macOS slice (host) — produces build-mac/piper_plus_g2p.xcframework
   ./scripts/build-g2p-macos-xcframework.sh   # if present, else mirror swift-g2p-ci.yml
   ```

   In CI this is done by `.github/workflows/swift-g2p-ci.yml`. Locally you can mirror the same steps: `cargo build -p piper-plus-g2p --target {aarch64,x86_64}-apple-darwin --release --features all-languages,naist-jdic,bundled-dicts,ffi`, then `lipo` + `cbindgen` + `xcodebuild -create-xcframework`. See the workflow file for the canonical sequence.

2. **Switch `HelloG2P/Package.swift` to local mode**:

   ```swift
   dependencies: [
       // .package(url: "https://github.com/ayutaz/piper-plus", from: "1.14.0"),
       .package(name: "piper-plus", path: "../../.."),
   ],
   ```

   With `path:`, SwiftPM uses the in-tree `Package.swift` at the piper-plus repo root. That manifest's `binaryTarget` URL still points at the unpublished v1.14.0 asset, so you'll also need to either (a) replace the binaryTarget with `.binaryTarget(name: "PiperPlusG2PBinary", path: "build-mac/piper_plus_g2p.xcframework")` for the duration of testing, or (b) use `Package.ci.swift` (already wired for `path:`-based local resolution — see `swift-g2p-ci.yml` for how CI swaps it in).

3. **Run**:

   ```bash
   cd examples/swift-g2p/HelloG2P
   swift run HelloG2P
   ```

> The `path:` workaround is intentionally manual — it should not be committed back. The expected user flow is to wait for v1.14.0 to land and depend on the URL form.

## Integrating into your own project

For an iOS app (Xcode project, not a CLI), the steps are:

1. **File → Add Package Dependencies…**, paste `https://github.com/ayutaz/piper-plus`, select `from: 1.14.0`.
2. Add `PiperPlusG2P` to your app target's "Frameworks, Libraries, and Embedded Content" (no need to add `onnxruntime` — `PiperPlusG2P` doesn't depend on it).
3. `import PiperPlusG2P` and use `Phonemizer` as in `main.swift` here.

Full guide: [docs/guides/swift-g2p-integration.md](../../docs/guides/swift-g2p-integration.md).

## Why a separate example directory?

The synthesis engine (`PiperPlus`, in [`../swift/`](../swift/)) ships with **iOS-only** binaries and a hard ORT dependency. The G2P product is intentionally lighter:

- **No ORT** — pure Rust + bundled dictionaries. ~3–5 MB xcframework download vs ~30 MB synthesis xcframework + ORT.
- **iOS + macOS slices** — `swift run` from a Mac CLI works directly (the synthesis engine cannot, because the xcframework lacks a macOS slice).
- **Different release cadence** — G2P version (`g2pVersion`) bumps independently of synthesis version (`version`). See `Package.swift` at the repo root.

Splitting the examples mirrors that split: this directory is the on-ramp for callers who want only G2P; `examples/swift/` is the on-ramp for callers who want full TTS.

## Further Reading

- [Swift G2P Integration Guide](../../docs/guides/swift-g2p-integration.md) — full usage, troubleshooting, App Store checklist.
- [Swift G2P Specification](../../docs/spec/swift-g2p.md) — design rationale.
- [piper-plus repo root Package.swift](../../Package.swift) — the canonical SPM manifest.
- [Issue #387](https://github.com/ayutaz/piper-plus/issues/387) — feature tracker.
