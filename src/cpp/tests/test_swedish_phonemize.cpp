/**
 * Unit tests for Swedish rule-based G2P phonemizer.
 *
 * Covers: basic vowels (long/short), soft/hard consonant contexts,
 * retroflex assimilation (including cascade), sj-sound digraphs,
 * stress placement, loanword suffixes, review-fix rules (gj/dj/berg),
 * and edge cases (empty string, punctuation, invalid UTF-8).
 *
 * Total: 26 tests.
 */

#include <gtest/gtest.h>
#include <string>
#include <vector>

#include "../swedish_phonemize.hpp"
#include "../phoneme_parser.hpp"  // piper::Phoneme = char32_t

using namespace piper;

// =========================================================================
// IPA / PUA constants matching swedish_phonemize.cpp
// =========================================================================

// PUA long vowels
static constexpr Phoneme PUA_I_LONG   = 0xE059; // iː
static constexpr Phoneme PUA_Y_LONG   = 0xE05A; // yː
static constexpr Phoneme PUA_E_LONG   = 0xE05B; // eː
static constexpr Phoneme PUA_EPS_LONG = 0xE05C; // ɛː
static constexpr Phoneme PUA_OE_LONG  = 0xE05D; // øː
static constexpr Phoneme PUA_AH_LONG  = 0xE05E; // ɑː
static constexpr Phoneme PUA_O_LONG   = 0xE05F; // oː
static constexpr Phoneme PUA_U_LONG   = 0xE060; // uː
static constexpr Phoneme PUA_UB_LONG  = 0xE061; // ʉː

// IPA codepoints
static constexpr Phoneme IPA_STRESS   = 0x02C8; // ˈ
static constexpr Phoneme IPA_RETRO_T  = 0x0288; // ʈ
static constexpr Phoneme IPA_RETRO_N  = 0x0273; // ɳ
static constexpr Phoneme IPA_RETRO_S  = 0x0282; // ʂ
static constexpr Phoneme IPA_SJ       = 0x0267; // ɧ
static constexpr Phoneme IPA_TJ       = 0x0255; // ɕ
static constexpr Phoneme IPA_G_IPA    = 0x0261; // ɡ
static constexpr Phoneme IPA_EPSILON  = 0x025B; // ɛ
static constexpr Phoneme IPA_SM_CAP_I = 0x026A; // ɪ
static constexpr Phoneme IPA_OPEN_O   = 0x0254; // ɔ

// =========================================================================
// Helper: check if a phoneme sequence contains a given phoneme
// =========================================================================
static bool containsPhoneme(const std::vector<Phoneme> &seq, Phoneme target) {
    for (auto ph : seq) {
        if (ph == target) return true;
    }
    return false;
}

// =========================================================================
// 1. Basic vowels (3 tests)
// =========================================================================

TEST(SwedishVowelTest, GataLongA) {
    // "gata" = 2 syllables, stress on 1st => long vowel on stressed 'a'
    // Expected: first 'a' -> PUA_AH_LONG (ɑː)
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("gata", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_FALSE(phonemes[0].empty());
    EXPECT_TRUE(containsPhoneme(phonemes[0], PUA_AH_LONG))
        << "Stressed 'a' in 'gata' should produce long vowel (PUA_AH_LONG)";
}

TEST(SwedishVowelTest, FestShortE) {
    // "fest" = 1 syllable, stressed, but 'e' followed by 2 consonants (s,t) => short
    // Expected: 'e' -> IPA_EPSILON (ɛ)
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("fest", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_FALSE(phonemes[0].empty());
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_EPSILON))
        << "Short 'e' before consonant cluster in 'fest' should produce epsilon";
}

TEST(SwedishVowelTest, HusLongU) {
    // "hus" = 1 syllable, stressed, 'u' + single consonant => long
    // Expected: 'u' -> PUA_UB_LONG (ʉː)
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("hus", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_FALSE(phonemes[0].empty());
    EXPECT_TRUE(containsPhoneme(phonemes[0], PUA_UB_LONG))
        << "Stressed 'u' with single following consonant in 'hus' should be long";
}

// =========================================================================
// 2. Soft / hard consonants (4 tests)
// =========================================================================

TEST(SwedishConsonantTest, SkedSoftSk) {
    // "sked" = sk + front vowel 'e' -> sj-sound (ɧ)
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("sked", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_SJ))
        << "'sk' before front vowel 'e' in 'sked' should produce sj-sound";
}

