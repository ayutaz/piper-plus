#ifndef PIPER_SSML_HPP
#define PIPER_SSML_HPP

// Basic SSML (Speech Synthesis Markup Language) subset parser.
//
// Supports the same subset of W3C SSML as the canonical Rust / Python /
// C# / Go implementations:
//   - <speak> root element
//   - <break time="500ms"/> or <break time="1s"/>
//   - <break strength="medium"/> (W3C named strength)
//   - <prosody rate="slow"|"x-slow"|...|"120%"|"1.5">..</prosody>
//
// Unknown tags degrade gracefully (their text content is preserved).
// XML parse errors fall back to a stripped-tags plain-text segment.
//
// Output shape mirrors the other runtimes: a vector of SsmlSegment values
// each carrying (text, break_ms, rate). Callers iterate over segments,
// phonemize the non-empty text, apply length_scale = rate when synthesizing
// that segment, and insert break_ms of silence after.
//
// Canonical sources / cross-runtime parity:
//   - Rust:   src/rust/piper-plus-g2p/src/ssml.rs
//   - Python: src/python/g2p/piper_plus_g2p/ssml.py
//   - C#:     src/csharp/PiperPlus.Core/Ssml/SsmlParser.cs
//   - Go:     src/go/piperplus/ssml/parser.go
//   - Spec:   docs/spec/ssml-contract.toml
//             tests/fixtures/ssml/contract.json

#include <cstdint>
#include <string>
#include <vector>

namespace piper {
namespace ssml {

// Maximum break duration in milliseconds. Matches the Rust canonical
// implementation's MAX_BREAK_MS. SSML W3C spec does not constrain this,
// but TTS callers rarely benefit from > 1 min silence and unbounded
// values risk runaway buffer allocation downstream.
constexpr uint32_t kMaxBreakMs = 60000;

// A parsed SSML fragment.
//
// `text`     — text to phonemize; empty for silence-only segments.
// `breakMs`  — silence in milliseconds to insert after this segment.
// `rate`     — length_scale multiplier ( > 1.0 = slower, < 1.0 = faster ).
struct SsmlSegment {
  std::string text;
  uint32_t breakMs = 0;
  float rate = 1.0f;
};

// Returns true if `text` looks like an SSML document.
//
// Detection mirrors the canonical regex `^\s*<speak[\s>]`:
//   - skip leading whitespace
//   - require literal `<speak` followed by whitespace or `>`
//
// Case-sensitive: `<SPEAK>` is NOT treated as SSML (parity with all 4
// canonical runtimes — the regex flag table in ssml-contract.toml pins
// `case_sensitive = true`).
bool isSsml(const std::string &text);

// Parse an SSML document into an ordered list of segments.
//
// Non-SSML input is returned as a single segment containing the raw text.
// XML parse errors fall back to a single segment containing the input with
// all tags stripped (or the original input if stripping yields empty).
// Empty `<speak></speak>` returns a single empty segment so callers always
// receive a non-empty vector.
std::vector<SsmlSegment> parse(const std::string &ssmlText);

// ---------------------------------------------------------------------------
// Lower-level helpers exposed for testing & contract-fixture parity. These
// match the algorithms in the canonical runtimes byte-for-byte.
// ---------------------------------------------------------------------------

// Convert a `<break strength="...">` attribute value to milliseconds.
// Unknown values fall back to `medium` (400 ms). Case-insensitive.
uint32_t breakStrengthMs(const std::string &strength);

// Convert a `<break time="...">` attribute value to milliseconds.
//   - `"500ms"` -> 500
//   - `"1.5s"`  -> 1500
//   - `"500"`   -> 500 (bare number assumes ms)
//   - negative / NaN / inf / unparseable -> 0
//   - values > kMaxBreakMs are saturated to kMaxBreakMs
uint32_t parseBreakTime(const std::string &timeStr);

// Convert a `<prosody rate="...">` attribute value to a length_scale
// multiplier.
//   - Named (`"slow"`, `"x-fast"`, …)
//   - Percentage (`"120%"` -> 100 / 120)
//   - Bare float (`"1.3"` -> 1.3)
//   - Invalid / non-positive -> 1.0 (default)
float parseRate(const std::string &rateStr);

} // namespace ssml
} // namespace piper

#endif // PIPER_SSML_HPP
