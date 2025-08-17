# OpenJTalk ARM64 Linux Support

## Overview

This document describes the implementation of OpenJTalk support for ARM64 Linux platforms, resolving issue #42.

## Technical Approach

### Problem

OpenJTalk uses autotools build system which has difficulties with cross-compilation for ARM64 Linux:
- Complex configure scripts that don't properly detect cross-compilation environment
- Multiple internal libraries that need correct linking
- MeCab dependency requires proper cross-compilation setup

### Solution

We switched to CMake-based build for ARM64 Linux, similar to the Windows build approach:

1. **Use existing CMake build**: The project already has `OpenJTalk_CMakeLists.txt` for Windows
2. **Extend for Linux ARM64**: Added Linux-specific settings and cross-compilation support
3. **Leverage Docker toolchain**: Use the existing ARM64 cross-compilation tools in Docker

## Implementation Details

### CMakeLists.txt Changes

1. **HTSEngine configuration for ARM64 Linux**:
```cmake
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  # Linux ARM64 cross-compilation
  set(CONFIGURE_HOST "--host=aarch64-linux-gnu")
  set(CONFIGURE_ENV "CC=aarch64-linux-gnu-gcc" "CXX=aarch64-linux-gnu-g++" "AR=aarch64-linux-gnu-ar" "RANLIB=aarch64-linux-gnu-ranlib")
```

2. **OpenJTalk CMake build for ARM64 Linux**:
```cmake
# Use CMake build for Windows and Linux ARM64
if(WIN32 OR (CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" AND CMAKE_SYSTEM_NAME STREQUAL "Linux"))
```

3. **Cross-compilation toolchain settings**:
```cmake
# Linux ARM64
list(APPEND OPENJTALK_CMAKE_ARGS
  -DHTS_ENGINE_LIB:FILEPATH=${HTS_ENGINE_DIR}/lib/libHTSEngine.a
  -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
  -DCMAKE_C_COMPILER:FILEPATH=aarch64-linux-gnu-gcc
  -DCMAKE_CXX_COMPILER:FILEPATH=aarch64-linux-gnu-g++
  -DCMAKE_AR:FILEPATH=aarch64-linux-gnu-ar
  -DCMAKE_RANLIB:FILEPATH=aarch64-linux-gnu-ranlib
)
```

### OpenJTalk_CMakeLists.txt Updates

1. **Linux-specific library linking**:
```cmake
# Platform-specific settings
if(UNIX AND NOT APPLE)
  # Linux-specific settings
  find_package(Threads REQUIRED)
  target_link_libraries(mecab PUBLIC Threads::Threads)
  target_link_libraries(openjtalk PUBLIC Threads::Threads)
  
  # Add math library
  target_link_libraries(openjtalk PUBLIC m)
endif()
```

## Build Instructions

### Native ARM64 Build

On ARM64 Linux systems (e.g., Raspberry Pi, AWS Graviton):

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

### Cross-Compilation using Docker

For cross-compiling on x86_64 host:

```bash
docker buildx build --platform linux/arm64 -t piper-arm64 .
```

### Manual Cross-Compilation

```bash
cmake -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE=cmake/linux-aarch64.cmake
cmake --build build
```

## Testing

1. **Dictionary Loading**: Verify OpenJTalk dictionary loads correctly
2. **Japanese Text Processing**: Test with various Japanese inputs
3. **Performance**: Compare with x86_64 build
4. **Memory Usage**: Monitor on constrained devices

Example test:
```bash
echo "こんにちは世界" | ./build/piper \
  --model ja_JP-test-medium.onnx \
  --output_file test.wav
```

## Compatibility

- Maintains backward compatibility with existing builds
- No impact on other platforms
- Works with existing Docker infrastructure
- Compatible with all OpenJTalk features

## Future Improvements

1. **Native autotools support**: Eventually fix autotools cross-compilation
2. **Binary packages**: Provide pre-built ARM64 packages
3. **CI/CD integration**: Add ARM64 Linux builds to GitHub Actions
4. **Performance optimization**: ARM64-specific optimizations (NEON)

## References

- Issue #42: https://github.com/ayutaz/piper-plus/issues/42
- OpenJTalk: https://open-jtalk.sourceforge.net/
- CMake Cross-compilation: https://cmake.org/cmake/help/latest/manual/cmake-toolchains.7.html