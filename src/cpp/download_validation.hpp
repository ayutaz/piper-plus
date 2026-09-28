// Shell-injection and path-traversal validators for the model downloader,
// shared by src/cpp/model_manager.cpp and
// src/cpp/tests/test_download_utils.cpp.
//
// These were `static` in model_manager.cpp, which gives them internal linkage:
// no test could call them, ever. test_download_utils.cpp therefore carried
// hand-written copies and said so --
//
//     // --- Security validation helpers (inline replicas of static functions
//     //     in model_manager.cpp) ---
//
// -- and its 20+ assertions, including every `EXPECT_FALSE(isSafeForShell(
// "...;rm -rf /"))`, ran against those copies rather than against the code
// that guards `downloadFile`. That function passes its argument to `system()`,
// so this allowlist is the only thing between a hostile voice catalog entry
// and a shell.
//
// The copies had already drifted: production gained `%` (for URL-encoded
// characters) and the replica never followed, so the two disagreed on which
// characters are accepted. No assertion contradicted it yet, which is the
// point -- loosening the production allowlist further would also have gone
// unnoticed.
//
// Header-only and dependency-free (<cctype> + <string>) so the test links
// nothing but gtest.

#ifndef PIPER_PLUS_DOWNLOAD_VALIDATION_HPP
#define PIPER_PLUS_DOWNLOAD_VALIDATION_HPP

#include <cctype>
#include <string>

namespace piper {

// Shell-safe for URLs: allowlist approach.
// Only allow alphanumerics, hyphens, underscores, dots, forward slashes,
// colons, and percent (for URL-encoded characters).
// Explicitly rejects shell metacharacters: ' $ ` ( ) ; | & < > ~ # ! { } etc.
//
// NOTE: backslash is NOT allowed here even though isSafeForShellPath allows
// it. A URL has no use for one, and on a POSIX shell it is the escape
// character.
inline bool isSafeForShell(const std::string &s) {
  for (char c : s) {
    if (!std::isalnum(static_cast<unsigned char>(c)) && c != '-' && c != '_' &&
        c != '.' && c != '/' && c != ':' && c != '%') {
      return false;
    }
  }
  return !s.empty();
}

// Shell-safe for file paths: allows backslashes for Windows path separators.
// Explicitly rejects shell metacharacters: ' $ ` ( ) ; | & < > ~ # ! { } etc.
//
// NOTE: percent is NOT allowed here even though isSafeForShell allows it.
// Percent has no place in a local path and `%VAR%` expands on cmd.exe.
inline bool isSafeForShellPath(const std::string &s) {
  for (char c : s) {
    if (!std::isalnum(static_cast<unsigned char>(c)) && c != '-' && c != '_' &&
        c != '.' && c != '/' && c != '\\' && c != ':') {
      return false;
    }
  }
  return !s.empty();
}

// Validate that a voice key contains no path traversal characters.
// Rejects "..", "/", and "\" to prevent directory escape.
inline bool isSafeVoiceKey(const std::string &key) {
  if (key.empty()) return false;
  if (key.find("..") != std::string::npos) return false;
  if (key.find('/') != std::string::npos) return false;
  if (key.find('\\') != std::string::npos) return false;
  return true;
}

// Validate that a repoId contains only safe characters (alphanumerics,
// hyphens, underscores, dots, and a single forward slash separating
// owner/repo).
inline bool isSafeRepoId(const std::string &repoId) {
  if (repoId.empty()) return false;
  int slashCount = 0;
  for (char c : repoId) {
    if (c == '/') {
      ++slashCount;
      if (slashCount > 1) return false;  // only one slash allowed
    } else if (!std::isalnum(static_cast<unsigned char>(c)) && c != '-' &&
               c != '_' && c != '.') {
      return false;
    }
  }
  // Must have exactly one slash (owner/repo format)
  return slashCount == 1;
}

}  // namespace piper

#endif  // PIPER_PLUS_DOWNLOAD_VALIDATION_HPP
