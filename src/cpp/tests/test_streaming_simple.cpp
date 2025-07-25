#include <gtest/gtest.h>
#include <vector>
#include <string>
#include <regex>
#include <algorithm>
#include <cstdint>

// Simple test for streaming text chunking logic
TEST(StreamingSimpleTest, TextChunkingEnglish) {
    std::string text = "Hello world. This is a test. Multiple sentences here!";
    std::regex sentenceBoundary("([.!?,;:]+|\\s+(?:and|or|but|because|while|when|if|that|which)\\s+)");
    
    std::vector<std::string> chunks;
    std::sregex_token_iterator iter(text.begin(), text.end(), sentenceBoundary, {-1, 1});
    std::sregex_token_iterator end;
    
    std::string currentChunk;
    for (; iter != end; ++iter) {
        std::string token = *iter;
        if (token.empty()) continue;
        
        // Check if this is a delimiter
        if (std::regex_match(token, sentenceBoundary)) {
            // Add delimiter to current chunk
            currentChunk += token;
            if (!currentChunk.empty() && 
                (token.find_first_of(".!?") != std::string::npos ||
                 currentChunk.length() > 100)) {
                // End of sentence or chunk is getting long
                chunks.push_back(currentChunk);
                currentChunk.clear();
            }
        } else {
            // Regular text
            currentChunk += token;
        }
    }
    
    // Add any remaining text
    if (!currentChunk.empty()) {
        chunks.push_back(currentChunk);
    }
    
    EXPECT_EQ(chunks.size(), 3) << "Expected 3 chunks for 3 sentences";
    EXPECT_EQ(chunks[0], "Hello world.");
    EXPECT_EQ(chunks[1], " This is a test.");
    EXPECT_EQ(chunks[2], " Multiple sentences here!");
}

TEST(StreamingSimpleTest, TextChunkingJapanese) {
    std::string text = u8"こんにちは。今日はいい天気ですね。ありがとう！";
    // Use simple character-by-character parsing for Japanese
    std::vector<std::string> chunks;
    std::string currentChunk;
    
    for (size_t i = 0; i < text.length(); ) {
        // Check for Japanese punctuation (3-byte UTF-8 characters)
        if (i + 2 < text.length()) {
            std::string threeByte = text.substr(i, 3);
            currentChunk += threeByte;
            
            // Check if it's a sentence-ending punctuation
            if (threeByte == u8"。" || threeByte == u8"！" || threeByte == u8"？") {
                chunks.push_back(currentChunk);
                currentChunk.clear();
            }
            i += 3;
        } else {
            // Handle remaining bytes
            currentChunk += text[i];
            i++;
        }
    }
    
    if (!currentChunk.empty()) {
        chunks.push_back(currentChunk);
    }
    
    
    EXPECT_EQ(chunks.size(), 3) << "Expected 3 chunks for 3 sentences";
    EXPECT_EQ(chunks[0], u8"こんにちは。");
    EXPECT_EQ(chunks[1], u8"今日はいい天気ですね。");
    EXPECT_EQ(chunks[2], u8"ありがとう！");
}

TEST(StreamingSimpleTest, EmptyTextProducesNoChunks) {
    std::string text = "";
    std::regex sentenceBoundary("([.!?,;:]+)");
    
    std::vector<std::string> chunks;
    std::sregex_token_iterator iter(text.begin(), text.end(), sentenceBoundary, {-1, 1});
    std::sregex_token_iterator end;
    
    std::string currentChunk;
    for (; iter != end; ++iter) {
        std::string token = *iter;
        if (!token.empty()) {
            chunks.push_back(token);
        }
    }
    
    EXPECT_EQ(chunks.size(), 0) << "Empty text should produce no chunks";
}

TEST(StreamingSimpleTest, SingleSentenceProducesOneChunk) {
    std::string text = "This is a single sentence.";
    std::regex sentenceBoundary("([.!?,;:]+)");
    
    std::vector<std::string> chunks;
    std::sregex_token_iterator iter(text.begin(), text.end(), sentenceBoundary, {-1, 1});
    std::sregex_token_iterator end;
    
    std::string currentChunk;
    for (; iter != end; ++iter) {
        std::string token = *iter;
        if (token.empty()) continue;
        
        if (std::regex_match(token, sentenceBoundary)) {
            currentChunk += token;
            if (token.find_first_of(".!?") != std::string::npos) {
                chunks.push_back(currentChunk);
                currentChunk.clear();
            }
        } else {
            currentChunk += token;
        }
    }
    
    if (!currentChunk.empty()) {
        chunks.push_back(currentChunk);
    }
    
    EXPECT_EQ(chunks.size(), 1) << "Single sentence should produce one chunk";
    EXPECT_EQ(chunks[0], "This is a single sentence.");
}

