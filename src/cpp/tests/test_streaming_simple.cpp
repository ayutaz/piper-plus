#include <gtest/gtest.h>
#include <vector>
#include <string>
#include <regex>

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
    
    // Skip the regex-based implementation
    /*std::regex sentenceBoundary(u8"([。！？、]+)");
    */ // End of skipped regex implementation
    
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