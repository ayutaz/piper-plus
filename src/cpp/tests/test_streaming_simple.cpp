#include <gtest/gtest.h>
#include <vector>
#include <string>
#include <regex>
#include <algorithm>
#include <cstdint>

#include "utf8_utils.hpp"

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

// Test dynamic chunk size calculation (codepoint-based, mirrors piper.cpp)
TEST(StreamingSimpleTest, DynamicChunkSizeCalculation) {
    // Codepoint-level helper that mirrors the fixed calculateDynamicChunkSize
    // in piper.cpp (Issue #343: byte-level was broken for CJK text).
    using piper::utf8_util::toCodepoints;
    auto isPunctCodepoint = [](char32_t c) -> bool {
        switch (c) {
            case U'\u3002': case U'\u3001': case U'\uFF01': case U'\uFF1F':
            case U'.': case U'!': case U'?': case U',': case U';': case U':':
                return true;
            default: return false;
        }
    };
    auto calculateDynamicChunkSize = [&](const std::string& text, size_t baseSize = 50) -> size_t {
        auto cps = toCodepoints(text);
        size_t cpLen = cps.size();
        if (cpLen < baseSize * 2) return cpLen;
        size_t punctCount = 0;
        for (char32_t c : cps) { if (isPunctCodepoint(c)) punctCount++; }
        float punctDensity = static_cast<float>(punctCount) / static_cast<float>(cpLen);
        if (punctDensity > 0.05f) return baseSize;
        if (punctDensity < 0.02f) return baseSize * 3;
        return baseSize * 2;
    };

    // Test short ASCII text (12 codepoints < 100)
    std::string shortText = "Hello world!";
    EXPECT_EQ(calculateDynamicChunkSize(shortText), 12u);

    // Test short ASCII text with punctuation (46 codepoints < 100)
    std::string highPunctText = "Hello! How are you? I'm fine, thanks. And you?";
    size_t highPunctSize = calculateDynamicChunkSize(highPunctText);
    EXPECT_EQ(highPunctSize, 46u) << "Short text should return codepoint count";

    // Test low punctuation density with longer text
    std::string lowPunctText = "This is a very long text with minimal punctuation that goes on and on without many stops or breaks in the flow";
    size_t lowPunctSize = calculateDynamicChunkSize(lowPunctText);
    EXPECT_EQ(lowPunctSize, 150u) << "Low punctuation density should use 3x base size";

    // Test Japanese text: codepoint count should be used, not byte count
    // "こんにちは。今日はいい天気ですね。" = 17 codepoints (< 100), should return 17
    std::string jaText = u8"こんにちは。今日はいい天気ですね。";
    auto jaCps = toCodepoints(jaText);
    EXPECT_EQ(jaCps.size(), 17u) << "Japanese text should have 17 codepoints";
    size_t jaSize = calculateDynamicChunkSize(jaText);
    EXPECT_EQ(jaSize, 17u) << "Short CJK text should return codepoint count, not byte count";
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

// ===== M5-3: Iterator crossfade unit tests (float-based) =====
//
// These tests verify the crossfade math used in synth_next.
// The Iterator uses float samples (textToAudioFloat), so crossfade
// operates on float rather than int16_t.
//
// NOTE: Unit tests use TEST_CROSSFADE_SAMPLES=4 for logic verification.
// The production value CROSSFADE_SAMPLES=220 (10ms @ 22050Hz) is validated
// in integration tests (test_c_api_integration.cpp: IteratorCrossfade*).

// Simulate the Iterator crossfade logic extracted from synth_next.
// This mirrors the exact algorithm in piper_plus_c_api.cpp.
namespace {

// Small value for unit testing -- keeps expected values hand-computable.
// Production code uses CROSSFADE_SAMPLES = 220 (10ms @ 22050Hz).
static constexpr size_t TEST_CROSSFADE_SAMPLES = 4;

/// Apply crossfade between prevTail and the beginning of currentChunk.
/// Save tail of currentChunk into prevTail for next iteration.
/// On the last chunk, flush prevTail into output.
void applyIteratorCrossfade(
    std::vector<float> &prevTail,
    std::vector<float> &currentChunk,
    bool isLast)
{
    // Step 1: crossfade prevTail with beginning of currentChunk
    if (!prevTail.empty() && currentChunk.size() >= TEST_CROSSFADE_SAMPLES) {
        for (size_t i = 0; i < TEST_CROSSFADE_SAMPLES; ++i) {
            float alpha = static_cast<float>(i) / TEST_CROSSFADE_SAMPLES;
            currentChunk[i] = prevTail[i] * (1.0f - alpha)
                            + currentChunk[i] * alpha;
        }
        prevTail.clear();
    }

    // Step 2: save tail / flush depending on last-chunk status
    if (!isLast) {
        if (currentChunk.size() >= TEST_CROSSFADE_SAMPLES) {
            prevTail.assign(
                currentChunk.end() - static_cast<std::ptrdiff_t>(TEST_CROSSFADE_SAMPLES),
                currentChunk.end());
            currentChunk.resize(currentChunk.size() - TEST_CROSSFADE_SAMPLES);
        } else {
            prevTail.clear();
        }
    } else {
        if (!prevTail.empty()) {
            currentChunk.insert(currentChunk.begin(),
                                prevTail.begin(), prevTail.end());
            prevTail.clear();
        }
    }
}

} // anonymous namespace

TEST(IteratorCrossfadeTest, LinearCrossfadeTwoChunks) {
    // Chunk A: [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    // Chunk B: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    // CROSSFADE_SAMPLES = 4
    //
    // After processing chunk A (not last):
    //   prevTail = [1.0, 1.0, 1.0, 1.0] (last 4 of A)
    //   output A = [1.0, 1.0, 1.0, 1.0] (trimmed)
    //
    // After processing chunk B (last):
    //   crossfade region: prevTail * (1-alpha) + B * alpha
    //     i=0: 1.0*(1-0/4) + 0.0*(0/4) = 1.0
    //     i=1: 1.0*(1-1/4) + 0.0*(1/4) = 0.75
    //     i=2: 1.0*(1-2/4) + 0.0*(2/4) = 0.5
    //     i=3: 1.0*(1-3/4) + 0.0*(3/4) = 0.25
    //   output B = [1.0, 0.75, 0.5, 0.25, 0.0, 0.0, 0.0, 0.0]

    std::vector<float> chunkA(8, 1.0f);
    std::vector<float> chunkB(8, 0.0f);
    std::vector<float> prevTail;

    // Process chunk A (not last)
    applyIteratorCrossfade(prevTail, chunkA, /*isLast=*/false);
    ASSERT_EQ(prevTail.size(), TEST_CROSSFADE_SAMPLES);
    EXPECT_EQ(chunkA.size(), 4u);  // trimmed
    for (float v : chunkA) EXPECT_FLOAT_EQ(v, 1.0f);

    // Process chunk B (last)
    applyIteratorCrossfade(prevTail, chunkB, /*isLast=*/true);
    EXPECT_TRUE(prevTail.empty());
    ASSERT_EQ(chunkB.size(), 8u);

    // Verify crossfade region
    EXPECT_FLOAT_EQ(chunkB[0], 1.0f);    // alpha=0/4
    EXPECT_FLOAT_EQ(chunkB[1], 0.75f);   // alpha=1/4
    EXPECT_FLOAT_EQ(chunkB[2], 0.5f);    // alpha=2/4
    EXPECT_FLOAT_EQ(chunkB[3], 0.25f);   // alpha=3/4
    // Rest unchanged
    for (size_t i = 4; i < 8; ++i) {
        EXPECT_FLOAT_EQ(chunkB[i], 0.0f);
    }
}

TEST(IteratorCrossfadeTest, ThreeChunksIntermediateCrossfade) {
    // Verify crossfade works across 3 chunks:
    // A=[1,1,1,1,1,1,1,1], B=[0.5,...], C=[0,...] with CROSSFADE_SAMPLES=4

    std::vector<float> chunkA(8, 1.0f);
    std::vector<float> chunkB(8, 0.5f);
    std::vector<float> chunkC(8, 0.0f);
    std::vector<float> prevTail;

    // Chunk A (not last)
    applyIteratorCrossfade(prevTail, chunkA, false);
    EXPECT_EQ(chunkA.size(), 4u);
    EXPECT_EQ(prevTail.size(), TEST_CROSSFADE_SAMPLES);

    // Chunk B (not last) -- crossfade A's tail with B's head
    applyIteratorCrossfade(prevTail, chunkB, false);
    EXPECT_EQ(chunkB.size(), 4u);
    // B's crossfaded head: prevTail[i]*(1-alpha) + 0.5*alpha
    // prevTail was [1,1,1,1]
    // i=0: 1*(1) + 0.5*(0) = 1.0
    // i=1: 1*(0.75) + 0.5*(0.25) = 0.875
    // i=2: 1*(0.5) + 0.5*(0.5) = 0.75
    // i=3: 1*(0.25) + 0.5*(0.75) = 0.625
    // Then B is trimmed to first 4 (the 4 crossfaded values)
    EXPECT_FLOAT_EQ(chunkB[0], 1.0f);
    EXPECT_FLOAT_EQ(chunkB[1], 0.875f);
    EXPECT_FLOAT_EQ(chunkB[2], 0.75f);
    EXPECT_FLOAT_EQ(chunkB[3], 0.625f);
    EXPECT_EQ(prevTail.size(), TEST_CROSSFADE_SAMPLES);

    // Chunk C (last) -- crossfade B's tail with C's head
    // prevTail was saved from B: [0.5, 0.5, 0.5, 0.5]
    applyIteratorCrossfade(prevTail, chunkC, true);
    EXPECT_TRUE(prevTail.empty());
    ASSERT_EQ(chunkC.size(), 8u);
    // crossfade: 0.5*(1-alpha) + 0.0*alpha = 0.5*(1-alpha)
    EXPECT_FLOAT_EQ(chunkC[0], 0.5f);
    EXPECT_FLOAT_EQ(chunkC[1], 0.375f);
    EXPECT_FLOAT_EQ(chunkC[2], 0.25f);
    EXPECT_FLOAT_EQ(chunkC[3], 0.125f);
    for (size_t i = 4; i < 8; ++i) {
        EXPECT_FLOAT_EQ(chunkC[i], 0.0f);
    }
}

TEST(IteratorCrossfadeTest, ShortChunkSkipsCrossfade) {
    // When the current chunk is shorter than CROSSFADE_SAMPLES,
    // crossfade should be skipped and prevTail preserved for the last chunk.

    std::vector<float> chunkA(8, 1.0f);
    std::vector<float> chunkB = {0.5f, 0.5f};  // only 2 samples
    std::vector<float> prevTail;

    // Chunk A (not last)
    applyIteratorCrossfade(prevTail, chunkA, false);
    EXPECT_EQ(prevTail.size(), TEST_CROSSFADE_SAMPLES);

    // Chunk B (last, but too short for crossfade)
    // Since chunkB.size() < CROSSFADE_SAMPLES, crossfade is skipped.
    // prevTail is prepended to output.
    applyIteratorCrossfade(prevTail, chunkB, true);
    EXPECT_TRUE(prevTail.empty());
    EXPECT_EQ(chunkB.size(), 6u);  // 4 (prevTail) + 2 (original)
    // First 4 are prevTail values
    EXPECT_FLOAT_EQ(chunkB[0], 1.0f);
    EXPECT_FLOAT_EQ(chunkB[1], 1.0f);
    EXPECT_FLOAT_EQ(chunkB[2], 1.0f);
    EXPECT_FLOAT_EQ(chunkB[3], 1.0f);
    // Last 2 are original chunk B
    EXPECT_FLOAT_EQ(chunkB[4], 0.5f);
    EXPECT_FLOAT_EQ(chunkB[5], 0.5f);
}

TEST(IteratorCrossfadeTest, SingleChunkNoCrossfade) {
    // With only one chunk (isLast=true on first call), no crossfade occurs
    // and no samples are trimmed.

    std::vector<float> chunk = {0.1f, 0.2f, 0.3f, 0.4f, 0.5f, 0.6f, 0.7f, 0.8f};
    std::vector<float> original = chunk;  // copy for comparison
    std::vector<float> prevTail;

    applyIteratorCrossfade(prevTail, chunk, /*isLast=*/true);
    EXPECT_TRUE(prevTail.empty());
    EXPECT_EQ(chunk, original);  // unchanged
}

TEST(IteratorCrossfadeTest, TotalSamplesPreserved) {
    // The total number of samples across all output chunks should equal
    // the sum of input chunk sizes minus CROSSFADE_SAMPLES per boundary
    // (since crossfade overlaps CROSSFADE_SAMPLES at each junction).

    std::vector<float> chunkA(100, 0.8f);
    std::vector<float> chunkB(100, 0.4f);
    std::vector<float> chunkC(100, 0.2f);
    std::vector<float> prevTail;

    size_t totalInput = chunkA.size() + chunkB.size() + chunkC.size();  // 300

    applyIteratorCrossfade(prevTail, chunkA, false);
    size_t outA = chunkA.size();

    applyIteratorCrossfade(prevTail, chunkB, false);
    size_t outB = chunkB.size();

    applyIteratorCrossfade(prevTail, chunkC, true);
    size_t outC = chunkC.size();

    size_t totalOutput = outA + outB + outC;
    // Non-last chunks trim CROSSFADE_SAMPLES from their tail (saved for crossfade).
    // Last chunk keeps its full length.
    // totalInput = 300
    // outA = 100 - 4 = 96  (first chunk, tail trimmed and saved)
    // outB = 100 - 4 = 96  (middle chunk, crossfade applied, new tail saved)
    // outC = 100            (last chunk, no trim)
    // total = 96 + 96 + 100 = 292 = 300 - 2*4
    EXPECT_EQ(totalOutput, totalInput - 2 * TEST_CROSSFADE_SAMPLES);
}
