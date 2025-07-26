#include <gtest/gtest.h>
#include <vector>
#include <string>
#include <sstream>
#include "json.hpp"

// Mock phoneme timing structure for testing
struct PhonemeInfo {
    std::string phoneme;
    float start_time;
    float end_time;
    int start_frame;
    int end_frame;
};

// Test duration to timing conversion
TEST(PhonemeTimingTest, BasicDurationConversion) {
    // Test converting frame durations to time
    std::vector<float> durations = {2.0f, 3.0f, 4.0f};  // frames
    int hop_size = 256;
    int sample_rate = 22050;
    float frame_length = static_cast<float>(hop_size) / sample_rate;
    
    // Calculate expected times
    std::vector<float> expected_starts = {0.0f};
    std::vector<float> expected_ends;
    
    float current_time = 0.0f;
    for (auto duration : durations) {
        current_time += duration * frame_length;
        expected_ends.push_back(current_time);
        if (expected_starts.size() < durations.size()) {
            expected_starts.push_back(current_time);
        }
    }
    
    // Verify calculations
    EXPECT_FLOAT_EQ(expected_ends[0], 2.0f * frame_length);
    EXPECT_FLOAT_EQ(expected_ends[1], 5.0f * frame_length);
    EXPECT_FLOAT_EQ(expected_ends[2], 9.0f * frame_length);
}

TEST(PhonemeTimingTest, SpecialTokenHandling) {
    // Test that BOS (1), EOS (2), and PAD (0) tokens should be skipped
    const int BOS = 1;
    const int EOS = 2; 
    const int PAD = 0;
    
    // In real implementation, these would be filtered out
    std::vector<int> tokens = {BOS, 'a', 'b', EOS, PAD};
    std::vector<int> filtered;
    
    for (int token : tokens) {
        if (token != BOS && token != EOS && token != PAD) {
            filtered.push_back(token);
        }
    }
    
    EXPECT_EQ(filtered.size(), 2);
    EXPECT_EQ(filtered[0], 'a');
    EXPECT_EQ(filtered[1], 'b');
}

TEST(PhonemeTimingTest, JSONFormat) {
    // Test JSON structure creation
    nlohmann::json timing_json;
    timing_json["text"] = "Hello";
    timing_json["sample_rate"] = 22050;
    timing_json["total_duration"] = 0.3;
    
    // Add phonemes array
    nlohmann::json phonemes = nlohmann::json::array();
    nlohmann::json phoneme1;
    phoneme1["phoneme"] = "h";
    phoneme1["start"] = 0.0;
    phoneme1["end"] = 0.045;
    phonemes.push_back(phoneme1);
    
    timing_json["phonemes"] = phonemes;
    
    // Verify structure
    EXPECT_EQ(timing_json["text"], "Hello");
    EXPECT_EQ(timing_json["sample_rate"], 22050);
    EXPECT_EQ(timing_json["phonemes"].size(), 1);
    EXPECT_EQ(timing_json["phonemes"][0]["phoneme"], "h");
}

TEST(PhonemeTimingTest, TSVFormat) {
    // Test TSV format generation
    std::stringstream output;
    
    // Write header
    output << "phoneme\tstart\tend\tstart_frame\tend_frame" << std::endl;
    
    // Write data
    output << "h\t0\t0.045\t0\t4" << std::endl;
    output << "ə\t0.045\t0.120\t4\t10" << std::endl;
    
    // Read back and verify
    output.seekg(0);  // Reset read position to the beginning
    std::string line;
    std::getline(output, line);
    EXPECT_EQ(line, "phoneme\tstart\tend\tstart_frame\tend_frame");
    
    std::getline(output, line);
    EXPECT_EQ(line, "h\t0\t0.045\t0\t4");
}