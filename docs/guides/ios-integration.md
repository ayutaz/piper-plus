# iOS Integration Guide

Cross-runtime guide for integrating piper-plus into iOS projects (Dart / Flutter / Godot / Swift).

> **Quick links:**
> - [Dart / Flutter quick reference](../../examples/dart/README.md#ios-integration)
> - [Godot iOS notes](../../examples/godot/README.md#ios-v1130)
> - [Swift example (manual drag-and-drop, SPM via Package.swift)](../../examples/swift/README.md)
> - [Specification](../spec/ios-shared-lib.md) (design rationale)

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
        from: "1.17.0"  // semver range: 1.17.x compatible; bump cautiously
    ),
]
```

> **Version compatibility**: piper-plus is currently link-tested against ORT 1.17.0. See [`docs/spec/ort-versions.md`](../spec/ort-versions.md) for the full per-runtime ORT matrix. `from:` allows minor/patch bumps within the 1.x line; if a future ORT release introduces a breaking ABI change, downgrade with `exact:` until piper-plus is recompiled. Consumers using the SPM `piper-plus` package don't need to declare ORT themselves — it's pulled transitively (v1.13.0+).

### Option C: Microsoft CDN (manual)

```bash
curl -LO https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip
unzip pod-archive-onnxruntime-c-1.17.0.zip
```

> **sha256 (1.17.0)**: `1623e1150507d9e50554e3d3e5cf9abf75e1bfd8324b74a602acfe45343db871`

## Step 3: Link PiperPlus + Embed & Sign ORT

`piper_plus.xcframework` ships a **static archive** (`libpiper_plus.a`) — its symbols are linked into your app at link time, so it does NOT need to be embedded. `onnxruntime.xcframework` ships a **dynamic framework** (Mach-O dylib) — it must be embedded and signed so iOS can load it at runtime.

In Xcode for your iOS app target:

1. **Project Navigator** → drag both `piper_plus.xcframework` and `onnxruntime.xcframework` into the project
2. **Targets** → **General** → **Frameworks, Libraries, and Embedded Content**
3. Set the **"Embed"** column as follows:
   - `piper_plus.xcframework` → **"Do Not Embed"** (static archive; linked-only)
   - `onnxruntime.xcframework` → **"Embed & Sign"** (dynamic framework; required for `dyld` to find it)

> **The most common iOS integration failure is leaving the ORT framework as "Do Not Embed"** — that triggers `dyld: Library not loaded: @rpath/onnxruntime.framework/onnxruntime` at app launch. Always Embed & Sign the ORT framework.

> **Godot users**: Step 3 is automated by `ios.dependencies` in your `.gdextension` — no manual Embed & Sign required. See [`examples/godot/README.md` § iOS](../../examples/godot/README.md#ios-v1130).

## Step 4 (Japanese TTS only): Bundle the OpenJTalk Dictionary

Japanese synthesis requires the OpenJTalk MeCab dictionary (`open_jtalk_dic_utf_8-1.11`, ~30 MB uncompressed). On desktop, piper-plus auto-downloads this; **on iOS, the App Sandbox forbids `popen` / `system` so auto-download is disabled** — the consumer app must bundle the dictionary and pass its path explicitly.

### 4.1 Acquire the dictionary

Use the version that ships with `pyopenjtalk-plus` (the same one piper-plus uses on desktop):

```bash
# One-time, from any host machine:
curl -L -o open_jtalk_dic.tar.gz \
  https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz
tar -xzf open_jtalk_dic.tar.gz
# Result: open_jtalk_dic_utf_8-1.11/  (contains char.bin, sys.dic, ...)
```

Verify the SHA-256 (against a trusted source) before bundling — the dictionary is a runtime dependency.

### 4.2 Add to your Xcode project as a folder reference

1. Drag `open_jtalk_dic_utf_8-1.11/` into the Xcode project navigator.
2. In the import dialog, select **"Create folder references"** (NOT "Create groups"). This preserves the directory layout in the `.app` bundle.
3. Confirm "Copy items if needed" and add to your target.

The directory now appears in your built `.app` at `<MyApp.app>/open_jtalk_dic_utf_8-1.11/`.

### 4.3 Pass the path to piper-plus

```swift
import PiperPlus
import Foundation

guard let bundleDicPath = Bundle.main.path(forResource: "open_jtalk_dic_utf_8-1.11", ofType: nil) else {
    fatalError("OpenJTalk dictionary not bundled in app target")
}

