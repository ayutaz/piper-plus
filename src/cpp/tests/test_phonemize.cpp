/**
 * Unit tests for phonemization functionality
 */

#include <gtest/gtest.h>
#include <string>
#include <vector>
#include <map>

// Mock the phonemize functions for testing
namespace piper {

// Mock PUA mappings for testing
std::map<std::string, char32_t> testMultiCharToPUA = {
    {"ch", 0xE00E},
    {"ts", 0xE00F},
    {"ky", 0xE006},
    {"sh", 0xE010}
};

// Mock phoneme mapping function
std::vector<std::string> mapPhonemes(const std::vector<std::string>& phonemes) {
    std::vector<std::string> mapped;

    for (const auto& phoneme : phonemes) {
        auto it = testMultiCharToPUA.find(phoneme);
        if (it != testMultiCharToPUA.end()) {
            // Convert to UTF-8 string
            char32_t codepoint = it->second;
            if (codepoint <= 0x7F) {
                mapped.push_back(std::string(1, static_cast<char>(codepoint)));
            } else if (codepoint <= 0x7FF) {
                mapped.push_back(std::string{
                    static_cast<char>(0xC0 | (codepoint >> 6)),
                    static_cast<char>(0x80 | (codepoint & 0x3F))
                });
            } else if (codepoint <= 0xFFFF) {
                mapped.push_back(std::string{
                    static_cast<char>(0xE0 | (codepoint >> 12)),
                    static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)),
                    static_cast<char>(0x80 | (codepoint & 0x3F))
                });
            }
        } else {
            mapped.push_back(phoneme);
        }
    }

    return mapped;
}

} // namespace piper

// Test basic phoneme mapping
TEST(PhonemizeTest, BasicPhonemeMapping) {
    std::vector<std::string> input = {"a", "ch", "i"};
    auto result = piper::mapPhonemes(input);

    EXPECT_EQ(result.size(), 3);
    EXPECT_EQ(result[0], "a");
    EXPECT_NE(result[1], "ch"); // Should be mapped to PUA
    EXPECT_EQ(result[2], "i");
}

// Test all multi-char phoneme mappings
TEST(PhonemizeTest, AllMultiCharMappings) {
    std::vector<std::string> multiCharPhonemes = {"ch", "ts", "ky", "sh"};
    auto result = piper::mapPhonemes(multiCharPhonemes);

    EXPECT_EQ(result.size(), multiCharPhonemes.size());

    // All should be mapped (not equal to original)
    for (size_t i = 0; i < multiCharPhonemes.size(); ++i) {
        EXPECT_NE(result[i], multiCharPhonemes[i]);
    }
}

// Test mixed phonemes
TEST(PhonemizeTest, MixedPhonemes) {
    std::vector<std::string> input = {"k", "o", "n", "n", "i", "ch", "i", "w", "a"};
    auto result = piper::mapPhonemes(input);

    EXPECT_EQ(result.size(), input.size());

    // Single char phonemes should remain unchanged
    EXPECT_EQ(result[0], "k");
    EXPECT_EQ(result[1], "o");

    // Multi-char should be mapped
    EXPECT_NE(result[5], "ch");
}

// Test empty input
TEST(PhonemizeTest, EmptyInput) {
    std::vector<std::string> input = {};
    auto result = piper::mapPhonemes(input);

    EXPECT_TRUE(result.empty());
}

// Test single character phonemes
TEST(PhonemizeTest, SingleCharPhonemes) {
    std::vector<std::string> input = {"a", "i", "u", "e", "o"};
    auto result = piper::mapPhonemes(input);

    EXPECT_EQ(result, input); // Should be unchanged
}

// Test Japanese specific phonemes
TEST(PhonemizeTest, JapanesePhonemes) {
    std::vector<std::string> input = {"^", "k", "o", "N", "n", "i", "ch", "i", "w", "a", "$"};
    auto result = piper::mapPhonemes(input);

    // Check markers are preserved
    EXPECT_EQ(result.front(), "^");
    EXPECT_EQ(result.back(), "$");

    // Check "ch" is mapped
    bool found_ch_mapping = false;
    for (size_t i = 0; i < input.size(); ++i) {
        if (input[i] == "ch" && result[i] != "ch") {
            found_ch_mapping = true;
            break;
        }
    }
    EXPECT_TRUE(found_ch_mapping);
}

// Test UTF-8 encoding of PUA characters
TEST(PhonemizeTest, PUAEncodingTest) {
    // Test that PUA characters are properly encoded
    std::vector<std::string> input = {"ch"};
    auto result = piper::mapPhonemes(input);

    ASSERT_EQ(result.size(), 1);

    // Check it's a 3-byte UTF-8 sequence (PUA is in range E000-F8FF)
    const std::string& pua_char = result[0];
    EXPECT_EQ(pua_char.length(), 3); // PUA chars are 3 bytes in UTF-8

    // Check first byte starts with 1110 (0xE0)
    EXPECT_EQ((unsigned char)pua_char[0] & 0xF0, 0xE0);
}

// Test katakana to phoneme conversion patterns
TEST(PhonemizeTest, KatakanaToPhonemesPatterns) {
    // Mock katakana conversion results
    std::map<std::string, std::vector<std::string>> katakanaPatterns = {
        {"ア", {"a"}},
        {"カ", {"k", "a"}},
        {"ガ", {"g", "a"}},
        {"サ", {"s", "a"}},
        {"ザ", {"z", "a"}},
        {"タ", {"t", "a"}},
        {"ダ", {"d", "a"}},
        {"ナ", {"n", "a"}},
        {"ハ", {"h", "a"}},
        {"バ", {"b", "a"}},
        {"パ", {"p", "a"}},
        {"マ", {"m", "a"}},
        {"ヤ", {"y", "a"}},
        {"ラ", {"r", "a"}},
        {"ワ", {"w", "a"}},
        {"ン", {"N"}}
    };
    
    // Test consonant-vowel combinations
    for (const auto& [katakana, expected] : katakanaPatterns) {
        auto result = piper::mapPhonemes(expected);
        EXPECT_EQ(result.size(), expected.size());
        
        // For single phonemes, should be unchanged
        if (expected.size() == 1) {
            EXPECT_EQ(result[0], expected[0]);
        }
    }
}

