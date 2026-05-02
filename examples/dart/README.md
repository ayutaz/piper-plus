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
  `jniLibs/`. On iOS, use a framework or embed the `.dylib`. See [M5-20](../../docs/tickets/M5-20-android-aar.md) for Android packaging.
- **Native assets**: Dart's native assets RFC is experimental as of 2026. This
  example uses `DynamicLibrary.open()` with explicit paths. Once native assets
  stabilize, consider migrating to declarative native dependencies.

## Platform-specific library names

| Platform | Library name |
|----------|-------------|
| Linux | `libpiper_plus.so` |
| macOS | `libpiper_plus.dylib` |
| Windows | `piper_plus.dll` |
