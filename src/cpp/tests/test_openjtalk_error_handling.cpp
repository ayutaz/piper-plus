#include <gtest/gtest.h>
#include <cstring>
#include <thread>
#include <vector>

extern "C" {
#include "openjtalk_error.h"
#include "openjtalk_wrapper_functions.h"
}

class OpenJTalkErrorHandlingTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Setup test environment
    }

    void TearDown() override {
        // Clean up test environment
    }
};

// Test error string conversion
TEST_F(OpenJTalkErrorHandlingTest, ErrorToString) {
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_SUCCESS), "Success");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_NULL_INPUT), "Null input provided");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_EMPTY_INPUT), "Empty input provided");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_INPUT_TOO_LARGE), "Input size exceeds limit");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_INVALID_PATH), "Invalid path characters");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_DICTIONARY_NOT_FOUND), "Dictionary not found");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_VOICE_NOT_FOUND), "Voice file not found");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_BINARY_NOT_FOUND), "OpenJTalk binary not found");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_MEMORY), "Memory allocation failed");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_BUFFER_TOO_SMALL), "Buffer too small");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_IO_READ), "Failed to read file");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_IO_WRITE), "Failed to write file");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_TEMP_FILE), "Temporary file operation failed");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_COMMAND_FAILED), "Command execution failed");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_PARSE_OUTPUT), "Failed to parse output");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_SECURITY), "Security validation failed");
    EXPECT_STREQ(openjtalk_error_to_string(OPENJTALK_ERROR_UNKNOWN), "Unknown error");
    EXPECT_STREQ(openjtalk_error_to_string((OpenJTalkError)999), "Unknown error");
}

// Test result setting
TEST_F(OpenJTalkErrorHandlingTest, SetResult) {
    OpenJTalkResult result = {OPENJTALK_SUCCESS, ""};
    
    // Test simple error message
    openjtalk_set_result(&result, OPENJTALK_ERROR_NULL_INPUT, NULL);
    EXPECT_EQ(result.code, OPENJTALK_ERROR_NULL_INPUT);
    EXPECT_STREQ(result.message, "Null input provided");
    
    // Test formatted error message
    openjtalk_set_result(&result, OPENJTALK_ERROR_IO_READ, "Failed to open file: %s", "test.txt");
    EXPECT_EQ(result.code, OPENJTALK_ERROR_IO_READ);
    EXPECT_STREQ(result.message, "Failed to open file: test.txt");
    
    // Test with NULL result pointer (should not crash)
    openjtalk_set_result(NULL, OPENJTALK_ERROR_MEMORY, "Test message");
    
    // Test very long message (should be truncated)
    char long_msg[300];
    memset(long_msg, 'A', sizeof(long_msg) - 1);
    long_msg[sizeof(long_msg) - 1] = '\0';
    openjtalk_set_result(&result, OPENJTALK_ERROR_BUFFER_TOO_SMALL, "%s", long_msg);
    EXPECT_EQ(result.code, OPENJTALK_ERROR_BUFFER_TOO_SMALL);
    EXPECT_EQ(strlen(result.message), 255); // Should be truncated to 255 chars
    EXPECT_EQ(result.message[255], '\0'); // Should be null-terminated
}

// Test invalid input handling
TEST_F(OpenJTalkErrorHandlingTest, InvalidInput) {
    // Test NULL input
    char* phonemes = openjtalk_text_to_phonemes(NULL);
    EXPECT_EQ(phonemes, nullptr);
    
    // Test empty string
    phonemes = openjtalk_text_to_phonemes("");
    EXPECT_EQ(phonemes, nullptr);
}

// Test input size limits
TEST_F(OpenJTalkErrorHandlingTest, InputSizeLimits) {
    // Create a string that exceeds the maximum input size
    size_t max_size = 1024 * 1024; // 1MB limit
    char* huge_input = (char*)malloc(max_size + 100);
    if (huge_input) {
        memset(huge_input, 'A', max_size + 99);
        huge_input[max_size + 99] = '\0';
        
        // Should fail gracefully
        char* phonemes = openjtalk_text_to_phonemes(huge_input);
        EXPECT_EQ(phonemes, nullptr);
        
        free(huge_input);
    }
}

// Test thread safety of error handling
TEST_F(OpenJTalkErrorHandlingTest, ThreadSafety) {
    // Test that multiple threads can use openjtalk_text_to_phonemes
    // without interfering with each other
    const int num_threads = 4;
    std::vector<std::thread> threads;
    std::vector<std::string> test_texts = {
        "こんにちは",
        "ありがとう", 
        "さようなら",
        "おはよう"
    };
    
    // Skip this test if OpenJTalk binary is not available
    if (!openjtalk_is_available()) {
        GTEST_SKIP() << "OpenJTalk binary not available";
    }
    
    for (int i = 0; i < num_threads; i++) {
        threads.emplace_back([i, &test_texts]() {
            for (int j = 0; j < 10; j++) {
                char* phonemes = openjtalk_text_to_phonemes(test_texts[i % test_texts.size()].c_str());
                if (phonemes) {
                    openjtalk_free_phonemes(phonemes);
                }
            }
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
}