TEST(SwedishConsonantTest, SkolaHardSk) {
    // "skola" = sk + back vowel 'o' -> plain sk (no sj-sound)
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("skola", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_FALSE(containsPhoneme(phonemes[0], IPA_SJ))
        << "'sk' before back vowel in 'skola' should NOT produce sj-sound";
    EXPECT_TRUE(containsPhoneme(phonemes[0], 's'))
        << "'skola' should contain 's' from plain sk";
    EXPECT_TRUE(containsPhoneme(phonemes[0], 'k'))
        << "'skola' should contain 'k' from plain sk";
}

TEST(SwedishConsonantTest, KopSoftK) {
    // "köp" = k + front vowel ö -> tj-sound (ɕ)
    // ö is U+00F6 in UTF-8: \xc3\xb6
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("k\xc3\xb6p", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_TJ))
        << "'k' before front vowel in 'köp' should produce tj-sound (ɕ)";
}

TEST(SwedishConsonantTest, FlickaHardK) {
    // "flicka" is in HARD_K_WORDS -> k stays hard (no ɕ)
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("flicka", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_FALSE(containsPhoneme(phonemes[0], IPA_TJ))
        << "'flicka' is an exception word: k should be hard, not tj-sound";
    EXPECT_TRUE(containsPhoneme(phonemes[0], 'k'))
        << "'flicka' should retain hard 'k'";
}

// =========================================================================
// 3. Retroflex assimilation (3 tests)
// =========================================================================

TEST(SwedishRetroflexTest, KortRetroflexT) {
    // "kort" = r + t -> retroflex ʈ
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("kort", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_RETRO_T))
        << "'kort': r + t should assimilate to retroflex ʈ";
    // 'r' should be consumed (not present in output)
    // The r is absorbed into the retroflex
}

TEST(SwedishRetroflexTest, BarnRetroflexN) {
    // "barn" = r + n -> retroflex ɳ
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("barn", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_RETRO_N))
        << "'barn': r + n should assimilate to retroflex ɳ";
}

TEST(SwedishRetroflexTest, ForstCascade) {
    // "först" = ö + r + s + t -> retroflex cascade: r+s -> ʂ, then ʂ propagates to t -> ʈ
    // först in UTF-8: f + ö(\xc3\xb6) + r + s + t
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("f\xc3\xb6rst", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_RETRO_S))
        << "'först': r + s should produce retroflex ʂ";
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_RETRO_T))
        << "'först': cascade should convert following t to retroflex ʈ";
}

// =========================================================================
// 4. Sj-sound variations (4 tests)
// =========================================================================

TEST(SwedishSjSoundTest, Sjuk) {
    // "sjuk" = sj -> ɧ
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("sjuk", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_SJ))
        << "'sj' in 'sjuk' should produce sj-sound (ɧ)";
}

TEST(SwedishSjSoundTest, Stjarna) {
    // "stjärna" = stj -> ɧ
    // stjärna in UTF-8: s + t + j + ä(\xc3\xa4) + r + n + a
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("stj\xc3\xa4rna", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_SJ))
        << "'stj' in 'stjärna' should produce sj-sound (ɧ)";
}

TEST(SwedishSjSoundTest, Chef) {
    // "chef" = ch -> ɧ (not an exception word)
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("chef", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_SJ))
        << "'ch' in 'chef' should produce sj-sound (ɧ)";
}

TEST(SwedishSjSoundTest, Schema) {
    // "schema" = sch -> ɧ
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("schema", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_SJ))
        << "'sch' in 'schema' should produce sj-sound (ɧ)";
}

// =========================================================================
// 5. Stress placement (3 tests)
// =========================================================================

TEST(SwedishStressTest, FlickaFirstSyllable) {
    // "flicka" = 2 syllables, no stress-attracting suffix, no prefix -> stress on syl 0
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("flicka", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    // Stress marker should be present (word has 2+ syllables and is not a function word)
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_STRESS))
        << "'flicka' should have a stress marker";
    // Stress marker should be at the beginning (before first syllable onset)
    ASSERT_FALSE(phonemes[0].empty());
    EXPECT_EQ(phonemes[0][0], IPA_STRESS)
        << "Stress should be on the first syllable of 'flicka'";
}

TEST(SwedishStressTest, StationSecondSyllable) {
    // "station" = -tion suffix attracts stress to the syllable before suffix
    // sta- (syl 0), -tion (suffix phonemes)
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("station", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_STRESS))
        << "'station' should have a stress marker";
    // -tion suffix should produce sj-sound
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_SJ))
        << "'station' -tion suffix should produce sj-sound (ɧ)";
}

