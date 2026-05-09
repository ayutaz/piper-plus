#ifndef PORTUGUESE_PHONEMIZE_HPP
#define PORTUGUESE_PHONEMIZE_HPP

#include <string>
#include <vector>

#include "phoneme_parser.hpp" // Phoneme = char32_t

namespace piper {

// Phonemize Brazilian Portuguese text using rule-based G2P.
// Output is a vector of sentences, each sentence a vector of Phoneme (char32_t)
// codepoints.  Multi-codepoint IPA symbols are mapped to PUA codepoints so that
// every phoneme is a single char32_t.
void phonemize_portuguese(const std::string &text,
                          std::vector<std::vector<Phoneme>> &phonemes);

// Phonemize European Portuguese (pt-PT) text. Mirror of Python
// `_apply_eu_postprocessing`. Reuses `phonemize_portuguese` and applies the
// 5 BR↔EU contrast rewrites in-place. See
// `docs/spec/pt-dialect-contract.toml` (spec_version 2).
void phonemize_european_portuguese(const std::string &text,
                                   std::vector<std::vector<Phoneme>> &phonemes);

} // namespace piper

#endif // PORTUGUESE_PHONEMIZE_HPP
