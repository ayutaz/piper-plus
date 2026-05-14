// SSML parser unit tests + cross-runtime contract parity.
//
// Mirrors the test matrix in src/rust/piper-plus-g2p/src/ssml.rs and the
// canonical Python implementation. Self-contained: only links gtest + the
// json.hpp header for fixture parsing, plus ../ssml.cpp.

#include <gtest/gtest.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include "json.hpp"
#include "ssml.hpp"

namespace fs = std::filesystem;
using nlohmann::json;
using piper::ssml::isSsml;
using piper::ssml::parse;
using piper::ssml::parseBreakTime;
using piper::ssml::parseRate;
using piper::ssml::breakStrengthMs;
using piper::ssml::SsmlSegment;

namespace {

constexpr float kEps = 0.01f;

bool floatNear(float a, float b, float eps = kEps) {
  float d = a - b;
  if (d < 0) d = -d;
  return d < eps;
}

// ---------- is_ssml detection ----------

TEST(SsmlDetection, SpeakTag) {
  EXPECT_TRUE(isSsml("<speak>Hello</speak>"));
}

TEST(SsmlDetection, LeadingWhitespace) {
  EXPECT_TRUE(isSsml("  \n <speak>Hello</speak>"));
}

TEST(SsmlDetection, WithAttributes) {
  EXPECT_TRUE(isSsml("<speak version=\"1.0\" xml:lang=\"ja-JP\">Hi</speak>"));
}

TEST(SsmlDetection, PlainText) {
  EXPECT_FALSE(isSsml("Hello, world!"));
}

TEST(SsmlDetection, NonSpeakXml) {
  EXPECT_FALSE(isSsml("<root>Hello</root>"));
}

TEST(SsmlDetection, Empty) {
  EXPECT_FALSE(isSsml(""));
}

// Contract pin: detection is case-sensitive.
TEST(SsmlDetection, UppercaseNotDetected) {
  EXPECT_FALSE(isSsml("<SPEAK>Hi</SPEAK>"));
}

// Contract pin: `<speakers>` must NOT be detected as SSML (trailing `[\s>]`).
TEST(SsmlDetection, SpeakersTagNotMatched) {
  EXPECT_FALSE(isSsml("<speakers>Hi</speakers>"));
}

// ---------- Plain text fallback ----------

TEST(SsmlParse, PlainText) {
  auto segs = parse("Hello, world!");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_EQ(segs[0].text, "Hello, world!");
  EXPECT_EQ(segs[0].breakMs, 0u);
  EXPECT_TRUE(floatNear(segs[0].rate, 1.0f));
}

// ---------- Break with time ----------

TEST(SsmlParse, BreakTimeMs) {
  auto segs = parse(R"(<speak>Hello<break time="500ms"/>world</speak>)");
  ASSERT_EQ(segs.size(), 3u);
  EXPECT_EQ(segs[0].text, "Hello");
  EXPECT_EQ(segs[1].text, "");
  EXPECT_EQ(segs[1].breakMs, 500u);
  EXPECT_EQ(segs[2].text, "world");
}

TEST(SsmlParse, BreakTimeSeconds) {
  auto segs = parse(R"(<speak>Hello<break time="1.5s"/>world</speak>)");
  bool found = false;
  for (const auto &s : segs) {
    if (s.breakMs > 0) {
      EXPECT_EQ(s.breakMs, 1500u);
      found = true;
    }
  }
  EXPECT_TRUE(found);
}

TEST(SsmlParse, BreakTimeBareNumber) {
  auto segs = parse(R"(<speak>Hello<break time="750"/>world</speak>)");
  bool found = false;
  for (const auto &s : segs) {
    if (s.breakMs > 0) {
      EXPECT_EQ(s.breakMs, 750u);
      found = true;
    }
  }
  EXPECT_TRUE(found);
}

TEST(SsmlParse, BreakTimeInvalidFilteredOut) {
  // Invalid time parses to 0ms, which is filtered out by merge.
  auto segs = parse(R"(<speak>Hello<break time="abc"/>world</speak>)");
  ASSERT_EQ(segs.size(), 2u);
  EXPECT_EQ(segs[0].text, "Hello");
  EXPECT_EQ(segs[1].text, "world");
}

// ---------- Break with strength ----------

TEST(SsmlParse, BreakStrengthNoneDropped) {
  auto segs = parse(R"(<speak>Hello<break strength="none"/>world</speak>)");
  ASSERT_EQ(segs.size(), 2u);
  EXPECT_EQ(segs[0].text, "Hello");
  EXPECT_EQ(segs[1].text, "world");
}

TEST(SsmlParse, BreakStrengthMedium) {
  auto segs = parse(R"(<speak>Hello<break strength="medium"/>world</speak>)");
  bool found = false;
  for (const auto &s : segs) {
    if (s.breakMs > 0) {
      EXPECT_EQ(s.breakMs, 400u);
      found = true;
    }
  }
  EXPECT_TRUE(found);
}

TEST(SsmlParse, BreakStrengthXStrong) {
  auto segs = parse(R"(<speak>Hello<break strength="x-strong"/>world</speak>)");
  bool found = false;
  for (const auto &s : segs) {
    if (s.breakMs > 0) {
      EXPECT_EQ(s.breakMs, 1000u);
      found = true;
    }
  }
  EXPECT_TRUE(found);
}

TEST(SsmlParse, BreakBareDefaultsMedium) {
  auto segs = parse(R"(<speak>Hello<break/>world</speak>)");
  bool found = false;
  for (const auto &s : segs) {
    if (s.breakMs > 0) {
      EXPECT_EQ(s.breakMs, 400u);
      found = true;
    }
  }
  EXPECT_TRUE(found);
}

// ---------- Prosody rate (named) ----------

TEST(SsmlParse, ProsodyRateSlow) {
  auto segs = parse(R"(<speak><prosody rate="slow">Hello</prosody></speak>)");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_TRUE(floatNear(segs[0].rate, 1.25f));
}

TEST(SsmlParse, ProsodyRateFast) {
  auto segs = parse(R"(<speak><prosody rate="fast">Hello</prosody></speak>)");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_TRUE(floatNear(segs[0].rate, 0.8f));
}

TEST(SsmlParse, ProsodyRateXSlow) {
  auto segs = parse(R"(<speak><prosody rate="x-slow">Hello</prosody></speak>)");
  EXPECT_TRUE(floatNear(segs[0].rate, 1.5f));
}

TEST(SsmlParse, ProsodyRateXFast) {
  auto segs = parse(R"(<speak><prosody rate="x-fast">Hello</prosody></speak>)");
  EXPECT_TRUE(floatNear(segs[0].rate, 0.6f));
}

// ---------- Prosody rate (percentage / bare float) ----------

TEST(SsmlParse, ProsodyRatePercent120) {
  auto segs = parse(R"(<speak><prosody rate="120%">Hello</prosody></speak>)");
  EXPECT_TRUE(floatNear(segs[0].rate, 100.0f / 120.0f));
}

TEST(SsmlParse, ProsodyRatePercent50) {
  auto segs = parse(R"(<speak><prosody rate="50%">Hello</prosody></speak>)");
  EXPECT_TRUE(floatNear(segs[0].rate, 2.0f));
}

TEST(SsmlParse, ProsodyRatePercentZeroFallback) {
  auto segs = parse(R"(<speak><prosody rate="0%">Hello</prosody></speak>)");
  EXPECT_TRUE(floatNear(segs[0].rate, 1.0f));
}

TEST(SsmlParse, ProsodyRateBareFloat) {
  auto segs = parse(R"(<speak><prosody rate="1.3">Hello</prosody></speak>)");
  EXPECT_TRUE(floatNear(segs[0].rate, 1.3f));
}

// ---------- Nested elements ----------

TEST(SsmlParse, NestedProsodyAndBreak) {
  auto segs = parse(
      R"(<speak><prosody rate="slow">Hello<break time="300ms"/>world</prosody></speak>)");
  ASSERT_EQ(segs.size(), 3u);
  EXPECT_EQ(segs[0].text, "Hello");
  EXPECT_TRUE(floatNear(segs[0].rate, 1.25f));
  EXPECT_EQ(segs[1].breakMs, 300u);
  EXPECT_EQ(segs[2].text, "world");
  EXPECT_TRUE(floatNear(segs[2].rate, 1.25f));
}

TEST(SsmlParse, NestedProsodyRateOverride) {
  auto segs = parse(
      R"(<speak><prosody rate="slow"><prosody rate="fast">inner</prosody></prosody></speak>)");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_TRUE(floatNear(segs[0].rate, 0.8f));
}

TEST(SsmlParse, TextOutsideAndInsideProsody) {
  auto segs = parse(
      R"(<speak>before <prosody rate="fast">inside</prosody> after</speak>)");
  ASSERT_GE(segs.size(), 3u);
  // Locate each named segment
  const SsmlSegment *before = nullptr;
  const SsmlSegment *inside = nullptr;
  const SsmlSegment *after = nullptr;
  for (const auto &s : segs) {
    if (s.text == "before") before = &s;
    else if (s.text == "inside") inside = &s;
    else if (s.text == "after") after = &s;
  }
  ASSERT_NE(before, nullptr);
  ASSERT_NE(inside, nullptr);
  ASSERT_NE(after, nullptr);
  EXPECT_TRUE(floatNear(before->rate, 1.0f));
  EXPECT_TRUE(floatNear(inside->rate, 0.8f));
  EXPECT_TRUE(floatNear(after->rate, 1.0f));
}

// ---------- Unknown tags ----------

TEST(SsmlParse, UnknownTagExtractsText) {
  auto segs = parse(R"(<speak><emphasis>important</emphasis></speak>)");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_EQ(segs[0].text, "important");
}

// ---------- XML error fallback ----------

TEST(SsmlParse, XmlErrorFallbackMismatchedTags) {
  auto segs = parse(R"(<speak>Hello</wrong>)");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_FALSE(segs[0].text.empty());
  // Tags should be stripped
  EXPECT_EQ(segs[0].text.find('<'), std::string::npos);
}

// ---------- Edge cases ----------

TEST(SsmlParse, EmptySpeak) {
  auto segs = parse("<speak></speak>");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_TRUE(segs[0].text.empty());
}

TEST(SsmlParse, SpeakOnlyWhitespace) {
  auto segs = parse("<speak>   \n  </speak>");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_TRUE(segs[0].text.empty());
}

TEST(SsmlParse, MultipleBreaksInSequence) {
  auto segs = parse(
      R"(<speak>Hello<break time="200ms"/><break time="300ms"/>world</speak>)");
  uint32_t first = 0, second = 0;
  int idx = 0;
  for (const auto &s : segs) {
    if (s.breakMs > 0) {
      if (idx == 0) first = s.breakMs;
      else if (idx == 1) second = s.breakMs;
      ++idx;
    }
  }
  EXPECT_EQ(first, 200u);
  EXPECT_EQ(second, 300u);
}

TEST(SsmlParse, ProsodyRateUnrecognizedName) {
  auto segs = parse(
      R"(<speak><prosody rate="unknown_name">text</prosody></speak>)");
  EXPECT_TRUE(floatNear(segs[0].rate, 1.0f));
}

TEST(SsmlParse, ProsodyWithoutRateAttribute) {
  auto segs = parse(
      R"(<speak><prosody volume="loud">text</prosody></speak>)");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_TRUE(floatNear(segs[0].rate, 1.0f));
}

// ---------- Japanese (UTF-8) ----------

TEST(SsmlParse, JapaneseText) {
  auto segs = parse(R"(<speak>こんにちは<break time="500ms"/>世界</speak>)");
  ASSERT_EQ(segs.size(), 3u);
  EXPECT_EQ(segs[0].text, "こんにちは");
  EXPECT_EQ(segs[1].breakMs, 500u);
  EXPECT_EQ(segs[2].text, "世界");
}

TEST(SsmlParse, JapaneseWithProsody) {
  auto segs = parse(
      R"(<speak><prosody rate="slow">ゆっくり話します</prosody></speak>)");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_EQ(segs[0].text, "ゆっくり話します");
  EXPECT_TRUE(floatNear(segs[0].rate, 1.25f));
}

// ---------- All strengths / rates (canonical tables) ----------

TEST(SsmlParse, AllBreakStrengths) {
  struct Row { const char *name; uint32_t ms; };
  static const Row rows[] = {
      {"none", 0},   {"x-weak", 100}, {"weak", 200},
      {"medium", 400}, {"strong", 700}, {"x-strong", 1000},
  };
  for (const auto &r : rows) {
    std::ostringstream ss;
    ss << R"(<speak>a<break strength=")" << r.name << R"("/>b</speak>)";
    auto segs = parse(ss.str());
    if (r.ms == 0) {
      ASSERT_EQ(segs.size(), 2u) << "strength=" << r.name;
    } else {
      bool found = false;
      for (const auto &s : segs) {
        if (s.breakMs > 0) {
          EXPECT_EQ(s.breakMs, r.ms) << "strength=" << r.name;
          found = true;
        }
      }
      EXPECT_TRUE(found) << "strength=" << r.name;
    }
  }
}

TEST(SsmlParse, AllNamedRates) {
  struct Row { const char *name; float rate; };
  static const Row rows[] = {
      {"x-slow", 1.5f}, {"slow", 1.25f}, {"medium", 1.0f},
      {"fast", 0.8f},   {"x-fast", 0.6f},
  };
  for (const auto &r : rows) {
    std::ostringstream ss;
    ss << R"(<speak><prosody rate=")" << r.name
       << R"(">text</prosody></speak>)";
    auto segs = parse(ss.str());
    ASSERT_FALSE(segs.empty()) << "rate=" << r.name;
    EXPECT_TRUE(floatNear(segs[0].rate, r.rate))
        << "rate=" << r.name << " got=" << segs[0].rate;
  }
}