TEST(SwedishStressTest, OchNoStress) {
    // "och" is a function word -> no stress marker
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("och", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_FALSE(containsPhoneme(phonemes[0], IPA_STRESS))
        << "Function word 'och' should have no stress marker";
}

// =========================================================================
// 6. Loanword suffixes (2 tests)
// =========================================================================

TEST(SwedishLoanwordTest, StationTionSuffix) {
    // "station" -> stem "sta" + suffix -tion -> ɧ uː n
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("station", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    // Suffix produces: ɧ uː n
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_SJ))
        << "-tion should produce sj-sound";
    EXPECT_TRUE(containsPhoneme(phonemes[0], PUA_U_LONG))
        << "-tion should produce long uː";
}

TEST(SwedishLoanwordTest, GarageAgeSuffix) {
    // "garage" -> -age suffix (not in native exceptions) -> ɑː ɧ
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("garage", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], PUA_AH_LONG))
        << "-age suffix in 'garage' should produce long ɑː";
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_SJ))
        << "-age suffix in 'garage' should produce sj-sound (ɧ)";
}

// =========================================================================
// 7. Review-fix rules (3 tests)
// =========================================================================

TEST(SwedishReviewFixTest, GjordGjToJ) {
    // "gjord" = word-initial gj -> j
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("gjord", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], 'j'))
        << "Word-initial 'gj' in 'gjord' should produce 'j'";
    // Should NOT contain ɡ (hard g) at the start
    ASSERT_FALSE(phonemes[0].empty());
    // First non-stress phoneme should be 'j', not ɡ
    Phoneme firstConsonant = phonemes[0][0];
    if (firstConsonant == IPA_STRESS && phonemes[0].size() > 1) {
        firstConsonant = phonemes[0][1];
    }
    EXPECT_EQ(firstConsonant, static_cast<Phoneme>('j'))
        << "First consonant of 'gjord' should be 'j' (gj -> j)";
}

TEST(SwedishReviewFixTest, DjurDjToJ) {
    // "djur" = word-initial dj -> j
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("djur", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], 'j'))
        << "Word-initial 'dj' in 'djur' should produce 'j'";
    // First phoneme (after possible stress marker) should be 'j'
    Phoneme firstConsonant = phonemes[0][0];
    if (firstConsonant == IPA_STRESS && phonemes[0].size() > 1) {
        firstConsonant = phonemes[0][1];
    }
    EXPECT_EQ(firstConsonant, static_cast<Phoneme>('j'))
        << "First consonant of 'djur' should be 'j' (dj -> j)";
}

TEST(SwedishReviewFixTest, GerHardGBeforeFrontVowel) {
    // "ger" is in HARD_G_WORDS: g before front vowel 'e' stays hard (ɡ), not /j/
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("ger", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_TRUE(containsPhoneme(phonemes[0], IPA_G_IPA))
        << "'ger' is an exception: g before 'e' should be hard (ɡ), not /j/";
    // Verify no /j/ at start (which would indicate soft-g)
    Phoneme firstConsonant = phonemes[0][0];
    if (firstConsonant == IPA_STRESS && phonemes[0].size() > 1) {
        firstConsonant = phonemes[0][1];
    }
    EXPECT_NE(firstConsonant, static_cast<Phoneme>('j'))
        << "'ger' should NOT have soft /j/ -- it is a hard-g exception";
}

// =========================================================================
// 8. Edge cases (4 tests)
// =========================================================================

TEST(SwedishEdgeCaseTest, EmptyString) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("", phonemes);

    EXPECT_TRUE(phonemes.empty())
        << "Empty input should produce no output";
}

TEST(SwedishEdgeCaseTest, PunctuationOnly) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("...", phonemes);

    // Punctuation is passed through
    ASSERT_EQ(phonemes.size(), 1u);
    for (auto ph : phonemes[0]) {
        EXPECT_EQ(ph, static_cast<Phoneme>('.'))
            << "Punctuation-only input should pass through dots";
    }
}

TEST(SwedishEdgeCaseTest, InvalidUtf8) {
    std::vector<std::vector<Phoneme>> phonemes;
    std::string invalid = "\xFF\xFE\x80";
    EXPECT_NO_THROW(phonemize_swedish(invalid, phonemes));
    EXPECT_TRUE(phonemes.empty())
        << "Invalid UTF-8 should return empty (phonemize_swedish validates input)";
}

TEST(SwedishEdgeCaseTest, MixedTextAndPunctuation) {
    // "Hej, Sverige!" -> word + punct + word + punct
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_swedish("Hej, Sverige!", phonemes);

    ASSERT_EQ(phonemes.size(), 1u);
    EXPECT_FALSE(phonemes[0].empty());
    // Should contain comma and exclamation mark
    EXPECT_TRUE(containsPhoneme(phonemes[0], static_cast<Phoneme>(',')))
        << "Output should contain comma punctuation";
    EXPECT_TRUE(containsPhoneme(phonemes[0], static_cast<Phoneme>('!')))
        << "Output should contain exclamation mark";
}
