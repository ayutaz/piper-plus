# piper-plus Swift Integration Example

Swift integration for piper-plus on iOS / macOS.

> **Recommended path (v1.13.0+)**: use the `Package.swift` shipped at the **piper-plus repo root** as a Swift Package Manager dependency. See [SPM Quick Start](#spm-quick-start) below.
>
> **Alternative**: manual `xcframework` drag-and-drop. See [Manual Integration](#manual-integration) below.

## SPM Quick Start

### Step 1: Add piper-plus as a dependency

In your `Package.swift`:

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MyApp",
    platforms: [.iOS(.v15), .macOS(.v12)],
    dependencies: [
        .package(url: "https://github.com/ayutaz/piper-plus", from: "1.13.0"),
        .package(
            url: "https://github.com/microsoft/onnxruntime-swift-package-manager",
            exact: "1.17.0"
        ),
    ],
    targets: [
        .target(
            name: "MyApp",
            dependencies: [
                .product(name: "PiperPlus", package: "piper-plus"),
                .product(name: "onnxruntime", package: "onnxruntime-swift-package-manager"),
            ]
        ),
    ]
)
```

Or in Xcode:

1. **File → Add Package Dependencies…**
2. Paste `https://github.com/ayutaz/piper-plus`
3. Select `from: 1.13.0`
4. Add `PiperPlus` to your target
5. Repeat for `https://github.com/microsoft/onnxruntime-swift-package-manager` (exact `1.17.0`)

### Step 2: Resolve and use

```bash
swift package resolve
```

```swift
import PiperPlus

// piper_plus.h C API is exposed via the xcframework's module.modulemap
let synthesizer = piper_plus_create_synthesizer(/* … */)
```

> **Note**: the `Package.swift` at the piper-plus repo root uses `binaryTarget(url:, checksum:)` to point at the `libpiper_plus-ios-${VERSION}.xcframework.zip` published in GitHub Releases. SPM downloads the zip on first resolve and caches it in `~/Library/Developer/Xcode/DerivedData/SourcePackages/`.

## Manual Integration

If you cannot use SPM (e.g., your project ships its own bundled xcframework folder), follow the manual drag-and-drop path. This is identical to [`docs/guides/ios-integration.md`](../../docs/guides/ios-integration.md) Steps 1-4 with Swift specifics:

### Step 1-3: Acquire and Embed (same as the cross-runtime guide)

See [`docs/guides/ios-integration.md`](../../docs/guides/ios-integration.md):
- Step 1: download `libpiper_plus-ios-${VERSION}.xcframework.zip`
- Step 2: download `onnxruntime.xcframework` via CocoaPods / SPM / CDN
- Step 3: drag both into Xcode, **Embed & Sign Frameworks**

### Step 4: Swift-specific usage

```swift
// In any Swift file:
import PiperPlus

// The C API surface is bridged via module.modulemap inside the xcframework.
// piper_plus_* functions are accessible as global Swift functions.

let synthHandle = piper_plus_create_synthesizer(modelPath, configPath)
defer { piper_plus_destroy_synthesizer(synthHandle) }

let result = piper_plus_synthesize(synthHandle, "こんにちは。", &outputBuffer, &outputSize)
guard result == 0 else { /* error */ return }

let audioData = Data(bytes: outputBuffer, count: outputSize)
piper_plus_free_audio(outputBuffer)
```

> **For an idiomatic Swift wrapper**, the C API is intentionally raw. A higher-level `final class PiperVoice { ... }` wrapper may be added in a future release; track it via Issue #377 follow-ups.

## Project Structure (when using SPM)

```
MyApp/
├── Package.swift                    # depends on ayutaz/piper-plus + onnxruntime-spm
├── Package.resolved                 # locks piper-plus + ORT versions
└── Sources/
    └── MyApp/
        └── ContentView.swift        # `import PiperPlus` works
```

## Project Structure (when using manual drag-and-drop)

```
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
| macOS arm64 / x86_64 | ✓ via SPM `platforms: [.macOS(.v12)]` (M2 device + simulator slices cover Apple Silicon Mac targets) |
| visionOS / tvOS / watchOS | ✗ — pending ORT support (M5 candidate) |
| App Extension / App Clip | ✗ — size limits (32 MB / 10 MB uncompressed) cannot fit piper-plus + ORT |

## Troubleshooting

See [`docs/guides/ios-integration.md` § Troubleshooting](../../docs/guides/ios-integration.md#troubleshooting).

## Further Reading

- [Cross-runtime iOS Integration Guide](../../docs/guides/ios-integration.md) — Dart / Flutter / Godot / Swift
- [iOS Specification](../../docs/spec/ios-shared-lib.md) — design rationale and milestone history (M1-M4)
- [piper-plus Package.swift](../../Package.swift) — the SwiftPM manifest at the repo root
- [ORT SwiftPM Package](https://github.com/microsoft/onnxruntime-swift-package-manager) — Microsoft official ORT for Swift