// Test dynamic chunk size calculation
TEST(StreamingSimpleTest, DynamicChunkSizeCalculation) {
    // Helper function to calculate dynamic chunk size (simplified version)
    auto calculateDynamicChunkSize = [](const std::string& text, size_t baseSize = 50) -> size_t {
        if (text.length() < baseSize * 2) {
            return text.length();
        }
        
        size_t punctCount = 0;
        const std::string punctMarks = u8"。、！？.!?,;:";
        for (size_t i = 0; i < text.length(); ++i) {
            if (punctMarks.find(text[i]) != std::string::npos) {
                punctCount++;
            }
        }
        
        float punctDensity = static_cast<float>(punctCount) / text.length();
        if (punctDensity > 0.05f) {
            return baseSize;
        } else if (punctDensity < 0.02f) {
            return baseSize * 3;
        }
        return baseSize * 2;
    };
    
    // Test short text
    std::string shortText = "Hello world!";
    EXPECT_EQ(calculateDynamicChunkSize(shortText), shortText.length());
    
    // Test high punctuation density (text length is 46, so it returns length)
    std::string highPunctText = "Hello! How are you? I'm fine, thanks. And you?";
    size_t highPunctSize = calculateDynamicChunkSize(highPunctText);
    EXPECT_EQ(highPunctSize, highPunctText.length()) << "Short text should return its length";
    
    // Test low punctuation density with longer text
    std::string lowPunctText = "This is a very long text with minimal punctuation that goes on and on without many stops or breaks in the flow";
    size_t lowPunctSize = calculateDynamicChunkSize(lowPunctText);
    EXPECT_EQ(lowPunctSize, 150) << "Low punctuation density should use 3x base size";
    
    // Test medium punctuation density (text length is 65, so it returns length)
    std::string mediumPunctText = "This is a normal text. It has some punctuation, but not too much.";
    size_t mediumPunctSize = calculateDynamicChunkSize(mediumPunctText);
    EXPECT_EQ(mediumPunctSize, mediumPunctText.length()) << "Short text should return its length";
}

// Test crossfade functionality
TEST(StreamingSimpleTest, CrossfadeAudioChunks) {
    // Helper function for crossfade (simplified version)
    auto crossfadeAudioChunks = [](
        const std::vector<int16_t>& prevChunk,
        const std::vector<int16_t>& newChunk,
        std::vector<int16_t>& output,
        size_t overlapSamples = 4
    ) {
        if (prevChunk.empty() || newChunk.empty() || overlapSamples == 0) {
            output.insert(output.end(), newChunk.begin(), newChunk.end());
            return;
        }
        
        size_t actualOverlap = std::min({overlapSamples, prevChunk.size() / 4, newChunk.size() / 4});
        if (actualOverlap < 2) {
            output.insert(output.end(), newChunk.begin(), newChunk.end());
            return;
        }
        
        if (output.size() >= actualOverlap) {
            output.resize(output.size() - actualOverlap);
        }
        
        for (size_t i = 0; i < actualOverlap; ++i) {
            float fadeOut = 1.0f - (static_cast<float>(i) / actualOverlap);
            float fadeIn = static_cast<float>(i) / actualOverlap;
            
            size_t prevIdx = prevChunk.size() - actualOverlap + i;
            int16_t mixed = static_cast<int16_t>(
                prevChunk[prevIdx] * fadeOut + newChunk[i] * fadeIn
            );
            output.push_back(mixed);
        }
        
        output.insert(output.end(), newChunk.begin() + actualOverlap, newChunk.end());
    };
    
    // Test basic crossfade
    std::vector<int16_t> chunk1 = {100, 200, 300, 400};
    std::vector<int16_t> chunk2 = {500, 600, 700, 800};
    std::vector<int16_t> output;
    
    // First chunk
    output.insert(output.end(), chunk1.begin(), chunk1.end());
    
    // Crossfade second chunk
    // actualOverlap will be min(2, 4/4, 4/4) = 1
    // So overlap is too small (<2), it will just append chunk2
    crossfadeAudioChunks(chunk1, chunk2, output, 2);
    
    // Since actualOverlap=1 < 2, it just appends chunk2
    EXPECT_EQ(output.size(), 8) << "Output should have both chunks appended";
    
    // Test with larger chunks for actual crossfade
    std::vector<int16_t> bigChunk1 = {100, 200, 300, 400, 500, 600, 700, 800};
    std::vector<int16_t> bigChunk2 = {1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700};
    std::vector<int16_t> output3;
    
    output3.insert(output3.end(), bigChunk1.begin(), bigChunk1.end());
    crossfadeAudioChunks(bigChunk1, bigChunk2, output3, 4);
    
    // actualOverlap = min(4, 8/4, 8/4) = 2
    // output3 will be resized by 2, then 2 mixed samples + 6 from bigChunk2
    EXPECT_EQ(output3.size(), 14) << "Output should have correct size with crossfade";
    
    // Test empty chunk handling
    std::vector<int16_t> emptyChunk;
    std::vector<int16_t> output2;
    crossfadeAudioChunks(emptyChunk, chunk1, output2, 2);
    EXPECT_EQ(output2, chunk1) << "Empty previous chunk should just append new chunk";
}