var config = piper_plus_default_config()
config.dict_dir = (bundleDicPath as NSString).utf8String
let synth = piper_plus_create(modelPath, configPath, &config)
```

(Adjust to the actual `piper_plus_create` signature — see `piper_plus.h` for the exact init API.)

### 4.4 Avoid: do NOT rely on auto-download

On iOS, `piper_plus_create` for a Japanese model with no `dict_dir` returns a configuration error. The desktop fallback to download via curl/wget is **disabled by design** (`src/cpp/openjtalk_ios_stub.c`).

> **Bundle size tip**: The dictionary is ~30 MB uncompressed. If your app's user count for Japanese synthesis is small, consider gating the dictionary copy behind a runtime download from your own CDN (using `URLSession`) and caching to `Application Support/`. The piper-plus C API accepts any local path for `dict_dir`.

## Step 5: Use from Your Language

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
| `dyld: Library not loaded: @rpath/onnxruntime.framework/onnxruntime` (runtime) | ORT framework not embedded | Step 3 — set onnxruntime.xcframework to **Embed & Sign** |
| `_OrtCreateEnv` undefined symbol (link time) | ORT framework not added to the target / wrong slice picked | Confirm onnxruntime.xcframework is in **Frameworks, Libraries, and Embedded Content**, and that the build's `EFFECTIVE_PLATFORM_NAME` matches the slice (device build → `ios-arm64`, simulator build → `ios-arm64_x86_64-simulator`) |
| `_piper_plus_*` undefined symbol (link time) | piper_plus.xcframework not added to the target | Step 3 — drag piper_plus.xcframework into Frameworks (Embed = "Do Not Embed" is correct, but it must still be **linked**) |
| `piper_plus_create` returns "OpenJTalk dictionary not found" (runtime, JA models only) | Step 4 skipped or `dict_dir` not passed | Bundle `open_jtalk_dic_utf_8-1.11/` as a folder reference and pass `Bundle.main.path(forResource:)` to `piper_plus_create` config |
| `Failed to get OpenJTalk dictionary path` in console (JA models) | iOS stub returns NULL when `dict_dir` is unset | Same as above — Step 4 is mandatory for Japanese synthesis on iOS |
| Code Signing failed (Embed Frameworks phase) | Provisioning profile mismatch on bundled ORT framework | In Xcode → target → Signing & Capabilities, match the team identifier; use automatic signing for development |
| Embedded Binary not found (`onnxruntime.framework`) | Drag added to Frameworks but not Embed Frameworks build phase | Open Build Phases → Embed Frameworks → ensure `onnxruntime.xcframework` is listed and "Code Sign On Copy" is checked |
| `module.modulemap` not found in Swift import | xcframework's `Headers/` not on `HEADER_SEARCH_PATHS` | Don't override `HEADER_SEARCH_PATHS` in build settings — let Xcode's xcframework integration handle paths automatically |
| Build OK on simulator, crash on device (or vice versa) | Used a single-slice (device-only) artifact | Use the v1.13.0+ xcframework.zip (contains both slices) |
| `import PiperPlus` fails to compile in Swift | Old xcframework without modulemap | Use v1.13.0+ xcframework.zip (M2 includes modulemap) |
| App Store Connect rejects build for missing Privacy Manifest | Your app uses Required Reason APIs that ORT doesn't declare | Add a consolidated `PrivacyInfo.xcprivacy` to your app target covering ORT's API usage |
| Build size complaint | Single binary >2 GB unsigned per slice | Not a piper-plus issue — see [Apple's iOS app size limits](https://developer.apple.com/help/app-store-connect/reference/maximum-build-file-sizes) |

## Note: C++ Symbol Visibility (Static Archive Caveat)

`libpiper_plus.a` is a **static archive** containing C++ third-party code (`fmt::`, `spdlog::`, `nlohmann::json`) and the internal `piper::` namespace. By construction, static archive symbols are visible to the linker at consumer link time — `__attribute__((visibility("hidden")))` and `-fvisibility=hidden` only affect dynamic library export tables, not archive symbol resolution.

**Practical impact**: if your app also links another static archive that defines `fmt::` or `spdlog::` symbols (e.g., another C++ library with the same vendored copies), you may hit ODR (One Definition Rule) violations or duplicate-symbol link errors.

**Recommended mitigations** (in order of preference):

1. **`-load_hidden` linker flag** (Xcode 14+, ld64): pass `-Wl,-load_hidden,$(PROJECT_DIR)/Frameworks/piper_plus.xcframework/.../libpiper_plus.a` in the consumer target's **Other Linker Flags**. ld64 will hide all symbols from this archive in the final binary's export table, eliminating ODR collisions with other archives.
2. **`-exported_symbols_list`**: if you want even tighter control, create a `piper_plus_exports.txt` with one symbol per line listing only `_piper_plus_*` (the public C API), and add `-Wl,-exported_symbols_list,$(PROJECT_DIR)/piper_plus_exports.txt`. This works for the **final app binary** export table.
3. **Use the `import PiperPlus` Swift module**: Swift consumers automatically get only the `piper_plus_*` C API surface via `module.modulemap`'s `umbrella header "piper_plus.h"`. The implementation symbols remain in the static archive but are not exposed at the language level.

If you don't link any other C++ static archives in your app, no action is needed — Xcode's dead-code stripping removes unused symbols from the final binary.

## Note: Compatibility Status (v1.13.0)

| Item | Status | Notes |
|------|--------|-------|
| device + simulator slices | ✓ | M2: `ios-arm64` + `ios-arm64_x86_64-simulator` |
| Swift `import PiperPlus` | ✓ | M2: `module.modulemap` shipped in xcframework |
| Privacy Manifest reference | ⚠ informational | `PrivacyInfo.xcprivacy` is bundled at xcframework root, but Apple's App Store scanner reads manifests from `<Foo.framework>/PrivacyInfo.xcprivacy` (per-framework bundle root) — **not** from `.xcframework` containers carrying static archives. Treat the bundled file as a reference only; you must consolidate API usage in your app target's `PrivacyInfo.xcprivacy` (see [App Store Submission](#app-store-submission-checklist) below). |
| ORT-side Privacy Manifest | ✗ | Microsoft has not shipped one as of 2026-05; consumer must add their own if Required Reason APIs are used |
| `.dSYM` for crash symbolication | ✗ | Tracked in a separate issue; xcframework binaries are stripped |
| visionOS / Mac Catalyst slices | ✗ | Tracked as M5 candidate; ORT visionOS support pending |
| App Extension / App Clip | ✗ | piper-plus + ORT (~35 MB) exceeds the 32 MB / 10 MB limits |

## App Store Submission Checklist

iOS 17+ (since Spring 2024) requires a Privacy Manifest declaring usage of certain "Required Reason APIs". Both piper-plus and ONNX Runtime use such APIs internally. Because piper-plus ships as a **static archive**, the manifest at the xcframework root is informational only — Apple's scanner resolves manifests at the **app target level**.

### Step A: Create your app's Privacy Manifest

In Xcode: **File → New → File from Template** → Resource → **App Privacy** → save as `PrivacyInfo.xcprivacy` in your app target.

### Step B: Declare Required Reason API usage

ORT (and to a smaller extent piper-plus) likely call APIs in these categories. Add to your manifest:

```xml
<dict>
    <key>NSPrivacyTracking</key>
    <false/>
    <key>NSPrivacyTrackingDomains</key>
    <array/>
    <key>NSPrivacyCollectedDataTypes</key>
    <array/>
    <key>NSPrivacyAccessedAPITypes</key>
    <array>
        <!-- ORT uses mach_absolute_time / clock_gettime for profiling -->
        <dict>
            <key>NSPrivacyAccessedAPIType</key>
            <string>NSPrivacyAccessedAPICategorySystemBootTime</string>
            <key>NSPrivacyAccessedAPITypeReasons</key>
            <array>
                <string>35F9.1</string>  <!-- internal performance measurement -->
            </array>
        </dict>
        <!-- piper-plus reads model files, ORT reads ONNX graph data -->
        <dict>
            <key>NSPrivacyAccessedAPIType</key>
            <string>NSPrivacyAccessedAPICategoryFileTimestamp</string>
            <key>NSPrivacyAccessedAPITypeReasons</key>
            <array>
                <string>C617.1</string>  <!-- inside app container -->
            </array>
        </dict>
        <!-- Optional: only if you read environment-derived disk paths -->
        <dict>
            <key>NSPrivacyAccessedAPIType</key>
            <string>NSPrivacyAccessedAPICategoryDiskSpace</string>
            <key>NSPrivacyAccessedAPITypeReasons</key>
            <array>
                <string>E174.1</string>
            </array>
        </dict>
    </array>
