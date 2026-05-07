// ZH-EN code-switching: loanword data + embedded-English phonemization
// (Issue #384, design §2.5 / §4.1 P1-P6 / §8.1 / §8.5)

#ifndef CHINESE_LOANWORD_HPP
#define CHINESE_LOANWORD_HPP

#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include "phoneme_parser.hpp"  // Phoneme = char32_t

namespace piper {

// =========================================================================
// LoanwordData — schema mirror of zh_en_loanword.json
// =========================================================================

/// Forward-compatible loader (YELLOW-5): unknown top-level fields are
/// silently ignored by the parser, so a future schema_version: 2 with new
/// fields does not break this loader.
struct LoanwordData {
    int version = 1;
    std::unordered_map<std::string, std::vector<std::string>> acronyms;
    std::unordered_map<std::string, std::vector<std::string>> loanwords;
    std::unordered_map<std::string, std::vector<std::string>> letter_fallback;
};

/// Thrown by the JSON parser on schema violations.
class LoanwordSchemaError : public std::runtime_error {
public:
    explicit LoanwordSchemaError(const std::string& msg) : std::runtime_error(msg) {}
};

// =========================================================================
// Loader API
// =========================================================================

/// Return the bundled default loanword data.
///
/// On Apple-embedded / Android targets the JSON is statically embedded
/// (compile-time, via CMake `file(READ HEX)`). On desktop (Linux / macOS /
/// Windows) it is loaded from `<dict_dir>/zh_en_loanword.json` next to the
/// executable. Either way the parsed data is cached behind `std::call_once`
/// and shared as a `std::shared_ptr<const LoanwordData>` (immutable).
///
/// Returns `nullptr` on first-time load failure (subsequent calls keep
/// returning `nullptr`); inspect `getDefaultLoanwordError()` for the reason.
std::shared_ptr<const LoanwordData> getDefaultLoanwordData();

/// Last error string from a failed `getDefaultLoanwordData()` initialisation,
/// or empty string if the data is loaded successfully.
const std::string& getDefaultLoanwordError();

/// Parse JSON text into a LoanwordData (used internally by
/// `getDefaultLoanwordData` and exposed for overrides + tests).
///
/// Error format mirrors Python `_load_loanword_data`:
///   `<label>: '<section>.<key>' must be list[str], got <value>`
LoanwordData parseLoanwordJson(const std::string& label, const std::string& json);

/// Load + parse from a filesystem path. Throws on I/O or schema errors.
std::shared_ptr<const LoanwordData> loadLoanwordDataFromPath(const std::string& path);

// =========================================================================
// Embedded-English phonemization (TICKET-05 P2)
// =========================================================================

/// Phonemize English text embedded in Chinese context as Mandarin pinyin.
///
/// Lookup priority (Python-equivalent):
///   1. case-sensitive `loanwords` (e.g. "Python", "ChatGPT")
///   2. uppercase `acronyms`        (e.g. "GPS", "USB")
///   3. per-letter `letter_fallback` on uppercased text (digits dropped)
///
/// Output is a flat `std::vector<Phoneme>` matching Rust / Go / C# (see
/// design §8.5 for the cross-runtime `Vec<String>` / `[]string` / flat list
/// equivalence). The `piper.cpp` dispatch wraps this in
/// `vector<vector<Phoneme>>` for the existing audio pipeline ABI.
void phonemizeEmbeddedEnglish(const std::string& text,
                              std::vector<Phoneme>& out,
                              const LoanwordData& data);

}  // namespace piper

#endif  // CHINESE_LOANWORD_HPP
