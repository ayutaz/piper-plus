# Native Plugin Placement Guide

Place the pre-built `libpiper_plus` shared library for each target platform in this directory.
Download binaries from [GitHub Releases](https://github.com/ayutaz/piper-plus/releases).

## Directory Structure

```
Plugins/
  x86_64/
    piper_plus.dll              # Windows x64
    libpiper_plus.so            # Linux x64
  macOS/
    libpiper_plus.dylib         # macOS arm64 / x64
  Android/
    libs/
      arm64-v8a/
        libpiper_plus.so        # Android arm64
      armeabi-v7a/
        libpiper_plus.so        # Android armv7 (if supported)
  iOS/
    libpiper_plus.a             # iOS static library (if supported)
```

## Unity Import Settings

After placing the native libraries, select each file in Unity and configure the platform settings:

### Windows (piper_plus.dll)
- Platform: **Any Platform** or **Standalone Windows**
- CPU: **x86_64**

### macOS (libpiper_plus.dylib)
- Platform: **Standalone OSX**
- CPU: **AnySilicon** (Universal) or **Apple Silicon**

### Linux (libpiper_plus.so)
- Platform: **Standalone Linux**
- CPU: **x86_64**

### Android (libpiper_plus.so)
- Platform: **Android**
- CPU: Set per ABI folder (arm64-v8a, armeabi-v7a)

## Building from Source

To build the native library yourself:

```bash
# Clone piper-plus
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus

# Build shared library
cmake -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DPIPER_PLUS_BUILD_SHARED=ON
cmake --build build --config Release

# Output: build/libpiper_plus.{dll,dylib,so}
```

See the main repository [README](https://github.com/ayutaz/piper-plus) for dependencies and
detailed build instructions.

## OpenJTalk Dictionary

For Japanese TTS, the OpenJTalk dictionary is required. The native library will:

1. Auto-detect the dictionary if it's in a standard location
2. Use the path specified via `PiperModel.dictDir`
3. Auto-download if built with `dict-download` feature (default)

To bundle the dictionary with your app, place it in `StreamingAssets/dict/`
and set `dictDir` on your PiperModel asset.

## Troubleshooting

### DllNotFoundException
- Ensure the library is in the correct `Plugins/` subdirectory
- Check that platform import settings match your target
- On macOS, you may need to allow the library in System Preferences > Security

### EntryPointNotFoundException
- Version mismatch between the UPM package and native library
- Rebuild the native library from the same git tag as the UPM package
