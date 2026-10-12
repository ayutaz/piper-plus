// Public configs can carry the IPA tokens ɔɪ / œ̃ / ɐ̃ as raw keys.
// Resolve these known aliases to the canonical internal PUA codepoints without
// changing their model IDs. Unknown tokens and conflicting aliases must fail.
//
//   ɔɪ = U+0254 U+026A  -> PUA U+E062
//   œ̃  = U+0153 U+0303  -> PUA U+E063
//   ɐ̃  = U+0250 U+0303  -> PUA U+E064
// (PUA codepoints are the canonical values from
//  src/python/g2p/piper_plus_g2p/data/pua.json.)

#include <gtest/gtest.h>

#include <stdexcept>
#include <string>

#include "../piper.hpp"
#include "json.hpp"

using json = nlohmann::json;

namespace piper {
// Free function defined in piper.cpp (intentionally not declared in piper.hpp).
// Declared here so the test can exercise the config parser directly.
void parsePhonemizeConfig(json &configRoot, PhonemizeConfig &phonemizeConfig);
}  // namespace piper

namespace {

// UTF-8 encodings of the three IPA tokens that leaked as raw multi-codepoint
// keys, plus their canonical PUA single-codepoint encodings.
const std::string kOI = "\xC9\x94\xCA\xAA";       // ɔɪ  (U+0254 U+026A)
const std::string kOEtilde = "\xC5\x93\xCC\x83";  // œ̃   (U+0153 U+0303)
const std::string kAtilde = "\xC9\x90\xCC\x83";   // ɐ̃   (U+0250 U+0303)
const std::string kPuaOI = "\xEE\x81\xA2";        // U+E062
const std::string kPuaOEtilde = "\xEE\x81\xA3";   // U+E063
const std::string kPuaAtilde = "\xEE\x81\xA4";    // U+E064

}  // namespace

// --- isSingleCodepoint predicate (the gate at piper.cpp's phoneme_id_map loop)

TEST(PhonemizeConfigParse, RawMultiCodepointTokensAreNotSingleCodepoint) {
    EXPECT_FALSE(piper::isSingleCodepoint(kOI));
    EXPECT_FALSE(piper::isSingleCodepoint(kOEtilde));
    EXPECT_FALSE(piper::isSingleCodepoint(kAtilde));
}

TEST(PhonemizeConfigParse, PuaEncodedTokensAreSingleCodepoint) {
    EXPECT_TRUE(piper::isSingleCodepoint(kPuaOI));
    EXPECT_TRUE(piper::isSingleCodepoint(kPuaOEtilde));
    EXPECT_TRUE(piper::isSingleCodepoint(kPuaAtilde));
}

// --- parsePhonemizeConfig end-to-end behavior

TEST(PhonemizeConfigParse, RawKnownTokensPreserveModelIds) {
    json cfg = {
        {"phoneme_type", "multilingual"},
        {"phoneme_id_map",
         {
             {"_", {0}},
             {"a", {10}},
             {kOI, {94}},
             {kOEtilde, {149}},
             {kAtilde, {153}},
         }},
    };
    piper::PhonemizeConfig pc;
    ASSERT_NO_THROW(piper::parsePhonemizeConfig(cfg, pc));
    EXPECT_EQ(pc.phonemeIdMap.at(0xE062), std::vector<piper::PhonemeId>({94}));
    EXPECT_EQ(pc.phonemeIdMap.at(0xE063), std::vector<piper::PhonemeId>({149}));
    EXPECT_EQ(pc.phonemeIdMap.at(0xE064), std::vector<piper::PhonemeId>({153}));
    EXPECT_EQ(pc.phonemeIdMap.at(U'a'), std::vector<piper::PhonemeId>({10}));
}

TEST(PhonemizeConfigParse, UnknownMultiCodepointKeyIsRejected) {
    json cfg = {{"phoneme_id_map", {{"unknown-token", {149}}}}};
    piper::PhonemizeConfig pc;
    EXPECT_THROW(piper::parsePhonemizeConfig(cfg, pc), std::runtime_error);
}

TEST(PhonemizeConfigParse, MatchingRawAndPuaAliasesDoNotDuplicateIds) {
    json cfg = {{"phoneme_id_map", {{kOEtilde, {149}}, {kPuaOEtilde, {149}}}}};
    piper::PhonemizeConfig pc;
    ASSERT_NO_THROW(piper::parsePhonemizeConfig(cfg, pc));
    EXPECT_EQ(pc.phonemeIdMap.at(0xE063), std::vector<piper::PhonemeId>({149}));
}

TEST(PhonemizeConfigParse, ConflictingRawAndPuaAliasesAreRejected) {
    json cfg = {{"phoneme_id_map", {{kOEtilde, {149}}, {kPuaOEtilde, {150}}}}};
    piper::PhonemizeConfig pc;
    EXPECT_THROW(piper::parsePhonemizeConfig(cfg, pc), std::runtime_error);
}

TEST(PhonemizeConfigParse, PuaEncodedConfigParsesAndMaps) {
    // The corrected (PUA-encoded) form must parse cleanly and map each PUA
    // codepoint to its id.
    json cfg = {
        {"phoneme_type", "multilingual"},
        {"phoneme_id_map",
         {
             {"_", {0}},
             {"a", {10}},
             {kPuaOI, {94}},        // ɔɪ -> U+E062
             {kPuaOEtilde, {149}},  // œ̃  -> U+E063
             {kPuaAtilde, {153}},   // ɐ̃  -> U+E064
         }},
    };
    piper::PhonemizeConfig pc;
    ASSERT_NO_THROW(piper::parsePhonemizeConfig(cfg, pc));

    auto it = pc.phonemeIdMap.find(static_cast<piper::Phoneme>(0xE063));
    ASSERT_NE(it, pc.phonemeIdMap.end())
        << "PUA codepoint U+E063 (œ̃) must be present in the id map";
    ASSERT_FALSE(it->second.empty());
    EXPECT_EQ(it->second[0], 149);
}