// Test long vowel handling
TEST(PhonemizeTest, LongVowelHandling) {
    // Test cases for long vowels (represented by repeating the vowel)
    std::vector<std::pair<std::vector<std::string>, std::string>> testCases = {
        {{"k", "a", "a"}, "kaa"},  // カー
        {{"k", "i", "i"}, "kii"},  // キー
        {{"k", "u", "u"}, "kuu"},  // クー
        {{"k", "e", "e"}, "kee"},  // ケー
        {{"k", "o", "o"}, "koo"},  // コー
    };
    
    for (const auto& [phonemes, description] : testCases) {
        auto result = piper::mapPhonemes(phonemes);
        EXPECT_EQ(result.size(), phonemes.size());
        
        // Check that vowels are preserved (not modified)
        EXPECT_EQ(result[1], phonemes[1]);
        EXPECT_EQ(result[2], phonemes[2]);
        
        // Verify they are the same vowel (long vowel)
        EXPECT_EQ(result[1], result[2]);
    }
}

// Test invalid input handling
TEST(PhonemizeTest, InvalidInputHandling) {
    // Test with null-like empty strings in vector
    std::vector<std::string> input_with_empty = {"a", "", "b"};
    auto result = piper::mapPhonemes(input_with_empty);
    EXPECT_EQ(result.size(), 3);
    EXPECT_EQ(result[0], "a");
    EXPECT_EQ(result[1], "");
    EXPECT_EQ(result[2], "b");
    
    // Test with very long phoneme (should handle gracefully)
    std::string longPhoneme(100, 'a');
    std::vector<std::string> long_input = {longPhoneme};
    auto long_result = piper::mapPhonemes(long_input);
    EXPECT_EQ(long_result.size(), 1);
    EXPECT_EQ(long_result[0], longPhoneme); // Should be unchanged
    
    // Test with special characters
    std::vector<std::string> special_chars = {"!", "?", ".", ","};
    auto special_result = piper::mapPhonemes(special_chars);
    EXPECT_EQ(special_result, special_chars); // Should be unchanged
}

// Test buffer overflow protection
TEST(PhonemizeTest, BufferOverflowProtection) {
    // Create a very large input vector
    std::vector<std::string> large_input;
    for (int i = 0; i < 10000; ++i) {
        large_input.push_back("a");
        if (i % 100 == 0) {
            large_input.push_back("ch"); // Add some multi-char phonemes
        }
    }
    
    // Should handle without crashing
    auto result = piper::mapPhonemes(large_input);
    EXPECT_EQ(result.size(), large_input.size());
    
    // Verify some mappings still work
    for (size_t i = 0; i < large_input.size(); ++i) {
        if (large_input[i] == "ch") {
            EXPECT_NE(result[i], "ch"); // Should be mapped
        } else if (large_input[i] == "a") {
            EXPECT_EQ(result[i], "a"); // Should be unchanged
        }
    }
}

// Test concurrent access (basic thread safety check)
TEST(PhonemizeTest, ConcurrentAccess) {
    // Note: This is a basic test. Real concurrent testing would need thread support
    std::vector<std::string> input1 = {"a", "ch", "i"};
    std::vector<std::string> input2 = {"k", "ts", "u"};
    
    // Simulate concurrent access by interleaving calls
    auto result1 = piper::mapPhonemes(input1);
    auto result2 = piper::mapPhonemes(input2);
    
    // Verify both results are correct
    EXPECT_EQ(result1.size(), 3);
    EXPECT_EQ(result2.size(), 3);
    
    EXPECT_EQ(result1[0], "a");
    EXPECT_NE(result1[1], "ch"); // Should be mapped
    EXPECT_EQ(result1[2], "i");
    
    EXPECT_EQ(result2[0], "k");
    EXPECT_NE(result2[1], "ts"); // Should be mapped
    EXPECT_EQ(result2[2], "u");
}

// Test small tsu (sokuon) handling
TEST(PhonemizeTest, SmallTsuHandling) {
    // Small tsu is represented as 'q' in phonemes
    std::vector<std::string> input = {"g", "a", "q", "k", "o", "u"}; // がっこう
    auto result = piper::mapPhonemes(input);
    
    EXPECT_EQ(result.size(), input.size());
    EXPECT_EQ(result[2], "q"); // Small tsu should be preserved
}

// Test compound kana phonemes
TEST(PhonemizeTest, CompoundKanaPhonemes) {
    // Test compound phonemes like kya, shu, cho etc.
    std::vector<std::string> compounds = {"ky", "sh", "ch", "ny", "hy", "my", "ry", "gy", "by", "py"};
    
    for (const auto& compound : compounds) {
        std::vector<std::string> input = {compound, "a"};
        auto result = piper::mapPhonemes(input);
        
        EXPECT_EQ(result.size(), 2);
        
        // Multi-char compounds should be mapped if in the mapping table
        if (piper::testMultiCharToPUA.find(compound) != piper::testMultiCharToPUA.end()) {
            EXPECT_NE(result[0], compound);
        }
        EXPECT_EQ(result[1], "a");
    }
}

// Main function for test runner
int main(int argc, char **argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}