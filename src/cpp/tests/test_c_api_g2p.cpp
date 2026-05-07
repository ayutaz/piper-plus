/**
 * Test: Engine-less G2P C API (piper_plus_g2p_*)
 *
 * Issue #388 — engine-less G2P entrypoints used by the Kotlin Android AAR
 * (and Dart FFI / Godot / Unity for the same reason: skip the ONNX model).
 *
 * Categories:
 *   - G2pCreate:           handle lifecycle, NULL safety
 *   - G2pAvailableLangs:   built-in 8-language map exposed in deterministic order
 *   - G2pPhonemize:        phonemize without ONNX, BORROWED-pointer lifetimes
 *   - G2pZhEnDispatch:     ZH-EN code-switching toggle
 *   - G2pCustomDict:       custom dictionary loading
 */

#include <gtest/gtest.h>
#include "piper_plus.h"

#include <cstring>
#include <set>
#include <string>

// ===== Lifecycle / NULL safety =====

TEST(G2pCreate, CreateAndFreeWithNullDictDir) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    piper_plus_g2p_free(h);
}

TEST(G2pCreate, CreateAndFreeWithEmptyDictDir) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create("");
    ASSERT_NE(h, nullptr);
    piper_plus_g2p_free(h);
}

TEST(G2pCreate, FreeNullIsSafe) {
    piper_plus_g2p_free(nullptr);
    SUCCEED();
}

TEST(G2pCreate, MultipleHandlesAreIndependent) {
    PiperPlusG2pHandle *a = piper_plus_g2p_create(nullptr);
    PiperPlusG2pHandle *b = piper_plus_g2p_create(nullptr);
    ASSERT_NE(a, nullptr);
    ASSERT_NE(b, nullptr);
    EXPECT_NE(a, b);
    piper_plus_g2p_free(a);
    piper_plus_g2p_free(b);
}

// ===== Available languages =====

TEST(G2pAvailableLangs, ReturnsAllEightLanguages) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    const char *codes = piper_plus_g2p_available_languages(h);
    ASSERT_NE(codes, nullptr);

    // Split comma-separated string into a set
    std::set<std::string> langs;
    std::string s = codes;
    size_t pos = 0;
    while (pos < s.size()) {
        size_t comma = s.find(',', pos);
        if (comma == std::string::npos) comma = s.size();
        langs.insert(s.substr(pos, comma - pos));
        pos = comma + 1;
    }
    EXPECT_EQ(langs.size(), 8u);
    for (const auto &expected : {"en", "es", "fr", "ja", "ko", "pt", "sv", "zh"}) {
        EXPECT_TRUE(langs.count(expected)) << "missing language: " << expected;
    }
    piper_plus_g2p_free(h);
}

TEST(G2pAvailableLangs, OrderIsAlphabeticDeterministic) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    const char *codes = piper_plus_g2p_available_languages(h);
    EXPECT_STREQ(codes, "en,es,fr,ja,ko,pt,sv,zh");
    piper_plus_g2p_free(h);
}

TEST(G2pAvailableLangs, NullHandleReturnsEmpty) {
    const char *codes = piper_plus_g2p_available_languages(nullptr);
    ASSERT_NE(codes, nullptr);
    EXPECT_STREQ(codes, "");
}

// ===== Phonemize: NULL safety =====

TEST(G2pPhonemize, NullHandleReturnsErr) {
    PiperPlusPhonemeResult result;
    PiperPlusStatus rc = piper_plus_g2p_phonemize(nullptr, "hello", "en", &result);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
    const char *err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(G2pPhonemize, NullOutResultReturnsErr) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    PiperPlusStatus rc = piper_plus_g2p_phonemize(h, "hello", "en", nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
    piper_plus_g2p_free(h);
}

TEST(G2pPhonemize, NullTextIsTreatedAsEmpty) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    PiperPlusPhonemeResult result;
    PiperPlusStatus rc = piper_plus_g2p_phonemize(h, nullptr, "en", &result);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_EQ(result.num_phonemes, 0);
    piper_plus_g2p_free(h);
}

TEST(G2pPhonemize, EmptyTextProducesZeroPhonemes) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    PiperPlusPhonemeResult result;
    PiperPlusStatus rc = piper_plus_g2p_phonemize(h, "", "en", &result);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_EQ(result.num_phonemes, 0);
    piper_plus_g2p_free(h);
}

TEST(G2pPhonemize, UnknownLanguageReturnsErr) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    PiperPlusPhonemeResult result;
    PiperPlusStatus rc = piper_plus_g2p_phonemize(h, "hello", "xx", &result);
    EXPECT_EQ(rc, PIPER_PLUS_ERR_TEXT);
    piper_plus_g2p_free(h);
}

