# ARM64 Optimization for Piper TTS

## Overview

This document describes the ARM64-specific optimizations implemented for Piper TTS to improve performance and reduce binary size on ARM64 platforms, particularly for embedded devices like Raspberry Pi.

> **Note (current build status):** The NEON SIMD optimizations described below are currently **disabled** in the build. The `USE_ARM64_NEON` flag is commented out in `CMakeLists.txt`, so the NEON-optimized code paths are not compiled. The current ARM64 build uses only `-march=armv8-a -mtune=generic`. The compiler flags and NEON intrinsics described in this document are **aspirational/reference** material for when these optimizations are re-enabled.

## Optimization Goals (Issue #33)

1. **Reduce ARM64 build size by 20%**
2. **Improve speech synthesis processing speed**
3. **Reduce memory consumption**
4. **Verify functionality on Raspberry Pi**

## Implemented Optimizations

### 1. Compiler Optimization Flags

Added ARM64-specific compiler flags in `CMakeLists.txt`:

- `-march=armv8-a+simd`: Enable ARM64 SIMD instructions
- `-mtune=cortex-a72`: Optimize for Cortex-A72 (Raspberry Pi 4/5)
- `-O2`: Optimize for speed without excessive code size increase
- `-fomit-frame-pointer`: Free up a register for better optimization
- `-ftree-vectorize`: Enable auto-vectorization
- `-ffast-math`: Enable fast floating-point math

### 2. NEON SIMD Optimizations

Implemented NEON-optimized audio processing functions:

#### `findMaxAudioValueNEON()`
- Processes 4 float values simultaneously
- Uses `vabsq_f32` for vectorized absolute value
- Uses `vmaxq_f32` for vectorized maximum comparison
- Expected speedup: 3-4x

#### `scaleAndConvertAudioNEON()`
- Processes 8 audio samples at once
- Uses `vmulq_f32` for vectorized multiplication
- Uses `vminq_f32` and `vmaxq_f32` for clamping
- Uses `vcvtq_s32_f32` and `vqmovn_s32` for efficient float-to-int16 conversion
- Expected speedup: 4-6x

### 3. Link Time Optimization (LTO)

Enabled LTO for release builds to:
- Inline functions across compilation units
- Remove dead code
- Optimize whole program

### 4. Binary Stripping

Added automatic stripping of debug symbols:
- Reduces binary size significantly
- Uses `aarch64-linux-gnu-strip` for cross-compiled binaries

### 5. HTSEngine Optimization

Enabled `HTS_EMBEDDED` mode to:
- Reduce memory footprint
- Optimize for embedded systems

## Build Configuration

### Native ARM64 Build

```bash
cmake -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SYSTEM_PROCESSOR=aarch64
```

### Cross-Compilation

The Docker build automatically detects ARM64 target and applies optimizations:

```bash
docker buildx build --platform linux/arm64 -t piper-arm64 .
```

## Performance Results

Expected improvements on ARM64 devices:

- **Audio normalization**: 3-4x faster
- **Audio conversion**: 4-6x faster
- **Overall synthesis**: 15-25% faster
- **Binary size**: ~20% smaller
- **Memory usage**: Reduced due to optimized data structures

## Testing on Raspberry Pi

To test on Raspberry Pi 4/5:

1. Build the optimized binary
2. Copy to Raspberry Pi
3. Run performance tests:

```bash
# Basic functionality test
./piper --help

# Performance test with Japanese text
echo "こんにちは世界" | ./piper \
  --model ja_JP-test-medium.onnx \
  --output_file test.wav

# Measure performance
time echo "長い日本語のテキスト..." | ./piper \
  --model ja_JP-test-medium.onnx \
  --output_file /dev/null
```

## Compatibility

The optimizations are:
- Backward compatible (fallback to scalar code on non-ARM64)
- Conditional compilation using `USE_ARM64_NEON` macro
- No impact on other architectures

## Future Improvements

1. **OpenJTalk ARM64 support**: Currently limited on Linux ARM64
2. **Additional NEON optimizations**: Text processing, phoneme mapping
3. **ARM SVE support**: For newer ARM processors
4. **Profile-guided optimization**: Based on real-world usage patterns

## References

- [ARM NEON Intrinsics Reference](https://developer.arm.com/architectures/instruction-sets/intrinsics/)
- [Optimizing C++ for ARM64](https://developer.arm.com/documentation/)
- [Raspberry Pi Documentation](https://www.raspberrypi.com/documentation/)