// ---------- Break time sanitization ----------

TEST(SsmlParseBreakTime, NegativeClampedToZero) {
  EXPECT_EQ(parseBreakTime("-500ms"), 0u);
  EXPECT_EQ(parseBreakTime("-1s"), 0u);
  EXPECT_EQ(parseBreakTime("-1000"), 0u);

  auto segs = parse(R"(<speak>Hello<break time="-500ms"/>world</speak>)");
  for (const auto &s : segs) {
    EXPECT_EQ(s.breakMs, 0u);
    EXPECT_LT(s.breakMs, 4000000000u); // no wrap-cast
  }
}

TEST(SsmlParseBreakTime, OverflowClampedToMax) {
  constexpr uint32_t kMax = piper::ssml::kMaxBreakMs;
  EXPECT_EQ(parseBreakTime("999999s"), kMax);
  EXPECT_EQ(parseBreakTime("99999999999ms"), kMax);
  EXPECT_EQ(parseBreakTime("60001"), kMax);
  EXPECT_EQ(parseBreakTime("60000ms"), kMax);
  EXPECT_EQ(parseBreakTime("59999ms"), 59999u);
}

TEST(SsmlParseBreakTime, ScientificNotationClamped) {
  constexpr uint32_t kMax = piper::ssml::kMaxBreakMs;
  EXPECT_EQ(parseBreakTime("1e10ms"), kMax);
  EXPECT_EQ(parseBreakTime("1e30ms"), kMax);
  EXPECT_EQ(parseBreakTime("-1e5ms"), 0u);
  EXPECT_EQ(parseBreakTime("1e2ms"), 100u);
  EXPECT_EQ(parseBreakTime("1e10x"), 0u);
}

