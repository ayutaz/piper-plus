# iOS Integration Guide

Cross-runtime guide for integrating piper-plus into iOS projects (Dart / Flutter / Godot / Swift).

> **Quick links:**
> - [Dart / Flutter quick reference](../../examples/dart/README.md#ios-integration)
> - [Godot iOS notes](../../examples/godot/README.md#ios-v1130)
> - [Swift example (manual drag-and-drop, SPM via Package.swift)](../../examples/swift/README.md)
> - [Specification](../spec/ios-shared-lib.md) (design rationale, milestone history)

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Xcode | 15+ (Xcode 16 recommended) |
| iOS Deployment Target | 15.0+ |
| Development host | Apple Silicon Mac (Intel Mac works via simulator universal slice) |
| Bitcode | Disabled (deprecated since Xcode 14) |

## Distribution Selection

piper-plus v1.13.0 ships **two iOS artifacts** during the migration period:

| Your situation | Recommended | Why |
|----------------|------------|-----|
| Flutter / Dart FFI for iOS | **xcframework.zip** | Xcode treats xcframework as first-class; supports device + simulator |
| Godot GDExtension for iOS | **xcframework.zip** | `ios.dependencies` in `.gdextension` expects xcframework |
| Swift project (SPM-aware) | **xcframework.zip + Package.swift** | M4 ships `Package.swift` at the repo root for `import PiperPlus` |
| Existing CMake project (v1.12.0 or earlier) | tar.gz (deprecated) | `libpiper_plus-ios-arm64-${VERSION}.tar.gz`; **removed in v1.14.0** |
| You want simulator support | **xcframework.zip only** | tar.gz is device-only |

> **Don't know which?** → **xcframework.zip**. The `tar.gz` is kept for v1.13.0 only as a transitional path.

## Step 1: Get piper-plus xcframework

```bash
gh release download v1.13.0 -p 'libpiper_plus-ios-*.xcframework.zip'
unzip libpiper_plus-ios-*.xcframework.zip
```

Result:

```
piper_plus.xcframework/
├── Info.plist
├── PrivacyInfo.xcprivacy            ← empty (no tracking, no Required Reason API)
├── ios-arm64/
│   ├── libpiper_plus.a
│   └── Headers/
│       ├── piper_plus.h
│       └── module.modulemap         ← enables Swift `import PiperPlus`
└── ios-arm64_x86_64-simulator/
    ├── libpiper_plus.a              ← lipo arm64 + x86_64
    └── Headers/
        ├── piper_plus.h
        └── module.modulemap
```

## Step 2: Get ONNX Runtime xcframework

ORT is **not bundled** with `piper_plus.xcframework` (consumer chooses). Options:

### Option A: CocoaPods (recommended for existing Podfiles)

```ruby
# ios/Podfile
pod 'onnxruntime-c', '1.17.0'
```

```bash
cd ios && pod install
```

### Option B: Swift Package Manager (recommended for SwiftPM projects)

```swift
// Package.swift
dependencies: [
    .package(
        url: "https://github.com/microsoft/onnxruntime-swift-package-manager",
        exact: "1.17.0"
    ),
]
```

### Option C: Microsoft CDN (manual)

```bash
curl -LO https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip
unzip pod-archive-onnxruntime-c-1.17.0.zip
```

> **sha256 (1.17.0)**: `1623e1150507d9e50554e3d3e5cf9abf75e1bfd8324b74a602acfe45343db871`

## Step 3: Embed & Sign Both xcframeworks

In Xcode for your iOS app target:

1. **Project Navigator** → drag both `piper_plus.xcframework` and `onnxruntime.xcframework`
2. **Targets** → **General** → **Frameworks, Libraries, and Embedded Content**
3. For **both** entries, choose **"Embed & Sign"**

> **The single most common iOS integration failure is leaving "Do Not Embed".** Both frameworks must be Embed & Sign.

> **Godot users**: Step 3 is automated by `ios.dependencies` in your `.gdextension` — no manual Embed & Sign required. See [`examples/godot/README.md` § iOS](../../examples/godot/README.md#ios-v1130).

## Step 4: Use from Your Language

### Dart / Flutter (FFI)

```dart
import 'dart:ffi';
import 'dart:io' show Platform;

final lib = Platform.isIOS
    ? DynamicLibrary.process()  // static archive symbols are linked into the app
    : DynamicLibrary.open('libpiper_plus.${Platform.isMacOS ? "dylib" : "so"}');
```

### Swift

```swift
import PiperPlus  // resolves via module.modulemap inside xcframework

let synthesizer = piper_plus_create_synthesizer(...)
```

> Requires the `module.modulemap` shipped in M2. For the SPM-based workflow (avoids manual drag-and-drop), see [Package.swift integration](../../examples/swift/README.md).

### Godot (GDScript)

```gdscript
var tts = $PiperTTS  # PiperTTS GDExtension node from examples/godot/
tts.model_path = "res://models/tsukuyomi.onnx"
tts.load_model()
tts.speak("こんにちは。")
```

## Time-To-Hello-World Target

| Stage | Target | Action |
|-------|--------|--------|
| 0:00–0:05 | 5 min | Read this guide, identify the artifact (xcframework.zip) |
| 0:05–0:15 | 10 min | Download xcframework + ORT, drag into Xcode, set Embed & Sign |
| 0:15–0:25 | 10 min | Wire `import` / `DynamicLibrary` / GDScript node |
| 0:25–0:30 | 5 min | Download an `.onnx` model, run synthesis, hear audio |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `dyld: Library not loaded: @rpath/onnxruntime.framework/onnxruntime` | ORT xcframework Embed missing | Step 3 — Embed & Sign onnxruntime.xcframework |
| `_OrtCreateEnv` undefined at link | piper_plus xcframework Embed missing | Step 3 — Embed & Sign piper_plus.xcframework |
| Build OK on simulator, crash on device (or vice versa) | Used a single-slice (device-only) artifact | Use the v1.13.0+ xcframework.zip (contains both slices) |
| `import PiperPlus` fails to compile in Swift | Old xcframework without modulemap | Use v1.13.0+ xcframework.zip (M2 includes modulemap) |
| App Store Connect rejects build for missing Privacy Manifest | Your app uses Required Reason APIs that ORT doesn't declare | Add a consolidated `PrivacyInfo.xcprivacy` to your app target covering ORT's API usage |
| Build size complaint | Single binary >2 GB unsigned per slice | Not a piper-plus issue — see [Apple's iOS app size limits](https://developer.apple.com/help/app-store-connect/reference/maximum-build-file-sizes) |

## Note: Compatibility Status (v1.13.0)

| Item | Status | Notes |
|------|--------|-------|
| device + simulator slices | ✓ | M2: `ios-arm64` + `ios-arm64_x86_64-simulator` |
| Swift `import PiperPlus` | ✓ | M2: `module.modulemap` shipped in xcframework |
| Empty Privacy Manifest | ✓ | M2: `PrivacyInfo.xcprivacy` shipped at xcframework root |
| ORT-side Privacy Manifest | ✗ | Microsoft has not shipped one as of 2026-05; consumer must add their own if Required Reason APIs are used |
| `.dSYM` for crash symbolication | ✗ | Tracked in a separate issue; xcframework binaries are stripped |
| visionOS / Mac Catalyst slices | ✗ | Tracked as M5 candidate; ORT visionOS support pending |
| App Extension / App Clip | ✗ | piper-plus + ORT (~35 MB) exceeds the 32 MB / 10 MB limits |

## Note: Migration from v1.12.0 tar.gz

If you were using `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (v1.12.0 or earlier — note that v1.11.0/v1.12.0 builds were not actually published to Releases due to the iOS build failure that #377 resolved):

1. **Download xcframework instead** — `libpiper_plus-ios-${VERSION}.xcframework.zip`
2. **Replace** `lib/libpiper_plus.a` direct link with `Embed & Sign` of the xcframework
3. **Update Xcode build settings** — remove explicit linker paths to `libpiper_plus.a`; the xcframework handles slice selection automatically
4. **For Swift consumers** — switch from C header bridging to `import PiperPlus` via `module.modulemap`

> **The tar.gz is kept in v1.13.0 for the migration period and will be removed in v1.14.0.** Plan migration during the v1.13.0 cycle.

## Further Reading

- [iOS Specification](../spec/ios-shared-lib.md) — design rationale, plan A milestones, "what would I do from scratch" reflections
- [ORT Version Matrix](../spec/ort-versions.md) — concrete ORT versions per runtime
- [CHANGELOG](../../CHANGELOG.md) — release history
