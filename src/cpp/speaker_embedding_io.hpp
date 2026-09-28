// Speaker-embedding file loading, shared by src/cpp/main.cpp and
// src/cpp/tests/test_speaker_embedding.cpp.
//
// Both loaders lived in main.cpp: `loadSpeakerEmbeddingBin` as `static`
// (internal linkage, unreachable from anywhere) and `loadSpeakerEmbedding`
// in a translation unit that defines `main()`, so no test could link either.
// test_speaker_embedding.cpp therefore carried a hand-written copy and said
// so:
//
//     // Standalone reimplementation of loadSpeakerEmbedding() from main.cpp.
//     // We replicate the logic here rather than including main.cpp ...
//     // If the production implementation ever changes, this mirror must be
//     // updated.
//
// That last line is the problem: nothing enforces it, and a mirror cannot
// catch drift in the thing it mirrors (issue #703). What these functions
// decide is how many floats a file yields and what happens when that is not
// 192 -- get it wrong and the voice silently changes rather than failing, so
// the padding/truncation rule is exactly the part that needs a test against
// the real code.
//
// Warnings go through a callback rather than spdlog so this header stays
// dependency-free; main.cpp passes a lambda that calls spdlog::warn.
//
// Depends only on the standard library, so the test links neither onnxruntime
// nor spdlog.

#ifndef PIPER_PLUS_SPEAKER_EMBEDDING_IO_HPP
#define PIPER_PLUS_SPEAKER_EMBEDDING_IO_HPP

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <ios>
#include <stdexcept>
#include <string>
#include <vector>

namespace piper {

// The dimension every shipped speaker encoder produces (CAM++ / ECAPA-TDNN).
inline constexpr std::int64_t kSpeakerEmbeddingDim = 192;

// Load a speaker embedding from a raw float32 little-endian binary file.
//
// Format matches the Rust CLI's `--speaker-embedding`
// (src/rust/piper-cli/src/main.rs:load_speaker_embedding), so a file written
// by one runtime is readable by the other. Unlike the .npy-aware loader below
// this one does NOT pad or truncate: the caller compares the length against
// the model's own speaker_embedding dimension and fails on a mismatch, which
// is the behaviour a cross-runtime format needs.
inline std::vector<float> loadSpeakerEmbeddingBinIn(
    const std::filesystem::path &path) {
  std::ifstream f(path, std::ios::binary | std::ios::ate);
  if (!f.good()) {
    throw std::runtime_error("Failed to open speaker embedding file: " +
                             path.string());
  }
  const auto bytes = static_cast<std::streamsize>(f.tellg());
  if (bytes < 0) {
    throw std::runtime_error("Failed to stat speaker embedding file: " +
                             path.string());
  }
  if (bytes % 4 != 0) {
    throw std::runtime_error("Speaker embedding file size (" +
                             std::to_string(bytes) +
                             " bytes) is not a multiple of 4 (float32)");
  }
  f.seekg(0, std::ios::beg);
  std::vector<float> floats(static_cast<std::size_t>(bytes) / sizeof(float));
  if (!floats.empty()) {
    f.read(reinterpret_cast<char *>(floats.data()), bytes);
    if (!f) {
      throw std::runtime_error("Failed to read speaker embedding file: " +
                               path.string());
    }
  }
  return floats;
}

// Load a speaker embedding from a raw binary file (192 float32 = 768 bytes)
// or a NumPy .npy file (header + 192 float32), padding or truncating the
// result to kSpeakerEmbeddingDim.
//
// `onDimensionAdjusted(actual, expected)` is invoked, when set, whenever that
// resize happens. Padding with zeros produces a valid-looking but wrong voice
// rather than an error, so the notification is the only signal the caller
// gets.
inline std::vector<float> loadSpeakerEmbeddingIn(
    const std::filesystem::path &path,
    const std::function<void(std::size_t, std::int64_t)>
        &onDimensionAdjusted = nullptr) {
  std::ifstream file(path, std::ios::binary | std::ios::ate);
  if (!file.good()) {
    throw std::runtime_error("Cannot open speaker embedding file: " +
                             path.string());
  }

  const auto fileSize = file.tellg();
  file.seekg(0, std::ios::beg);

  // NumPy .npy starts with the magic "\x93NUMPY".
  char magic[6] = {};
  file.read(magic, 6);
  file.seekg(0, std::ios::beg);

  std::vector<float> embedding;

  if (magic[0] == '\x93' && magic[1] == 'N' && magic[2] == 'U' &&
      magic[3] == 'M' && magic[4] == 'P' && magic[5] == 'Y') {
    // Layout: magic(6) + major(1) + minor(1) + headerLen(2 or 4, LE) +
    //         header + data
    file.seekg(6, std::ios::beg);
    std::uint8_t majorVersion = 0;
    file.read(reinterpret_cast<char *>(&majorVersion), 1);
    file.seekg(8, std::ios::beg);
    std::size_t dataOffset = 0;
    if (majorVersion >= 2) {
      // v2.0+: headerLen is uint32 at offset 8, data starts at 12 + headerLen.
      std::uint32_t headerLen = 0;
      file.read(reinterpret_cast<char *>(&headerLen), sizeof(headerLen));
      dataOffset = 12 + headerLen;
    } else {
      // v1.0: headerLen is uint16 at offset 8, data starts at 10 + headerLen.
      std::uint16_t headerLen = 0;
      file.read(reinterpret_cast<char *>(&headerLen), sizeof(headerLen));
      dataOffset = 10 + headerLen;
    }
    file.seekg(static_cast<std::streamoff>(dataOffset), std::ios::beg);

    const auto dataStart = file.tellg();
    const auto dataBytes = fileSize - dataStart;
    const auto numFloats = static_cast<std::int64_t>(dataBytes) / sizeof(float);

    embedding.resize(numFloats);
    file.read(reinterpret_cast<char *>(embedding.data()),
              static_cast<std::streamsize>(numFloats * sizeof(float)));
  } else {
    const auto numFloats = static_cast<std::int64_t>(fileSize) / sizeof(float);
    embedding.resize(numFloats);
    file.read(reinterpret_cast<char *>(embedding.data()),
              static_cast<std::streamsize>(numFloats * sizeof(float)));
  }

  if (static_cast<std::int64_t>(embedding.size()) != kSpeakerEmbeddingDim) {
    if (onDimensionAdjusted) {
      onDimensionAdjusted(embedding.size(), kSpeakerEmbeddingDim);
    }
    embedding.resize(kSpeakerEmbeddingDim, 0.0f);
  }

  return embedding;
}

}  // namespace piper

#endif  // PIPER_PLUS_SPEAKER_EMBEDDING_IO_HPP
