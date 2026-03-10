#include <gtest/gtest.h>
#include "../openjtalk_phonemize_utils.hpp"

using namespace piper;

// =========================================================================
// Issue #207: Context-dependent N Phoneme Variant Tests
// Tests for applyNPhonemeRules() — classifies N based on following phoneme
// =========================================================================

// --- N_m: Before bilabial consonants (m, my, b, by, p, py) ---

TEST(NVariantsTest, N_m_BeforeP) {
    // さんぽ (sanpo) — N before p
    std::vector<std::string> tokens = {"s", "a", "N", "p", "o"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[2], "N_m");
}

TEST(NVariantsTest, N_m_BeforeM) {
    // さんま (sanma) — N before m
    std::vector<std::string> tokens = {"s", "a", "N", "m", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[2], "N_m");
}

TEST(NVariantsTest, N_m_BeforeB) {
    // さんば (sanba) — N before b
    std::vector<std::string> tokens = {"s", "a", "N", "b", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[2], "N_m");
}

TEST(NVariantsTest, N_m_BeforePy) {
    // N before py (palatalized bilabial)
    std::vector<std::string> tokens = {"N", "py", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_m");
}

TEST(NVariantsTest, N_m_BeforeBy) {
    // N before by (palatalized bilabial)
    std::vector<std::string> tokens = {"N", "by", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_m");
}

TEST(NVariantsTest, N_m_BeforeMy) {
    // N before my (palatalized bilabial)
    std::vector<std::string> tokens = {"N", "my", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_m");
}

// --- N_n: Before alveolar consonants (n, ny, t, ty, d, dy, ts, ch) ---

TEST(NVariantsTest, N_n_BeforeN) {
    // あんない (annai) — N before n
    std::vector<std::string> tokens = {"a", "N", "n", "a", "i"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[1], "N_n");
}

TEST(NVariantsTest, N_n_BeforeT) {
    // N before t
    std::vector<std::string> tokens = {"N", "t", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_n");
}

TEST(NVariantsTest, N_n_BeforeD) {
    // N before d
    std::vector<std::string> tokens = {"N", "d", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_n");
}

TEST(NVariantsTest, N_n_BeforeTs) {
    // N before ts
    std::vector<std::string> tokens = {"N", "ts", "u"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_n");
}

TEST(NVariantsTest, N_n_BeforeCh) {
    // N before ch
    std::vector<std::string> tokens = {"N", "ch", "i"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_n");
}

TEST(NVariantsTest, N_n_BeforeNy) {
    // N before ny
    std::vector<std::string> tokens = {"N", "ny", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_n");
}

TEST(NVariantsTest, N_n_BeforeTy) {
    // N before ty
    std::vector<std::string> tokens = {"N", "ty", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_n");
}

TEST(NVariantsTest, N_n_BeforeDy) {
    // N before dy
    std::vector<std::string> tokens = {"N", "dy", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_n");
}

// --- N_ng: Before velar consonants (k, ky, kw, g, gy, gw) ---

TEST(NVariantsTest, N_ng_BeforeK) {
    // ぎんこう (ginkou) — N before k
    std::vector<std::string> tokens = {"g", "i", "N", "k", "o", "u"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[2], "N_ng");
}

TEST(NVariantsTest, N_ng_BeforeG) {
    // N before g
    std::vector<std::string> tokens = {"N", "g", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_ng");
}

TEST(NVariantsTest, N_ng_BeforeKy) {
    // N before ky
    std::vector<std::string> tokens = {"N", "ky", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_ng");
}

TEST(NVariantsTest, N_ng_BeforeGy) {
    // N before gy
    std::vector<std::string> tokens = {"N", "gy", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_ng");
}

TEST(NVariantsTest, N_ng_BeforeKw) {
    // N before kw
    std::vector<std::string> tokens = {"N", "kw", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_ng");
}

TEST(NVariantsTest, N_ng_BeforeGw) {
    // N before gw
    std::vector<std::string> tokens = {"N", "gw", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_ng");
}

// --- N_uvular: End of phrase, before vowels, or other consonants ---

TEST(NVariantsTest, N_uvular_AtEnd) {
    // ほん (hon) — N at end of phrase
    std::vector<std::string> tokens = {"h", "o", "N"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[2], "N_uvular");
}

TEST(NVariantsTest, N_uvular_BeforeVowelA) {
    // ほんを (hon-o) — N before vowel
    std::vector<std::string> tokens = {"h", "o", "N", "o"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[2], "N_uvular");
}

TEST(NVariantsTest, N_uvular_BeforeVowelI) {
    // N before i
    std::vector<std::string> tokens = {"N", "i"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_uvular");
}

TEST(NVariantsTest, N_uvular_BeforeVowelU) {
    // N before u
    std::vector<std::string> tokens = {"N", "u"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_uvular");
}

TEST(NVariantsTest, N_uvular_BeforeVowelE) {
    // N before e
    std::vector<std::string> tokens = {"N", "e"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_uvular");
}

TEST(NVariantsTest, N_uvular_BeforeOtherConsonant) {
    // N before h (not bilabial, alveolar, or velar)
    std::vector<std::string> tokens = {"N", "h", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_uvular");
}

// --- Special token skipping ---

TEST(NVariantsTest, SkipProsodyMark_Bracket) {
    // N followed by ] then p — should skip ] and classify as N_m
    std::vector<std::string> tokens = {"N", "]", "p", "o"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_m");
}

TEST(NVariantsTest, SkipProsodyMark_Hash) {
    // N followed by # then k — should skip # and classify as N_ng
    std::vector<std::string> tokens = {"N", "#", "k", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_ng");
}

TEST(NVariantsTest, SkipProsodyMark_OpenBracket) {
    // N followed by [ then n — should skip [ and classify as N_n
    std::vector<std::string> tokens = {"N", "[", "n", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_n");
}

TEST(NVariantsTest, SkipMultipleSpecialTokens) {
    // N followed by ] # [ then m — should skip all specials
    std::vector<std::string> tokens = {"N", "]", "#", "[", "m", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_m");
}

TEST(NVariantsTest, OnlySpecialTokensAfterN) {
    // N followed by only special tokens — should be N_uvular
    std::vector<std::string> tokens = {"N", "]", "#", "$"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_uvular");
}

// --- Multiple N in sequence ---

TEST(NVariantsTest, MultipleN_DifferentContexts) {
    // Two N's with different following contexts
    std::vector<std::string> tokens = {"N", "p", "o", "#", "N", "k", "a"};
    applyNPhonemeRules(tokens);
    EXPECT_EQ(tokens[0], "N_m");   // before p
    EXPECT_EQ(tokens[4], "N_ng");  // before k
}

// --- isSpecialToken tests ---

TEST(NVariantsTest, IsSpecialToken_Markers) {
    EXPECT_TRUE(isSpecialToken("_"));
    EXPECT_TRUE(isSpecialToken("#"));
    EXPECT_TRUE(isSpecialToken("["));
    EXPECT_TRUE(isSpecialToken("]"));
    EXPECT_TRUE(isSpecialToken("^"));
    EXPECT_TRUE(isSpecialToken("$"));
    EXPECT_TRUE(isSpecialToken("?"));
    EXPECT_TRUE(isSpecialToken("?!"));
    EXPECT_TRUE(isSpecialToken("?."));
    EXPECT_TRUE(isSpecialToken("?~"));
}

TEST(NVariantsTest, IsSpecialToken_Phonemes) {
    EXPECT_FALSE(isSpecialToken("a"));
    EXPECT_FALSE(isSpecialToken("k"));
    EXPECT_FALSE(isSpecialToken("N"));
    EXPECT_FALSE(isSpecialToken("ch"));
    EXPECT_FALSE(isSpecialToken("ts"));
    EXPECT_FALSE(isSpecialToken("N_m"));
}