// ===== Phonemize: rule-based languages (no dictionary required) =====

TEST(G2pPhonemize, SpanishRuleBasedProducesPhonemes) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    PiperPlusPhonemeResult result;
    PiperPlusStatus rc = piper_plus_g2p_phonemize(h, "hola mundo", "es", &result);
    ASSERT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GT(result.num_phonemes, 0);
    EXPECT_NE(result.phonemes, nullptr);
    EXPECT_STREQ(result.language, "es");
    piper_plus_g2p_free(h);
}

TEST(G2pPhonemize, FrenchRuleBasedProducesPhonemes) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    PiperPlusPhonemeResult result;
    PiperPlusStatus rc = piper_plus_g2p_phonemize(h, "bonjour", "fr", &result);
    ASSERT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GT(result.num_phonemes, 0);
    EXPECT_STREQ(result.language, "fr");
    piper_plus_g2p_free(h);
}

TEST(G2pPhonemize, PortugueseRuleBasedProducesPhonemes) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    PiperPlusPhonemeResult result;
    PiperPlusStatus rc = piper_plus_g2p_phonemize(h, "bom dia", "pt", &result);
    ASSERT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GT(result.num_phonemes, 0);
    piper_plus_g2p_free(h);
}

// ===== Phonemize: ZH-EN dispatch toggle =====

TEST(G2pZhEnDispatch, EnabledByDefault) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    EXPECT_EQ(piper_plus_g2p_is_zh_en_dispatch_enabled(h), 1);
    piper_plus_g2p_free(h);
}

TEST(G2pZhEnDispatch, CanBeDisabledAndReEnabled) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    EXPECT_EQ(piper_plus_g2p_set_zh_en_dispatch(h, 0), PIPER_PLUS_OK);
    EXPECT_EQ(piper_plus_g2p_is_zh_en_dispatch_enabled(h), 0);
    EXPECT_EQ(piper_plus_g2p_set_zh_en_dispatch(h, 1), PIPER_PLUS_OK);
    EXPECT_EQ(piper_plus_g2p_is_zh_en_dispatch_enabled(h), 1);
    piper_plus_g2p_free(h);
}

TEST(G2pZhEnDispatch, NullHandleReturnsErr) {
    EXPECT_EQ(piper_plus_g2p_set_zh_en_dispatch(nullptr, 1), PIPER_PLUS_ERR);
    EXPECT_EQ(piper_plus_g2p_is_zh_en_dispatch_enabled(nullptr), -1);
}

// ===== Phonemize: BORROWED pointer lifetime =====

TEST(G2pPhonemize, RepeatedCallsOverwriteResultButHandleStaysValid) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    PiperPlusPhonemeResult r1;
    ASSERT_EQ(piper_plus_g2p_phonemize(h, "hola", "es", &r1), PIPER_PLUS_OK);
    std::string copied(r1.phonemes ? r1.phonemes : "");

    PiperPlusPhonemeResult r2;
    ASSERT_EQ(piper_plus_g2p_phonemize(h, "bonjour", "fr", &r2), PIPER_PLUS_OK);
    EXPECT_GT(r2.num_phonemes, 0);
    // r1.phonemes is invalidated now (BORROWED), but we kept a copy:
    EXPECT_FALSE(copied.empty());
    piper_plus_g2p_free(h);
}

TEST(G2pPhonemize, AvailableLanguagesPointerStableBetweenCalls) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    const char *codes1 = piper_plus_g2p_available_languages(h);
    std::string snapshot = codes1 ? codes1 : "";
    // After a phonemize call the language list contents must remain consistent.
    PiperPlusPhonemeResult result;
    piper_plus_g2p_phonemize(h, "hola", "es", &result);
    const char *codes2 = piper_plus_g2p_available_languages(h);
    EXPECT_STREQ(codes2, snapshot.c_str());
    piper_plus_g2p_free(h);
}

// ===== Custom dictionary =====

TEST(G2pCustomDict, NullHandleReturnsErr) {
    EXPECT_EQ(piper_plus_g2p_load_custom_dict(nullptr, "/path/x.json"),
              PIPER_PLUS_ERR);
}

TEST(G2pCustomDict, NullPathReturnsErr) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    EXPECT_EQ(piper_plus_g2p_load_custom_dict(h, nullptr), PIPER_PLUS_ERR);
    piper_plus_g2p_free(h);
}

TEST(G2pCustomDict, NonexistentPathReturnsErr) {
    PiperPlusG2pHandle *h = piper_plus_g2p_create(nullptr);
    ASSERT_NE(h, nullptr);
    EXPECT_EQ(piper_plus_g2p_load_custom_dict(h, "/nonexistent/path.json"),
              PIPER_PLUS_ERR);
    piper_plus_g2p_free(h);
}
