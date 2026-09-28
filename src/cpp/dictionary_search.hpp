// Dictionary file search, shared by src/cpp/piper.cpp and
// src/cpp/tests/test_multilingual_g2p.cpp.
//
// This was `static` inside piper.cpp, so no test could reach it. The test file
// carried a hand-written copy and said so:
//
//     // replicate the same 3-tier search algorithm here so the logic is
//     // ...
//     // Replicates piper.cpp findDictionaryFile() search logic:
//
// A replica cannot catch a change to the search ORDER, which is the only thing
// this function really decides: whether a dictionary shipped next to the model
// wins over one installed system-wide, and whether the environment variable
// can override either. Getting that order wrong silently degrades G2P quality
// rather than failing, so it needs a test against the real code (issue #703).
//
// `getExeDir` is injected rather than called directly: the production version
// reads the running executable's path, which a unit test cannot control. The
// test passes a lambda returning a temp directory.
//
// Depends only on <filesystem> / <functional> / <string> and a logging
// callback, so the test links neither onnxruntime nor spdlog.

#ifndef PIPER_PLUS_DICTIONARY_SEARCH_HPP
#define PIPER_PLUS_DICTIONARY_SEARCH_HPP

#include <cstdlib>
#include <filesystem>
#include <functional>
#include <string>

namespace piper {

// Where a dictionary was found. Returned alongside the path so a caller (or a
// test) can assert WHICH tier won, not merely that some file was located.
enum class DictionaryTier {
  NotFound,
  ModelDir,      // 1. next to the model
  ExeRelative,   // 2. <exe_dir>/../share/piper-plus/dicts
  EnvironmentVar // 3. PIPER_PLUS_DICTIONARIES_PATH
};

struct DictionarySearchResult {
  std::string path;
  DictionaryTier tier = DictionaryTier::NotFound;
};

// Three-tier search, in priority order. The first existing candidate wins.
//
// `exeDirProvider` returns the directory of the running executable, or an
// empty path when it cannot be determined (tier 2 is then skipped).
// `envValue` is the value of PIPER_PLUS_DICTIONARIES_PATH, or nullptr.
//
// Tier 2 is canonicalised (`weakly_canonical`) because it is built from a
// `..` component; tiers 1 and 3 are returned as composed. That asymmetry is
// deliberate and pinned by a test -- it is what the production code did, and
// changing it would change the strings callers hand to sanitizeCliPath.
inline DictionarySearchResult findDictionaryFileIn(
    const std::string &filename, const std::string &modelDir,
    const std::function<std::filesystem::path()> &exeDirProvider,
    const char *envValue) {
  namespace fs = std::filesystem;

  // 1. Model directory
  fs::path p1 = fs::path(modelDir) / filename;
  if (fs::exists(p1)) {
    return {p1.string(), DictionaryTier::ModelDir};
  }

  // 2. Exe-relative path: <exe_dir>/../share/piper-plus/dicts/<filename>
  const fs::path exeDir = exeDirProvider ? exeDirProvider() : fs::path();
  if (!exeDir.empty()) {
    fs::path p2 = exeDir / ".." / "share" / "piper-plus" / "dicts" / filename;
    if (fs::exists(p2)) {
      std::error_code ec;
      auto resolved = fs::weakly_canonical(p2, ec);
      return {ec ? p2.string() : resolved.string(),
              DictionaryTier::ExeRelative};
    }
  }

  // 3. Environment variable PIPER_PLUS_DICTIONARIES_PATH
  if (envValue != nullptr && envValue[0] != '\0') {
    fs::path p3 = fs::path(envValue) / filename;
    if (fs::exists(p3)) {
      return {p3.string(), DictionaryTier::EnvironmentVar};
    }
  }

  return {};
}

}  // namespace piper

#endif  // PIPER_PLUS_DICTIONARY_SEARCH_HPP