</dict>
```

The reason codes above are taken from Apple's [Required Reason API list](https://developer.apple.com/documentation/bundleresources/privacy_manifest_files/describing_use_of_required_reason_api). Adjust per-category if your app's actual usage differs.

### Step C: Encryption Export Compliance

In `Info.plist` add:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

ORT and piper-plus do not use encryption beyond standard TLS (which is exempt under EAR §740.17(b)(1)).

### Step D: TestFlight / App Store Connect

- **Notarization**: not required for iOS (only macOS).
- **Archive**: Xcode → Product → Archive → Distribute App → App Store Connect.
- The validation step automatically reads `PrivacyInfo.xcprivacy` and surfaces missing categories in the Archive Organizer.

## Note: Migration from v1.12.0 tar.gz

If you were using `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (v1.12.0 or earlier — note that v1.11.0/v1.12.0 builds were not actually published to Releases due to the iOS build failure that #377 resolved):

1. **Download xcframework instead** — `libpiper_plus-ios-v${VERSION}.xcframework.zip`
2. **Replace** `lib/libpiper_plus.a` direct link with `Embed & Sign` of the xcframework
3. **Update Xcode build settings** — remove explicit linker paths to `libpiper_plus.a`; the xcframework handles slice selection automatically
4. **For Swift consumers** — switch from C header bridging to `import PiperPlus` via `module.modulemap`

> **The tar.gz is kept in v1.13.0 for the migration period and will be removed in v1.14.0.** Plan migration during the v1.13.0 cycle.

## Further Reading

- [iOS Specification](../spec/ios-shared-lib.md) — design rationale and Plan A details
- [ORT Version Matrix](../spec/ort-versions.md) — concrete ORT versions per runtime
- [CHANGELOG](../../CHANGELOG.md) — release history
