# piper-plus Dart FFI Example

Dart/Flutter FFI example for the piper-plus C shared library.
Demonstrates one-shot and streaming text-to-speech synthesis using `dart:ffi`.

> **CI verification status**: this example is **not** currently exercised by CI (no Dart toolchain in the GitHub Actions matrix). The bindings target a stable C ABI from `src/cpp/piper_plus.h`, which itself is regression-tested. Please report issues if Dart/Flutter integration breaks.

## Prerequisites

- **Dart SDK** >= 3.1.0 (required for `NativeCallable.listener`)
- **piper-plus shared library** from [GitHub Releases](https://github.com/ayutaz/piper-plus/releases)

### Install the shared library

```bash
# Linux
tar -xzf piper-plus-shared-linux-x64.tar.gz -C /usr/local
sudo ldconfig

# macOS
tar -xzf piper-plus-shared-macos-arm64.tar.gz -C /usr/local

# Windows — extract to a directory on PATH, or set the full path in code
```

### Download a model

```bash
curl -LO https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx
curl -LO https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx.json
```

The OpenJTalk dictionary is bundled in the release archive at `share/open_jtalk/dic/`.

## Setup

```bash
cd examples/dart
dart pub get
```

## Generate FFI bindings (optional)

A hand-written bindings skeleton is provided at `lib/piper_plus_bindings.dart`.
To regenerate from `piper_plus.h` using ffigen:

```bash
dart run ffigen --config ffigen.yaml
```

## Run examples

### One-shot synthesis

```bash
dart run example/main.dart multilingual-test-medium.onnx /usr/local/share/open_jtalk/dic \
    "Hello, this is piper-plus." output.wav
```

### Streaming synthesis

```bash
dart run example/streaming.dart multilingual-test-medium.onnx /usr/local/share/open_jtalk/dic \
    "First sentence. Second sentence. Third sentence." streaming.wav
```

## Project structure

```
examples/dart/
  pubspec.yaml                      # Dart package definition (sdk >=3.1.0)
  ffigen.yaml                       # ffigen config for piper_plus.h
  lib/
    piper_plus_bindings.dart        # Low-level FFI bindings (ffigen skeleton)
    piper_plus.dart                 # High-level Dart API wrapper
  example/
    main.dart                       # One-shot synthesis demo
    streaming.dart                  # Streaming synthesis demo
```

## API overview

```dart
import 'lib/piper_plus.dart';

// Create engine
final tts = PiperPlus.load(
  libraryPath: 'libpiper_plus.so',  // or .dylib / .dll
  modelPath: 'model.onnx',
  dictDir: '/usr/local/share/open_jtalk/dic',
);

// One-shot: returns complete WAV as Uint8List
final wav = tts.synthesize('Hello world.', speakerId: 0);
File('output.wav').writeAsBytesSync(wav);

// Streaming: yields PCM chunks via Stream
await for (final chunk in tts.synthesizeStream('First. Second. Third.')) {
  // chunk is Uint8List of 16-bit PCM samples
  audioPlayer.feed(chunk);
}

// Clean up
tts.dispose();
```

## Flutter integration notes

- **Isolates**: `piper_plus_synthesize_streaming` is synchronous on the C side.
  In a Flutter app, run synthesis in a separate `Isolate` to avoid blocking the
  UI thread. The streaming example uses `scheduleMicrotask` for simplicity.
- **Library path**: On Android, the `.so` is typically bundled via the AAR in
  `jniLibs/`. On iOS, use the **xcframework** approach described in [iOS Integration](#ios-integration) below. Pre-built Android AAR packaging is not yet tracked — please open an issue at [ayutaz/piper-plus/issues](https://github.com/ayutaz/piper-plus/issues) if you need it.
- **Native assets**: Dart's native assets RFC is experimental as of 2026. This
  example uses `DynamicLibrary.open()` with explicit paths. Once native assets
  stabilize, consider migrating to declarative native dependencies.
- **iOS Mach-O dead-code stripping** (most common Flutter-on-iOS bug):
  `DynamicLibrary.process()` only resolves symbols that ld kept in the final
  app binary. Static archives like `libpiper_plus.a` are subject to dead-code
  stripping — if no Swift / Obj-C code references `piper_plus_*`, all symbols
  get stripped and `DynamicLibrary.process()` returns `Symbol not found` at
  the first FFI call. **Fix**: in `ios/Runner.xcodeproj` → Build Settings →
  **Other Linker Flags**, add:
  ```
  -force_load $(BUILT_PRODUCTS_DIR)/PiperPlus/piper_plus.xcframework/ios-arm64/libpiper_plus.a
  ```
  (or the matching simulator path for sim builds). Alternatively, use
  `DynamicLibrary.open(...)` with an explicit path to the framework binary
  inside the app bundle if you switched to a dynamic framework variant.

## iOS Integration

> **For the full cross-runtime guide (Dart / Godot / Swift), see [`docs/guides/ios-integration.md`](../../docs/guides/ios-integration.md).** This section is the Dart-specific quick reference.

### Prerequisites

- **Xcode** 15+ (Xcode 16 recommended)
- **iOS Deployment Target** 15.0+
- **Apple Silicon Mac** for development (Intel Macs work via the simulator universal slice)

### Distribution selection (v1.13.0)

| Your situation | Recommended artifact | Why |
|----------------|---------------------|-----|
| Flutter / Dart FFI for iOS | **`libpiper_plus-ios-v${VERSION}.xcframework.zip`** | Xcode treats xcframework as first-class, supports both device and simulator |
| Existing CMake project (v1.12.0 or earlier) | `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (device-only, deprecated) | v1.13.0 transitional; **will be removed in v1.14.0** |

> **Don't know which?** Choose the **xcframework.zip** — it's the supported path going forward.

### Step 1: Download piper-plus xcframework

```bash
gh release download v1.13.0 -p 'libpiper_plus-ios-*.xcframework.zip'
unzip libpiper_plus-ios-*.xcframework.zip
# Result: piper_plus.xcframework/
#   ├── Info.plist
#   ├── PrivacyInfo.xcprivacy        (empty Privacy Manifest)
#   ├── ios-arm64/
#   │   ├── libpiper_plus.a
#   │   └── Headers/
#   │       ├── piper_plus.h
#   │       └── module.modulemap     (for Swift `import PiperPlus`)
#   └── ios-arm64_x86_64-simulator/
#       └── (same structure)
```

### Step 2: Download ONNX Runtime xcframework (3 options)

ORT is **not** bundled with `piper_plus.xcframework` — the consumer chooses how to obtain it.

#### Option A: CocoaPods (recommended for existing Podfiles)

```ruby
# ios/Podfile
pod 'onnxruntime-c', '1.17.0'
```

```bash
cd ios && pod install
```

#### Option B: Swift Package Manager (recommended for pure SPM projects)

```swift
// Package.swift — semver range, see docs/spec/ort-versions.md for the matrix
.package(url: "https://github.com/microsoft/onnxruntime-swift-package-manager", from: "1.17.0")
```

#### Option C: Microsoft CDN (manual)

```bash
curl -LO https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip
unzip pod-archive-onnxruntime-c-1.17.0.zip
# Result: onnxruntime.xcframework/
```

> **sha256 (1.17.0)**: `1623e1150507d9e50554e3d3e5cf9abf75e1bfd8324b74a602acfe45343db871`

### Step 3: Add to Xcode (Link PiperPlus + Embed & Sign ORT)

`piper_plus.xcframework` ships a **static archive** (`libpiper_plus.a`) → linked-only, no embedding required. `onnxruntime.xcframework` ships a **dynamic framework** → must be Embed & Sign so iOS can load it at runtime.

In Xcode for your Flutter project's iOS target (`Runner.xcodeproj`):

1. **Project Navigator** → drag `piper_plus.xcframework` and `onnxruntime.xcframework` into the project
2. **Targets** → **General** → **Frameworks, Libraries, and Embedded Content**
3. Set the **"Embed"** column:
   - `piper_plus.xcframework` → **"Do Not Embed"** (static archive — linked-only)
   - `onnxruntime.xcframework` → **"Embed & Sign"** (dynamic framework — required for `dyld`)

> **Common failure**: leaving `onnxruntime.xcframework` as `"Do Not Embed"` causes `dyld: Library not loaded: @rpath/onnxruntime.framework/onnxruntime` at app launch. The ORT framework MUST be Embed & Sign.

### Step 4: Use from Dart FFI

```dart
import 'dart:ffi';
import 'dart:io' show Platform;

final lib = Platform.isIOS
    ? DynamicLibrary.process()  // statically linked from xcframework, symbols are in process
    : DynamicLibrary.open(...);
```

On iOS, the static archive in the xcframework gets linked into the consumer app, so `DynamicLibrary.process()` resolves the symbols. ORT framework symbols resolve via the embedded dynamic framework.

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `dyld: Library not loaded: @rpath/onnxruntime.framework/onnxruntime` (runtime) | ORT framework not embedded | Step 3 — set onnxruntime.xcframework to **Embed & Sign** |
| `_OrtCreateEnv` undefined symbol (link time) | ORT framework not added to the target / wrong slice picked | Confirm onnxruntime.xcframework is in **Frameworks, Libraries, and Embedded Content**, and that the slice (`ios-arm64` for device, `ios-arm64_x86_64-simulator` for simulator) matches your build target |
| `_piper_plus_*` undefined symbol (link time) | piper_plus.xcframework not added to the target | Step 3 — drag piper_plus.xcframework into Frameworks (Embed = "Do Not Embed" is correct, but it must still be **linked**) |
| Simulator crash on Apple Silicon Mac | Old xcframework without simulator slice | Use v1.13.0+ xcframework.zip (M2 includes simulator slice) |
| App Store Connect rejects build | Missing Privacy Manifest for ORT | Add your own `PrivacyInfo.xcprivacy` covering Microsoft's ORT (piper-plus side already includes empty Manifest) |

### Note: Privacy Manifest (iOS 17+)

- piper-plus xcframework ships with an **empty** `PrivacyInfo.xcprivacy` (no tracking, no Required Reason API access)
- **ONNX Runtime does not yet ship a Privacy Manifest** (Microsoft, as of 2026-05). If your app uses Required Reason APIs (file timestamp, system boot time, disk space, user defaults), add your own consolidated `PrivacyInfo.xcprivacy` to your app target

### Note: App Extension / App Clip size limits

- piper-plus + ORT is ~35MB (compressed slice); the iOS App Extension uncompressed slice limit is **32 MB** — **piper-plus + ORT cannot fit inside an App Extension**
- App Clip's 10 MB uncompressed limit makes piper-plus integration impossible there too

## Platform-specific library names

| Platform | Library name |
|----------|-------------|
| Linux | `libpiper_plus.so` |
| macOS | `libpiper_plus.dylib` |
| Windows | `piper_plus.dll` |
| iOS | `piper_plus.xcframework` (static archive inside, see [iOS Integration](#ios-integration)) |
