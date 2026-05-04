# Godot GDExtension Example for piper-plus

A reference implementation of a GDExtension wrapper that uses the **piper-plus C API shared library** for text-to-speech in Godot 4.3+.

> **CI verification status**: this example is **not** currently exercised by CI (no Godot/SCons toolchain in the GitHub Actions matrix). The wrapper targets a stable C ABI from `src/cpp/piper_plus.h`, which itself is regression-tested. The companion project [godot-piper-plus](https://github.com/ayutaz/godot-piper-plus) provides a more polished, separately-maintained Godot integration.

This example demonstrates how to wrap the piper-plus C API into a `PiperTTS` node (derived from `AudioStreamPlayer`) that can be used directly from GDScript.

## Directory Structure

```
examples/godot/
  SConstruct                   # SCons build script (~15 lines)
  src/
    register_types.h           # GDExtension entry point
    register_types.cpp
    piper_tts_node.h           # PiperTTS node (AudioStreamPlayer derived)
    piper_tts_node.cpp
  demo/
    project.godot              # Godot demo project
    main.tscn                  # Main scene
    main.gd                    # GDScript demo
    bin/
      piper_tts.gdextension    # GDExtension descriptor
```

## Prerequisites

1. **Godot 4.3+** installed
2. **piper-plus shared library** installed and discoverable via `pkg-config`:
   ```bash
   # Verify installation
   pkg-config --cflags --libs piper_plus
   ```
   If not installed, download from [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) and extract:
   ```bash
   tar -xzf piper-plus-shared-linux-x64.tar.gz -C /usr/local
   ```
3. **godot-cpp** (Godot C++ bindings):
   ```bash
   cd examples/godot
   git clone --depth 1 --branch godot-4.3-stable \
     https://github.com/godotengine/godot-cpp.git
   ```
4. **SCons** build system:
   ```bash
   pip install scons
   ```

## Build

```bash
cd examples/godot

# Debug build
scons

# Release build
scons target=template_release
```

The built shared library is output to `demo/bin/`.

### Custom pkg-config Path

If piper-plus is installed in a non-standard location:

```bash
PKG_CONFIG_PATH=/path/to/piper-plus/lib/pkgconfig scons
```

## Run the Demo

1. Open the `demo/` folder as a Godot project
2. Enter the path to your `.onnx` model in the "Model" field
3. Click "Load Model"
4. Enter text and click "Speak" or "Speak (Streaming)"

### Download a Model

```bash
curl -LO https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-6lang-v2-fixed.onnx
curl -LO https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-6lang-v2-fixed.onnx.json
```

## PiperTTS Node API

### Properties (Inspector)

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `model_path` | String | `""` | Path to `.onnx` model file |
| `config_path` | String | `""` | Path to `.json` config (auto-detected if empty) |
| `speaker_id` | int | `0` | Speaker index |
| `language_id` | int | `-1` | Language index (`-1` = auto-detect) |
| `noise_scale` | float | `0.667` | VITS noise scale |
| `length_scale` | float | `1.0` | VITS length scale (speed) |

### Methods

| Method | Description |
|--------|-------------|
| `load_model() -> bool` | Load the ONNX model. Returns `true` on success. |
| `speak(text: String)` | One-shot synthesis and playback |
| `speak_streaming(text: String)` | Streaming synthesis (sentence-by-sentence) and playback |
| `get_num_speakers() -> int` | Number of speakers in the loaded model |
| `get_num_languages() -> int` | Number of languages in the loaded model |
| `is_model_loaded() -> bool` | Whether a model is currently loaded |

### Signals

| Signal | Description |
|--------|-------------|
| `synthesis_complete` | Emitted after synthesis finishes and audio playback begins |

### GDScript Example

```gdscript
var tts = $PiperTTS
tts.model_path = "res://models/tsukuyomi.onnx"
tts.load_model()

# One-shot
tts.speak("Hello, world!")

# Streaming (lower latency for long text)
tts.speak_streaming("First sentence. Second sentence. Third sentence.")

# Wait for completion
await tts.synthesis_complete
```

## Exporting Your Project

When exporting a Godot project, ensure the following files are included alongside the executable:

1. **piper-plus shared library** (`libpiper_plus.so` / `libpiper_plus.dylib` / `piper_plus.dll`)
2. **ONNX Runtime shared library** (`libonnxruntime.so` / etc.)
3. **OpenJTalk dictionary** (`share/open_jtalk/dic/`) -- required for Japanese
4. **Your .onnx model and .json config**

On Linux/macOS, set `LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH` if the shared libraries are not in a standard location. On Windows, place DLLs next to the executable.

## Migration from godot-piper-plus (Source Copy)

[godot-piper-plus](https://github.com/ayutaz/godot-piper-plus) currently copies 25+ C++ source files from piper-plus and compiles them directly into the GDExtension. The C API shared library approach replaces this with a thin wrapper (~200 lines of C++) that links against a pre-built `libpiper_plus`.

### Before (Source Copy)

```
godot-piper-plus/
  src/
    piper_tts.h / .cpp         # GDExtension wrapper
    register_types.h / .cpp    # Entry point
    # ... 25+ copied piper-plus source files ...
    vits/models.cpp
    vits/lightning.cpp
    phonemize/*.cpp
    ...
  SConstruct                   # Must compile all piper-plus sources
```

- Updating piper-plus requires re-copying all source files
- Build dependencies (onnxruntime headers, jpreprocess, etc.) must be managed manually
- Compile time is long due to large codebase

### After (C API Shared Library)

```
examples/godot/
  src/
    piper_tts_node.h / .cpp    # GDExtension wrapper (~150 lines)
    register_types.h / .cpp    # Entry point (~30 lines)
  SConstruct                   # 3 lines: SConscript + ParseConfig + SharedLibrary
```

- Updating piper-plus: just replace `libpiper_plus.so` / `.dylib` / `.dll`
- No C++ dependency management -- all handled by the shared library
- Compile time: seconds instead of minutes

### Migration Steps

1. **Install piper-plus shared library** via release archive or `cmake --install`
2. **Replace** the `src/` directory with the 4 files from this example
3. **Replace** `SConstruct` with the 3-line version using `pkg-config`
4. **Copy** `demo/bin/piper_tts.gdextension` to your project's `bin/` directory
5. **Ship** `libpiper_plus.so` (+ `libonnxruntime.so`) alongside your exported game

### Feature Comparison

| Feature | godot-piper-plus (source copy) | This example (C API) |
|---------|-------------------------------|---------------------|
| Wrapper code size | ~25+ files | 4 files (~200 lines) |
| Build time | Minutes | Seconds |
| piper-plus update | Re-copy all sources | Replace shared library |
| Custom dictionary | Requires source changes | `piper_plus_load_custom_dict()` via C API |
| Streaming synthesis | Custom implementation | `piper_plus_synth_start/next()` via C API |
| Thread safety | Varies | Documented: one engine per thread |
| Platforms | Linux, Windows, macOS | Linux, Windows, macOS, **iOS (xcframework, v1.13.0+)** |

## Platform Notes

### Linux

```bash
# Ensure libpiper_plus.so is in LD_LIBRARY_PATH or install to /usr/local/lib
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
```

### macOS

```bash
# Ensure libpiper_plus.dylib is discoverable
export DYLD_LIBRARY_PATH=/usr/local/lib:$DYLD_LIBRARY_PATH
```

### Windows

Place `piper_plus.dll` and `onnxruntime.dll` in the same directory as the Godot executable or the exported game executable.

### iOS (v1.13.0+)

- **Architecture**: arm64 (device) + arm64/x86_64 (simulator universal)
- **Status**: Stable
- **Distribution**: `libpiper_plus-ios-v${VERSION}.xcframework.zip` (Mach-O static archive, modulemap + empty PrivacyInfo bundled)
- **ORT bundling**: separate — consumer must obtain `onnxruntime.xcframework` via CocoaPods, SPM, or [Microsoft CDN](https://download.onnxruntime.ai/)

> **Note: this demo's `bin/piper_tts.gdextension` does NOT include iOS entries** because the demo's `piper_tts_init` GDExtension wrapper is built only for desktop platforms (Linux / macOS / Windows) at this time. Building the demo wrapper into a `piper_tts.xcframework` for iOS is a follow-up task. The snippet below is a **template for your own consumer GDExtension** that wraps piper-plus directly.

#### GDExtension descriptor (`piper_tts.gdextension`)

```ini
[libraries]
ios.debug   = "res://addons/piper-plus/ios/piper_plus.xcframework"
ios.release = "res://addons/piper-plus/ios/piper_plus.xcframework"

[dependencies]
ios.debug   = {"res://addons/piper-plus/ios/onnxruntime.xcframework" : ""}
ios.release = {"res://addons/piper-plus/ios/onnxruntime.xcframework" : ""}
```

The `ios.dependencies` entry instructs Godot's iOS exporter to embed `onnxruntime.xcframework` automatically — no manual `Embed & Sign Frameworks` step required from the consumer.

#### Setup

```bash
# Place inside your Godot project
mkdir -p addons/piper-plus/ios
gh release download v1.13.0 -p 'libpiper_plus-ios-*.xcframework.zip' \
  -O addons/piper-plus/ios/libpiper_plus-ios.xcframework.zip
unzip addons/piper-plus/ios/libpiper_plus-ios.xcframework.zip \
  -d addons/piper-plus/ios/

# ORT (CDN option, see ios-integration.md for CocoaPods/SPM alternatives)
curl -LO https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip
unzip pod-archive-onnxruntime-c-1.17.0.zip -d addons/piper-plus/ios/
```

For the cross-runtime guide (Dart / Godot / Swift) see [`docs/guides/ios-integration.md`](../../docs/guides/ios-integration.md).

#### Note: App Extension / App Clip not supported

piper-plus + ORT is ~35MB (compressed slice). iOS App Extension uncompressed slice limit is 32 MB and App Clip is 10 MB — piper-plus cannot fit inside either. Targeting full iOS apps only.

## Thread Safety

The piper-plus C API engine handle (`PiperPlusEngine`) is **not thread-safe**. This example calls the C API from Godot's main thread. If you need background synthesis, create a separate engine instance per thread and protect shared state with a mutex.
