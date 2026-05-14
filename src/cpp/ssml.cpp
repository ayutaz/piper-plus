// Basic SSML subset parser (W3C subset).
//
// Implementation notes:
//   * Standard library only — no pugixml / tinyxml dependency. The canonical
//     runtimes parse with their language's XML library (quick-xml /
//     ElementTree / System.Xml / encoding/xml). Pulling in an XML library
//     just for `<speak>` / `<break>` / `<prosody>` would be overkill, so we
//     hand-roll a tiny tag scanner. The grammar we accept is a strict
//     subset: tags, self-closing tags, attributes (`name="value"` or
//     `name='value'`), text content, basic XML entities. CDATA, comments,
//     processing instructions, and DOCTYPE are skipped (no DOCTYPE support
//     also means no entity-expansion DoS surface — billion-laughs is
//     impossible by construction).
//   * Tag-matching errors (unclosed / mismatched tags) trigger the same
//     graceful fallback as the canonical runtimes: strip all `<…>` and
//     return the remaining text as a single segment.
//   * The output shape (vector<SsmlSegment>) matches the contract — the
//     ssml-contract.toml fixture is the source of truth, and the
//     accompanying test_ssml.cpp asserts the constants here match.

#include "ssml.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

namespace piper {
namespace ssml {

namespace {

// ---------------------------------------------------------------------------
// Case / whitespace helpers
// ---------------------------------------------------------------------------

inline char asciiLower(char c) {
  if (c >= 'A' && c <= 'Z') {
    return static_cast<char>(c - 'A' + 'a');
  }
  return c;
}

std::string toLowerAscii(const std::string &s) {
  std::string out;
  out.reserve(s.size());
  for (char c : s) {
    out.push_back(asciiLower(c));
  }
  return out;
}

inline bool isXmlSpace(char c) {
  return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

std::string trim(const std::string &s) {
  size_t a = 0;
  while (a < s.size() && isXmlSpace(s[a])) {
    ++a;
  }
  size_t b = s.size();
  while (b > a && isXmlSpace(s[b - 1])) {
    --b;
  }
  return s.substr(a, b - a);
}

// Strip a namespace prefix (`xmlns:` style) from a tag name. We only support
// the local-name match contract (`strip_xml_namespace_for_tag_match = true`).
// In a real XML parser the namespace is resolved via xmlns attributes; here
// we just drop everything up to the last ':' since SSML never uses prefixed
// element names in practice and Python's ElementTree replaces the entire
// `{uri}local` Clark notation with `local` via _local_tag().
std::string localName(const std::string &raw) {
  // Clark notation: `{http://…}speak` -> `speak`
  auto rbrace = raw.find('}');
  if (rbrace != std::string::npos) {
    return raw.substr(rbrace + 1);
  }
  // Prefix notation: `pfx:speak` -> `speak`
  auto colon = raw.find(':');
  if (colon != std::string::npos) {
    return raw.substr(colon + 1);
  }
  return raw;
}

// ---------------------------------------------------------------------------
// XML entity decode (subset used by W3C SSML examples)
// ---------------------------------------------------------------------------

std::string decodeEntities(const std::string &s) {
  std::string out;
  out.reserve(s.size());
  size_t i = 0;
  while (i < s.size()) {
    if (s[i] == '&') {
      // Find terminating ';'
      size_t semi = s.find(';', i + 1);
      if (semi != std::string::npos && semi - i <= 8) {
        std::string ent = s.substr(i + 1, semi - i - 1);
        if (ent == "amp") {
          out.push_back('&');
        } else if (ent == "lt") {
          out.push_back('<');
        } else if (ent == "gt") {
          out.push_back('>');
        } else if (ent == "apos") {
          out.push_back('\'');
        } else if (ent == "quot") {
          out.push_back('"');
        } else if (!ent.empty() && ent[0] == '#') {
          // Numeric entity: &#NNN; or &#xHHHH;
          unsigned long codepoint = 0;
          try {
            if (ent.size() > 1 && (ent[1] == 'x' || ent[1] == 'X')) {
              codepoint = std::stoul(ent.substr(2), nullptr, 16);
            } else {
              codepoint = std::stoul(ent.substr(1), nullptr, 10);
            }
          } catch (...) {
            // Malformed numeric — keep raw
            out.append(s, i, semi - i + 1);
            i = semi + 1;
            continue;
          }
          // UTF-8 encode
          if (codepoint < 0x80) {
            out.push_back(static_cast<char>(codepoint));
          } else if (codepoint < 0x800) {
            out.push_back(static_cast<char>(0xC0 | (codepoint >> 6)));
            out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
          } else if (codepoint < 0x10000) {
            out.push_back(static_cast<char>(0xE0 | (codepoint >> 12)));
            out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
          } else if (codepoint < 0x110000) {
            out.push_back(static_cast<char>(0xF0 | (codepoint >> 18)));
            out.push_back(static_cast<char>(0x80 | ((codepoint >> 12) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
          }
        } else {
          // Unknown entity — keep raw
          out.append(s, i, semi - i + 1);
        }
        i = semi + 1;
        continue;
      }
    }
    out.push_back(s[i]);
    ++i;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Detection regex literal: `^\s*<speak[\s>]` (case-sensitive, matches at start)
// We avoid pulling in <regex> for a six-character literal.
// ---------------------------------------------------------------------------

bool detectionMatch(const std::string &text) {
  size_t i = 0;
  while (i < text.size() && isXmlSpace(text[i])) {
    ++i;
  }
  static const char kLit[] = "<speak";
  static constexpr size_t kLitLen = sizeof(kLit) - 1;
  if (i + kLitLen >= text.size()) {
    // Need at least one char after "<speak" (either whitespace or '>')
    return false;
  }
  if (std::memcmp(text.data() + i, kLit, kLitLen) != 0) {
    return false;
  }
  char nxt = text[i + kLitLen];
  return isXmlSpace(nxt) || nxt == '>';
}

// ---------------------------------------------------------------------------
// Strip all `<…>` from a string (graceful XML fallback).
// ---------------------------------------------------------------------------

std::string stripTags(const std::string &s) {
  std::string out;
  out.reserve(s.size());
  bool inTag = false;
  for (char c : s) {
    if (inTag) {
      if (c == '>') {
        inTag = false;
      }
    } else {
      if (c == '<') {
        inTag = true;
      } else {
        out.push_back(c);
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Tag attribute parsing helper.
// ---------------------------------------------------------------------------

struct Attr {
  std::string name;
  std::string value;
};

// Parse `name="value"` / `name='value'` / `name=value` pairs from a tag's
// attribute substring (the part after the tag name, before `>` or `/>`).
// Returns true on syntactic success, false on unrecoverable error.
bool parseAttrs(const std::string &chunk, std::vector<Attr> &out) {
  size_t i = 0;
  while (i < chunk.size()) {
    // skip whitespace
    while (i < chunk.size() && isXmlSpace(chunk[i])) {
      ++i;
    }
    if (i >= chunk.size()) {
      break;
    }
    // Attribute name: [^\s=>/]+
    size_t nameStart = i;
    while (i < chunk.size() && !isXmlSpace(chunk[i]) && chunk[i] != '='
           && chunk[i] != '>' && chunk[i] != '/') {
      ++i;
    }
    if (i == nameStart) {
      return false;
    }
    std::string name = chunk.substr(nameStart, i - nameStart);
    // optional whitespace + '='
    while (i < chunk.size() && isXmlSpace(chunk[i])) {
      ++i;
    }
    if (i < chunk.size() && chunk[i] == '=') {
      ++i;
      while (i < chunk.size() && isXmlSpace(chunk[i])) {
        ++i;
      }
      if (i >= chunk.size()) {
        return false;
      }
      std::string value;
      if (chunk[i] == '"' || chunk[i] == '\'') {
        char quote = chunk[i++];
        size_t vStart = i;
        while (i < chunk.size() && chunk[i] != quote) {
          ++i;
        }
        if (i >= chunk.size()) {
          return false; // unterminated quoted value
        }
        value = chunk.substr(vStart, i - vStart);
        ++i; // skip closing quote
      } else {
        size_t vStart = i;
        while (i < chunk.size() && !isXmlSpace(chunk[i]) && chunk[i] != '>'
               && chunk[i] != '/') {
          ++i;
        }
        value = chunk.substr(vStart, i - vStart);
      }
      out.push_back({std::move(name), decodeEntities(value)});
    } else {
      // Boolean attribute (rare in SSML; record with empty value)
      out.push_back({std::move(name), std::string()});
    }
  }
  return true;
}

const std::string *getAttr(const std::vector<Attr> &attrs, const std::string &name) {
  for (const auto &a : attrs) {
    if (a.name == name) {
      return &a.value;
    }
  }
  return nullptr;
}

// ---------------------------------------------------------------------------
// Streaming token walker.
//
// We push a frame for every open tag and pop on close; the top of the stack
// holds the active rate (inherited from the nearest ancestor <prosody>).
// `<break>` empty tags emit a segment in-place. Mismatched / unclosed tags
// trigger the graceful fallback (caller strips tags and returns plain).
// ---------------------------------------------------------------------------

struct Frame {
  std::string tag;
  float rate;
};

uint32_t resolveBreak(const std::vector<Attr> &attrs) {
  if (const std::string *t = getAttr(attrs, "time")) {
    return parseBreakTime(*t);
  }
  if (const std::string *st = getAttr(attrs, "strength")) {
    return breakStrengthMs(*st);
  }
  // Bare `<break/>` => medium (400 ms) per W3C spec.
  return breakStrengthMs("medium");
}

bool walkXml(const std::string &ssml, std::vector<SsmlSegment> &out) {
  std::vector<Frame> stack;
  // Sentinel root frame so currentRate() always works.
  stack.push_back({"", 1.0f});
  auto currentRate = [&]() { return stack.back().rate; };

  size_t i = 0;
  const size_t n = ssml.size();

  while (i < n) {
    if (ssml[i] != '<') {
      // Text node — accumulate until next '<' or EOF.
      size_t start = i;
      while (i < n && ssml[i] != '<') {
        ++i;
      }
      std::string raw = ssml.substr(start, i - start);
      std::string text = trim(decodeEntities(raw));
      if (!text.empty()) {
        SsmlSegment seg;
        seg.text = std::move(text);
        seg.breakMs = 0;
        seg.rate = currentRate();
        out.push_back(std::move(seg));
      }
      continue;
    }

    // ssml[i] == '<'. Classify the markup form.
    if (i + 1 >= n) {
      return false; // dangling '<'
    }

    // Skip XML declarations / comments / CDATA / DOCTYPE / PI.
    if (ssml[i + 1] == '?') {
      // Processing instruction `<?…?>`
      auto end = ssml.find("?>", i + 2);
      if (end == std::string::npos) {
        return false;
      }
      i = end + 2;
      continue;
    }
    if (ssml[i + 1] == '!') {
      // <!-- … --> or <![CDATA[ … ]]> or <!DOCTYPE …>
      if (ssml.compare(i, 4, "<!--") == 0) {
        auto end = ssml.find("-->", i + 4);
        if (end == std::string::npos) {
          return false;
        }
        i = end + 3;
        continue;
      }
      if (ssml.compare(i, 9, "<![CDATA[") == 0) {
        auto end = ssml.find("]]>", i + 9);
        if (end == std::string::npos) {
          return false;
        }
        // CDATA content treated as raw text under the current rate.
        std::string raw = ssml.substr(i + 9, end - (i + 9));
        std::string text = trim(raw);
        if (!text.empty()) {
          SsmlSegment seg;
          seg.text = std::move(text);
          seg.breakMs = 0;
          seg.rate = currentRate();
          out.push_back(std::move(seg));
        }
        i = end + 3;
        continue;
      }
      // <!DOCTYPE …> — refuse: we don't expand entities, so DOCTYPE leaks
      // would be unsafe. Skip the declaration and continue parsing without
      // entity tables (parity with quick-xml default behaviour).
      auto end = ssml.find('>', i);
      if (end == std::string::npos) {
        return false;
      }
      i = end + 1;
      continue;
    }

    // Closing tag: </name>
    if (ssml[i + 1] == '/') {
      auto end = ssml.find('>', i + 2);
      if (end == std::string::npos) {
        return false;
      }
      std::string name = localName(trim(ssml.substr(i + 2, end - (i + 2))));
      if (stack.size() <= 1) {
        return false; // close without open
      }
      if (stack.back().tag != name) {
        return false; // mismatched
      }
      stack.pop_back();
      i = end + 1;
      continue;
    }

    // Opening or self-closing tag.
    auto end = ssml.find('>', i + 1);
    if (end == std::string::npos) {
      return false;
    }
    bool selfClosing = end > 0 && ssml[end - 1] == '/';
    size_t innerEnd = selfClosing ? end - 1 : end;
    std::string inner = ssml.substr(i + 1, innerEnd - (i + 1));

    // Split into tag name + attribute chunk.
    size_t k = 0;
    while (k < inner.size() && !isXmlSpace(inner[k])) {
      ++k;
    }
    std::string rawName = inner.substr(0, k);
    std::string attrChunk = (k < inner.size()) ? inner.substr(k) : std::string();
    std::string tag = localName(rawName);
    if (tag.empty()) {
      return false;
    }
    std::vector<Attr> attrs;
    if (!parseAttrs(attrChunk, attrs)) {
      return false;
    }

    if (selfClosing) {
      if (tag == "break") {
        SsmlSegment seg;
        seg.text.clear();
        seg.breakMs = resolveBreak(attrs);
        seg.rate = currentRate();
        out.push_back(std::move(seg));
      }
      // Other self-closing tags (e.g. `<unknown/>`) are silently ignored —
      // they have no text content and no meaning in this subset.
      i = end + 1;
      continue;
    }

    // Opening tag: push a frame.
    float newRate = currentRate();
    if (tag == "prosody") {
      if (const std::string *r = getAttr(attrs, "rate")) {
        newRate = parseRate(*r);
      }
    } else if (tag == "break") {
      // Non-self-closing <break>: emit and treat as a normal frame so the
      // matching </break> just pops without effect.
      SsmlSegment seg;
      seg.text.clear();
      seg.breakMs = resolveBreak(attrs);
      seg.rate = currentRate();
      out.push_back(std::move(seg));
    }
    stack.push_back({tag, newRate});
    i = end + 1;
  }

  // All opened elements must be closed (sentinel root frame remains).
  return stack.size() == 1;
}

// Drop empty-text segments with zero break (no-ops) — matches the canonical
// merge() implementations.
std::vector<SsmlSegment> mergeSegments(std::vector<SsmlSegment> &&in) {
  std::vector<SsmlSegment> out;
  out.reserve(in.size());
  for (auto &s : in) {
    if (!trim(s.text).empty() || s.breakMs > 0) {
      out.push_back(std::move(s));
    }
  }
  return out;
}

// Sanitize a floating-point ms value into a clamped uint32_t. Mirrors the
// Rust canonical sanitize_ms(): NaN / Inf -> 0, negative -> 0, > kMaxBreakMs
// -> kMaxBreakMs.
uint32_t sanitizeMs(double v) {
  if (!std::isfinite(v)) {
    return 0;
  }
  if (v <= 0.0) {
    return 0;
  }
  if (v >= static_cast<double>(kMaxBreakMs)) {
    return kMaxBreakMs;
  }
  return static_cast<uint32_t>(v);
}

bool tryParseDouble(const std::string &s, double &out) {
  if (s.empty()) {
    return false;
  }
  try {
    size_t consumed = 0;
    double v = std::stod(s, &consumed);
    if (consumed != s.size()) {
      return false; // trailing garbage like "1e10x"
    }
    out = v;
    return true;
  } catch (...) {
    return false;
  }
}

} // namespace

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

bool isSsml(const std::string &text) { return detectionMatch(text); }

uint32_t breakStrengthMs(const std::string &strength) {
  std::string s = toLowerAscii(trim(strength));
  if (s == "none") return 0;
  if (s == "x-weak") return 100;
  if (s == "weak") return 200;
  if (s == "medium") return 400;
  if (s == "strong") return 700;
  if (s == "x-strong") return 1000;
  return 400; // unknown -> medium
}

uint32_t parseBreakTime(const std::string &timeStr) {
  std::string s = toLowerAscii(trim(timeStr));
  if (s.size() >= 2 && s.compare(s.size() - 2, 2, "ms") == 0) {
    double v;
    if (!tryParseDouble(s.substr(0, s.size() - 2), v)) {
      return 0;
    }
    return sanitizeMs(v);
  }
  if (s.size() >= 1 && s.back() == 's') {
    double v;
    if (!tryParseDouble(s.substr(0, s.size() - 1), v)) {
      return 0;
    }
    return sanitizeMs(v * 1000.0);
  }
  double v;
  if (!tryParseDouble(s, v)) {
    return 0;
  }
  return sanitizeMs(v);
}

float parseRate(const std::string &rateStr) {
  std::string s = toLowerAscii(trim(rateStr));
  if (s == "x-slow") return 1.5f;
  if (s == "slow") return 1.25f;
  if (s == "medium") return 1.0f;
  if (s == "fast") return 0.8f;
  if (s == "x-fast") return 0.6f;

  if (!s.empty() && s.back() == '%') {
    double pct;
    if (!tryParseDouble(s.substr(0, s.size() - 1), pct)) {
      return 1.0f;
    }
    if (!(pct > 0.0)) {
      return 1.0f;
    }
    return static_cast<float>(100.0 / pct);
  }
  double v;
  if (!tryParseDouble(s, v)) {
    return 1.0f;
  }
  if (!(v > 0.0)) {
    return 1.0f;
  }
  return static_cast<float>(v);
}

std::vector<SsmlSegment> parse(const std::string &ssmlText) {
  if (!isSsml(ssmlText)) {
    // Plain text — single segment, rate 1.0.
    return std::vector<SsmlSegment>{SsmlSegment{ssmlText, 0, 1.0f}};
  }

  std::vector<SsmlSegment> raw;
  if (!walkXml(ssmlText, raw)) {
    // Graceful fallback: strip tags, trim, return as one segment.
    std::string stripped = trim(stripTags(ssmlText));
    if (stripped.empty()) {
      return std::vector<SsmlSegment>{SsmlSegment{ssmlText, 0, 1.0f}};
    }
    return std::vector<SsmlSegment>{SsmlSegment{stripped, 0, 1.0f}};
  }

  auto merged = mergeSegments(std::move(raw));
  if (merged.empty()) {
    // Empty <speak></speak> — return one empty segment (parity contract).
    return std::vector<SsmlSegment>{SsmlSegment{"", 0, 1.0f}};
  }
  return merged;
}

} // namespace ssml
} // namespace piper
