// Path sanitizer for CLI binaries — wraps std::filesystem::weakly_canonical
// with a `..` denylist barrier to break CodeQL's cpp/path-injection
// taint flow on argv-derived paths.
//
// The piper-plus CLI's security boundary is the user invoking the binary
// (the user owns argv); however CodeQL still flags argv → ifstream chains
// as path-injection because the same patterns appear in privileged daemons.
// Routing all argv-derived paths through this helper, then propagating the
// `std::nullopt` case as an early reject (rather than falling back to the
// raw input), gives CodeQL's data-flow library a visible sanitizer barrier.

#pragma once
#include <filesystem>
#include <optional>
#include <string>

namespace piper_plus {

// Canonicalizes a user-supplied filesystem path with a CodeQL-recognizable
// taint barrier. Returns std::nullopt if the path is empty, contains a
// NUL byte, contains a `..` component, or fails canonicalization.
//
// Callers MUST treat std::nullopt as a hard reject — falling back to the
// original (un-sanitized) path defeats the barrier and re-introduces the
// taint flow. The `..` denylist is a small breaking change for CLI users
// passing relative paths with parent-directory traversal (`--model
// ../models/x.onnx`); use absolute paths or cwd-relative paths instead.
inline std::optional<std::filesystem::path>
sanitizeCliPath(const std::filesystem::path& userPath) {
    if (userPath.empty()) return std::nullopt;
    const std::string s = userPath.string();
    if (s.find('\0') != std::string::npos) return std::nullopt;
    // Reject path traversal — CodeQL's data-flow library recognizes a
    // denylist on `..` as a sanitizer barrier for cpp/path-injection.
    if (s.find("..") != std::string::npos) return std::nullopt;
    std::error_code ec;
    auto canon = std::filesystem::weakly_canonical(userPath, ec);
    if (ec) return std::nullopt;
    return canon;
}

}  // namespace piper_plus
