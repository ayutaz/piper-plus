# piper-plus Swift Integration Example

Swift integration for piper-plus on **iOS** (device + simulator).

> **Compatibility (v2.0.2)**: the released xcframework currently contains
> `ios-arm64` + `ios-arm64_x86_64-simulator` slices only. macOS / Mac Catalyst
> / visionOS / tvOS / watchOS slices are M5 candidates and not yet supported.

> **Recommended path (v2.0.2+)**: use the `Package.swift` shipped at the **piper-plus repo root** as a Swift Package Manager dependency. See [SPM Quick Start](#spm-quick-start) below.
>
> **Alternative**: manual `xcframework` drag-and-drop. See [Manual Integration](#manual-integration) below.

## SPM Quick Start

### v2.0.2 dependency compatibility

The published `v2.0.2` manifest pins the compatible ONNX Runtime SDK, so
consumers do not need to add a separate ONNX Runtime package constraint:

```swift
.package(url: "https://github.com/ayutaz/piper-plus", exact: "2.0.2"),
```

This uses the unmodified public release and its official transitive SDK dependency.

### Step 1: Add piper-plus as a dependency

The current `piper-plus` `Package.swift` wraps the binary xcframework in a
Swift `target` that depends on the official
`onnxruntime-swift-package-manager` package. **ORT is therefore pulled
transitively** — consumers only declare `piper-plus`:

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MyApp",
    // iOS-only — piper-plus xcframework currently has no macOS slice.
    platforms: [.iOS(.v15)],
    dependencies: [
        .package(url: "https://github.com/ayutaz/piper-plus", from: "2.0.2"),
        // No need to declare onnxruntime — piper-plus pulls it transitively
        // through its wrapper target. See Package.swift in the piper-plus repo.
    ],
    targets: [
        .target(
            name: "MyApp",
            dependencies: [
                .product(name: "PiperPlus", package: "piper-plus"),
            ]
        ),
    ]
)
```

Or in Xcode:

1. **File → Add Package Dependencies…**
2. Paste `https://github.com/ayutaz/piper-plus`
3. Select `from: 2.0.2`
4. Add `PiperPlus` to your target — `onnxruntime` is added automatically.

### Step 2: Resolve and use

```bash
swift package resolve
```

```swift
import PiperPlus

// piper_plus.h is exposed via the xcframework's module.modulemap.
// The C API uses piper_plus_create/free; there is no synthesizer-specific
// create/destroy pair.
// See the complete call sequence in the manual integration example below.
```

> **Note**: the `Package.swift` at the piper-plus repo root combines a Swift wrapper `target` (named `PiperPlus`) with a `binaryTarget` (named `PiperPlusBinary`) that points at `libpiper_plus-ios-v${VERSION}.xcframework.zip` published in GitHub Releases. SPM downloads the zip on first resolve and caches it in `~/Library/Developer/Xcode/DerivedData/SourcePackages/`. The wrapper target depends on `onnxruntime`, so consumers don't need to declare it.

> **Release-cycle caveat**: SPM resolves `binaryTarget` against the manifest at the resolved tag commit. The piper-plus maintainer updates `Package.swift`'s version + checksum on `dev` BEFORE tagging; if you depend on a tag whose `Package.swift` was not updated to match its release asset, `swift package resolve` will fail with a checksum mismatch. Pin to the known-good public tag `from: "2.0.2"`.

## Manual Integration

If you cannot use SPM (e.g., your project ships its own bundled xcframework folder), follow the manual drag-and-drop path.

### Step 1-3: Acquire and Embed (same as the cross-runtime guide)

See [`docs/guides/platform/ios-integration.md`](../../docs/guides/platform/ios-integration.md):

- Step 1: download `libpiper_plus-ios-v${VERSION}.xcframework.zip`
- Step 2: download `onnxruntime.xcframework` via CocoaPods / SPM / CDN
- Step 3: in Xcode, **link `piper_plus.xcframework` (Do Not Embed) and Embed & Sign `onnxruntime.xcframework`**

> piper_plus is a static archive (linked into the app at link time) so it does NOT need to be embedded. ORT is a dynamic framework so it MUST be embedded and signed for `dyld` to find it at runtime.

### Step 4: Swift-specific usage

```swift
import Foundation
import PiperPlus

let modelPath = "/path/to/model.onnx"
let configPath = "/path/to/config.json"
var audioData: Data?

modelPath.withCString { modelPtr in
    configPath.withCString { configPtr in
        var config = PiperPlusConfig()
        config.model_path = modelPtr
        config.config_path = configPtr

        var engine: OpaquePointer?
        guard piper_plus_create(&config, &engine) == PIPER_PLUS_OK,
              let engine else { return }
        defer { piper_plus_free(engine) }

        var options = piper_plus_default_options()
        var samples: UnsafeMutablePointer<Float>?
        var sampleCount: Int32 = 0
        var sampleRate: Int32 = 0
        let status = "こんにちは。".withCString { textPtr in
            piper_plus_synthesize(
                engine, textPtr, &options, &samples, &sampleCount, &sampleRate
            )
        }
        guard status == PIPER_PLUS_OK, let samples else { return }
        defer { piper_plus_free_audio(samples) }

        // `sampleRate` is the model's output rate; bridge the copied samples
        // to AVAudioPCMBuffer or another Swift audio representation.
        audioData = Data(
            bytes: samples,
            count: Int(sampleCount) * MemoryLayout<Float>.stride
        )
    }
}
```

> **For an idiomatic Swift wrapper**, the C API is intentionally raw. A higher-level `final class PiperVoice { ... }` wrapper may be added in a future release; track it via Issue #377 follow-ups.

## Project Structure (when using SPM)

```text
MyApp/
├── Package.swift                    # depends on ayutaz/piper-plus + onnxruntime-spm
├── Package.resolved                 # locks piper-plus + ORT versions
└── Sources/
    └── MyApp/
        └── ContentView.swift        # `import PiperPlus` works
```

## Project Structure (when using manual drag-and-drop)

```text
MyApp/
├── Frameworks/
│   ├── piper_plus.xcframework/      # device + simulator slices, modulemap, PrivacyInfo
│   └── onnxruntime.xcframework/     # device + simulator slices
├── MyApp.xcodeproj/
└── MyApp/
    └── ContentView.swift            # `import PiperPlus` works (modulemap resolves)
```

## Note: Compatibility Status

| Item | Status |
|------|--------|
| iOS device (arm64) | ✓ |
| iOS Simulator (arm64 / x86_64) | ✓ |
| macOS / Mac Catalyst | ✗ — the synthesis xcframework has no macOS slice in v2.0.2. M5 candidate |
| visionOS / tvOS / watchOS | ✗ — pending ORT support and dedicated slices. M5 candidate |
| App Extension / App Clip | ✗ — size limits (32 MB / 10 MB uncompressed) cannot fit piper-plus + ORT |

## Troubleshooting

See [`docs/guides/platform/ios-integration.md` § Troubleshooting](../../docs/guides/platform/ios-integration.md#troubleshooting).

## Further Reading

- [Cross-runtime iOS Integration Guide](../../docs/guides/platform/ios-integration.md) — Dart / Flutter / Godot / Swift
- [iOS Specification](../../docs/reference/ios-shared-lib.md) — design rationale
- [piper-plus Package.swift](../../Package.swift) — the SwiftPM manifest at the repo root
- [ORT SwiftPM Package](https://github.com/microsoft/onnxruntime-swift-package-manager) — Microsoft official ORT for Swift