TEST(SsmlParseBreakTime, InfNanRejected) {
  EXPECT_EQ(parseBreakTime("inf"), 0u);
  EXPECT_EQ(parseBreakTime("infms"), 0u);
  EXPECT_EQ(parseBreakTime("-infms"), 0u);
  EXPECT_EQ(parseBreakTime("nan"), 0u);
  EXPECT_EQ(parseBreakTime("NaNms"), 0u);
  EXPECT_EQ(parseBreakTime("INF"), 0u);
}

TEST(SsmlParseBreakTime, ZeroPassthrough) {
  EXPECT_EQ(parseBreakTime("0ms"), 0u);
  EXPECT_EQ(parseBreakTime("0s"), 0u);
  EXPECT_EQ(parseBreakTime("0"), 0u);
  EXPECT_EQ(parseBreakTime("0.0ms"), 0u);

  EXPECT_EQ(parseBreakTime("500x"), 0u);
  EXPECT_EQ(parseBreakTime(""), 0u);
  EXPECT_EQ(parseBreakTime("abc"), 0u);
}

// ---------- Large input + stress ----------

TEST(SsmlParse, LargeText) {
  std::string big;
  big.reserve(50000);
  big += "<speak>";
  for (int i = 0; i < 5000; ++i) {
    big += "hello ";
  }
  big += "</speak>";
  auto segs = parse(big);
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_GT(segs[0].text.size(), 10000u);
}

