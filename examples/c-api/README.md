# piper-plus C API Examples

Minimal examples demonstrating the piper-plus C shared library.

## Prerequisites

Download a release archive from [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) and extract it:

```bash
tar -xzf piper-plus-shared-linux-x64.tar.gz -C /usr/local
```

## Build with Makefile (pkg-config)

```bash
PKG_CONFIG_PATH=/usr/local/lib/pkgconfig make
```

## Build with CMake

```bash
cmake -B build -DCMAKE_PREFIX_PATH=/usr/local
cmake --build build
```

## Run

```bash
# One-shot synthesis (outputs WAV file)
./basic model.onnx /usr/local/share/open_jtalk/dic "Hello world." output.wav

# Streaming synthesis (prints chunk info)
./streaming model.onnx /usr/local/share/open_jtalk/dic "First. Second. Third."
```
