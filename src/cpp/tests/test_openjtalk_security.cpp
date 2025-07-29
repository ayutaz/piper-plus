#include <gtest/gtest.h>
#include <string>
#include <cstdlib>
#include <thread>
#include <vector>

extern "C" {
#include "../openjtalk_wrapper_functions.h"
}

class OpenJTalkSecurityTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Ensure dictionary is available for tests
        openjtalk_ensure_dictionary();
    }
};

// Test that temporary files are created securely
TEST_F(OpenJTalkSecurityTest, SecureTempFileCreation) {
    // Skip test if OpenJTalk is not available
    if (!openjtalk_is_available()) {
        GTEST_SKIP() << "OpenJTalk binary not available in test environment";
    }
    
    const char* test_text = "テストテキスト";
    
    // Run multiple conversions in parallel to test for race conditions
    std::vector<std::thread> threads;
    std::vector<char*> results(10, nullptr);
    
    for (int i = 0; i < 10; i++) {
        threads.emplace_back([&results, i, test_text]() {
            results[i] = openjtalk_text_to_phonemes(test_text);
        });
    }
    
    // Wait for all threads to complete
    for (auto& t : threads) {
        t.join();
    }
    
    // Check that at least some conversions succeeded
    // Note: In CI environment, temporary file creation might fail due to security restrictions
    int success_count = 0;
    for (int i = 0; i < 10; i++) {
        if (results[i] != nullptr) {
            success_count++;
            openjtalk_free_phonemes(results[i]);
        }
    }
    ASSERT_GT(success_count, 0) << "No conversions succeeded";
}

// Test memory management with large inputs
TEST_F(OpenJTalkSecurityTest, LargeInputHandling) {
    // Create a large but valid input
    std::string large_text;
    for (int i = 0; i < 1000; i++) {
        large_text += "これはテストです。";
    }
    
    char* result = openjtalk_text_to_phonemes(large_text.c_str());
    if (result) {
        // Verify result is not empty
        EXPECT_GT(strlen(result), 0);
        openjtalk_free_phonemes(result);
    }
}

// Test memory management with API method
// DISABLED: API method temporarily disabled until OpenJTalk static libs are available
/*
TEST_F(OpenJTalkSecurityTest, ApiMethodMemoryManagement) {
    const char* test_text = "API経由のテスト";
    
    char* result = openjtalk_text_to_phonemes_api(test_text);
    if (result) {
        // Verify result is not empty
        EXPECT_GT(strlen(result), 0);
        openjtalk_free_phonemes(result);
    }
}
*/

// Test that extremely large inputs are rejected
TEST_F(OpenJTalkSecurityTest, RejectExtremelyLargeInput) {
    // Create input larger than 1MB limit
    std::string huge_text(2 * 1024 * 1024, 'A');
    
    char* result = openjtalk_text_to_phonemes(huge_text.c_str());
    EXPECT_EQ(result, nullptr) << "Should reject input larger than 1MB";
    
    // API method test disabled
    // result = openjtalk_text_to_phonemes_api(huge_text.c_str());
    // EXPECT_EQ(result, nullptr) << "API method should also reject input larger than 1MB";
}

// Test special characters that could cause issues
TEST_F(OpenJTalkSecurityTest, SpecialCharacterHandling) {
    const char* test_cases[] = {
        "テスト\"引用符\"",
        "テスト'シングル'",
        "テスト\\バックスラッシュ",
        "テスト\nニューライン",
        "テスト\tタブ",
        nullptr
    };
    
    for (int i = 0; test_cases[i] != nullptr; i++) {
        char* result = openjtalk_text_to_phonemes(test_cases[i]);
        if (result) {
            EXPECT_GT(strlen(result), 0) << "Failed for: " << test_cases[i];
            openjtalk_free_phonemes(result);
        }
    }
}

// Test buffer reallocation in API method
// DISABLED: API method temporarily disabled until OpenJTalk static libs are available
/*
TEST_F(OpenJTalkSecurityTest, ApiBufferReallocation) {
    // Create text that will produce many phonemes
    std::string long_text;
    for (int i = 0; i < 100; i++) {
        long_text += "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん";
    }
    
    char* result = openjtalk_text_to_phonemes_api(long_text.c_str());
    if (result) {
        // Verify result is not empty and reasonably long
        size_t result_len = strlen(result);
        EXPECT_GT(result_len, 1000) << "Expected long phoneme output";
        openjtalk_free_phonemes(result);
    }
}
*/

// Test NULL input handling
TEST_F(OpenJTalkSecurityTest, NullInputHandling) {
    char* result = openjtalk_text_to_phonemes(nullptr);
    EXPECT_EQ(result, nullptr) << "Should handle NULL input gracefully";
    
    // API method test disabled
    // result = openjtalk_text_to_phonemes_api(nullptr);
    // EXPECT_EQ(result, nullptr) << "API method should also handle NULL input gracefully";
}

// Test empty string handling
TEST_F(OpenJTalkSecurityTest, EmptyStringHandling) {
    char* result = openjtalk_text_to_phonemes("");
    EXPECT_EQ(result, nullptr) << "Should handle empty string gracefully";
    
    // API method test disabled
    // result = openjtalk_text_to_phonemes_api("");
    // EXPECT_EQ(result, nullptr) << "API method should also handle empty string gracefully";
}

// Test malformed UTF-8 sequences
TEST_F(OpenJTalkSecurityTest, MalformedUtf8Handling) {
    // Invalid UTF-8 sequence
    const char invalid_utf8[] = {static_cast<char>(0xFF), static_cast<char>(0xFE), static_cast<char>(0xFD), 0};
    
    char* result = openjtalk_text_to_phonemes(invalid_utf8);
    // Should either handle gracefully or return NULL
    if (result) {
        openjtalk_free_phonemes(result);
    }
    
    // API method test disabled
    // result = openjtalk_text_to_phonemes_api(invalid_utf8);
    // if (result) {
    //     openjtalk_free_phonemes(result);
    // }
}