// ---------- XML entity decoding ----------

TEST(SsmlParse, EntityDecodingInText) {
  auto segs = parse(R"(<speak>Tom &amp; Jerry</speak>)");
  ASSERT_EQ(segs.size(), 1u);
  EXPECT_EQ(segs[0].text, "Tom & Jerry");
}

// ---------- Fixture parity (forward-compat) ----------
//
// Asserts the C++ constants match the canonical contract fixture. If
// docs/spec/ssml-contract.toml + tests/fixtures/ssml/contract.json drift
// from the C++ values, this test fails — guarding against silent breakage
// of cross-runtime byte-for-byte parity.

namespace {

fs::path resolveFixturePath() {
  // 1) PIPER_SSML_FIXTURE env override
  if (const char *env = std::getenv("PIPER_SSML_FIXTURE")) {
    return fs::path(env);
  }
  // 2) Search upwards from the current working directory for
  //    tests/fixtures/ssml/contract.json. The CTest WORKING_DIRECTORY is
  //    set to ${CMAKE_SOURCE_DIR} for most tests, but in standalone runs
  //    the test binary may live a few levels deep — walk upwards a bit.
  fs::path cwd = fs::current_path();
  for (int depth = 0; depth < 8; ++depth) {
    fs::path candidate = cwd / "tests" / "fixtures" / "ssml" / "contract.json";
    if (fs::exists(candidate)) {
      return candidate;
    }
    if (!cwd.has_parent_path()) break;
    cwd = cwd.parent_path();
  }
  return fs::path();
}

} // namespace

TEST(SsmlContract, FixtureMatchesCppConstants) {
  fs::path fixturePath = resolveFixturePath();
  if (fixturePath.empty() || !fs::exists(fixturePath)) {
    GTEST_SKIP() << "SSML contract fixture not found (set PIPER_SSML_FIXTURE "
                    "or run from repo root)";
  }

  std::ifstream f(fixturePath);
  ASSERT_TRUE(f.is_open());
  std::stringstream buf;
  buf << f.rdbuf();
  json root = json::parse(buf.str());

  // break_strength.map: every entry must match breakStrengthMs().
  for (auto &el : root["break_strength"]["map"].items()) {
    uint32_t expected = el.value().get<uint32_t>();
    EXPECT_EQ(breakStrengthMs(el.key()), expected)
        << "strength=" << el.key();
  }
  // default_ms == medium == 400
  EXPECT_EQ(breakStrengthMs("medium"),
            root["break_strength"]["default_ms"].get<uint32_t>());
  // unknown_strength_fallback_ms
  EXPECT_EQ(
      breakStrengthMs("definitely-not-a-strength"),
      root["break_strength"]["unknown_strength_fallback_ms"].get<uint32_t>());

  // prosody_rate.named_map: every entry must match parseRate().
  for (auto &el : root["prosody_rate"]["named_map"].items()) {
    float expected = el.value().get<float>();
    EXPECT_TRUE(floatNear(parseRate(el.key()), expected))
        << "rate=" << el.key();
  }
  // default_rate == 1.0
  EXPECT_TRUE(floatNear(parseRate("not-a-rate"),
                        root["prosody_rate"]["default_rate"].get<float>()));

  // break_time fallback: unparseable -> 0 ms
  EXPECT_EQ(parseBreakTime("garbage"),
            root["break_time"]["unparseable_fallback_ms"].get<uint32_t>());

  // segment_defaults: confirm SsmlSegment default-constructs to the
  // contract values.
  SsmlSegment def{};
  EXPECT_EQ(def.text, root["segment_defaults"]["text"].get<std::string>());
  EXPECT_EQ(def.breakMs,
            root["segment_defaults"]["break_ms"].get<uint32_t>());
  EXPECT_TRUE(floatNear(def.rate,
                        root["segment_defaults"]["rate"].get<float>()));
}

} // namespace
