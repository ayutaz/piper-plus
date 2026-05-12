/**
 * Test: Model Speaker Detection
 *
 * Tests for single-speaker and multi-speaker model input handling.
 * Verifies that "sid" input is only added for multi-speaker models.
 */

#include <gtest/gtest.h>
#include <vector>
#include <string>
#include <algorithm>

// Simulate the ModelSession flags from piper.hpp
struct TestModelSession {
    bool hasDurationOutput = false;
    bool hasProsodyInput = false;
    bool hasMultiSpeaker = false;
    // Issue #426: MB-iSTFT-VITS2 + Voice Cloning exports declare these
    // unconditionally; runtimes feed zero+mask=0 to fall back to emb_g(sid).
    bool hasSpeakerEmbeddingInput = false;
    int64_t speakerEmbeddingDim = 256;
};

// Helper function that mirrors the input name building logic from piper.cpp
std::vector<const char*> buildInputNames(const TestModelSession& session) {
    std::vector<const char *> inputNamesVec = {"input", "input_lengths", "scales"};

    // Add speaker id only for multi-speaker models
    if (session.hasMultiSpeaker) {
        inputNamesVec.push_back("sid");
    }

    // Add prosody features if model supports them
    if (session.hasProsodyInput) {
        inputNamesVec.push_back("prosody_features");
    }

    // Add speaker_embedding / mask when declared (Issue #426).
    if (session.hasSpeakerEmbeddingInput) {
        inputNamesVec.push_back("speaker_embedding");
        inputNamesVec.push_back("speaker_embedding_mask");
    }

    return inputNamesVec;
}

// Helper to check if a vector contains a specific value
bool containsInput(const std::vector<const char*>& inputs, const char* name) {
    return std::find_if(inputs.begin(), inputs.end(),
        [name](const char* s) { return std::string(s) == name; }) != inputs.end();
}

// ----------------------------------------------------------------------------
// Test: Single Speaker Model Input Names
// ----------------------------------------------------------------------------

TEST(ModelSpeakerDetectionTest, SingleSpeakerInputNames) {
    TestModelSession session;
    session.hasMultiSpeaker = false;
    session.hasProsodyInput = false;

    auto inputs = buildInputNames(session);

    // Should have exactly 3 inputs: input, input_lengths, scales
    EXPECT_EQ(inputs.size(), 3);

    // Verify required inputs are present
    EXPECT_TRUE(containsInput(inputs, "input"));
    EXPECT_TRUE(containsInput(inputs, "input_lengths"));
    EXPECT_TRUE(containsInput(inputs, "scales"));

    // sid should NOT be present for single-speaker models
    EXPECT_FALSE(containsInput(inputs, "sid"));

    // prosody_features should NOT be present when not enabled
    EXPECT_FALSE(containsInput(inputs, "prosody_features"));
}

// ----------------------------------------------------------------------------
// Test: Multi Speaker Model Input Names
// ----------------------------------------------------------------------------

TEST(ModelSpeakerDetectionTest, MultiSpeakerInputNames) {
    TestModelSession session;
    session.hasMultiSpeaker = true;
    session.hasProsodyInput = false;

    auto inputs = buildInputNames(session);

    // Should have 4 inputs: input, input_lengths, scales, sid
    EXPECT_EQ(inputs.size(), 4);

    // Verify required inputs are present
    EXPECT_TRUE(containsInput(inputs, "input"));
    EXPECT_TRUE(containsInput(inputs, "input_lengths"));
    EXPECT_TRUE(containsInput(inputs, "scales"));

    // sid SHOULD be present for multi-speaker models
    EXPECT_TRUE(containsInput(inputs, "sid"));

    // prosody_features should NOT be present when not enabled
    EXPECT_FALSE(containsInput(inputs, "prosody_features"));
}

// ----------------------------------------------------------------------------
// Test: Single Speaker with Prosody
// ----------------------------------------------------------------------------

TEST(ModelSpeakerDetectionTest, SingleSpeakerWithProsody) {
    TestModelSession session;
    session.hasMultiSpeaker = false;
    session.hasProsodyInput = true;

    auto inputs = buildInputNames(session);

    // Should have 4 inputs: input, input_lengths, scales, prosody_features
    EXPECT_EQ(inputs.size(), 4);

    // Verify required inputs are present
    EXPECT_TRUE(containsInput(inputs, "input"));
    EXPECT_TRUE(containsInput(inputs, "input_lengths"));
    EXPECT_TRUE(containsInput(inputs, "scales"));

    // sid should NOT be present for single-speaker models
    EXPECT_FALSE(containsInput(inputs, "sid"));

    // prosody_features SHOULD be present when enabled
    EXPECT_TRUE(containsInput(inputs, "prosody_features"));
}

// ----------------------------------------------------------------------------
// Test: Multi Speaker with Prosody
// ----------------------------------------------------------------------------

TEST(ModelSpeakerDetectionTest, MultiSpeakerWithProsody) {
    TestModelSession session;
    session.hasMultiSpeaker = true;
    session.hasProsodyInput = true;

    auto inputs = buildInputNames(session);

    // Should have 5 inputs: input, input_lengths, scales, sid, prosody_features
    EXPECT_EQ(inputs.size(), 5);

    // Verify all inputs are present
    EXPECT_TRUE(containsInput(inputs, "input"));
    EXPECT_TRUE(containsInput(inputs, "input_lengths"));
    EXPECT_TRUE(containsInput(inputs, "scales"));
    EXPECT_TRUE(containsInput(inputs, "sid"));
    EXPECT_TRUE(containsInput(inputs, "prosody_features"));
}

// ----------------------------------------------------------------------------
// Test: Input Order (sid before prosody_features)
// ----------------------------------------------------------------------------

TEST(ModelSpeakerDetectionTest, InputOrderSidBeforeProsody) {
    TestModelSession session;
    session.hasMultiSpeaker = true;
    session.hasProsodyInput = true;

    auto inputs = buildInputNames(session);

    // Find positions of sid and prosody_features
    int sidPos = -1, prosodyPos = -1;
    for (size_t i = 0; i < inputs.size(); i++) {
        if (std::string(inputs[i]) == "sid") sidPos = i;
        if (std::string(inputs[i]) == "prosody_features") prosodyPos = i;
    }

    // Both should be found
    EXPECT_NE(sidPos, -1);
    EXPECT_NE(prosodyPos, -1);

    // sid should come before prosody_features (matches ONNX model input order)
    EXPECT_LT(sidPos, prosodyPos);
}

// ----------------------------------------------------------------------------
// Test: Base Inputs Always Present
// ----------------------------------------------------------------------------

TEST(ModelSpeakerDetectionTest, BaseInputsAlwaysPresent) {
    // Test all combinations
    std::vector<std::pair<bool, bool>> combinations = {
        {false, false},  // single, no prosody
        {false, true},   // single, with prosody
        {true, false},   // multi, no prosody
        {true, true}     // multi, with prosody
    };

    for (const auto& combo : combinations) {
        TestModelSession session;
        session.hasMultiSpeaker = combo.first;
        session.hasProsodyInput = combo.second;

        auto inputs = buildInputNames(session);

        // Base inputs should always be present
        EXPECT_TRUE(containsInput(inputs, "input"))
            << "input missing for hasMultiSpeaker=" << combo.first
            << ", hasProsodyInput=" << combo.second;
        EXPECT_TRUE(containsInput(inputs, "input_lengths"))
            << "input_lengths missing for hasMultiSpeaker=" << combo.first
            << ", hasProsodyInput=" << combo.second;
        EXPECT_TRUE(containsInput(inputs, "scales"))
            << "scales missing for hasMultiSpeaker=" << combo.first
            << ", hasProsodyInput=" << combo.second;
    }
}

// ============================================================================
// Issue #426: speaker_embedding / speaker_embedding_mask feed contract
// ============================================================================
//
// PR #320 made MB-iSTFT-VITS2 + Voice Cloning exports declare these inputs
// unconditionally; without feeding them ORT raises "Required inputs
// missing". The canonical fallback is zero embedding + mask=0 to route
// through emb_g(sid) (vits/models.py:1015-1037).

TEST(ModelSpeakerDetectionTest, SpeakerEmbeddingAddedWhenDeclared) {
    TestModelSession session;
    session.hasMultiSpeaker = true;
    session.hasSpeakerEmbeddingInput = true;

    auto inputs = buildInputNames(session);
    EXPECT_TRUE(containsInput(inputs, "speaker_embedding"));
    EXPECT_TRUE(containsInput(inputs, "speaker_embedding_mask"));
}

TEST(ModelSpeakerDetectionTest, SpeakerEmbeddingAbsentByDefault) {
    TestModelSession session;
    // hasSpeakerEmbeddingInput defaults to false — legacy non-MB-iSTFT
    // exports must NOT receive these inputs (ORT would reject them).
    auto inputs = buildInputNames(session);
    EXPECT_FALSE(containsInput(inputs, "speaker_embedding"));
    EXPECT_FALSE(containsInput(inputs, "speaker_embedding_mask"));
}

TEST(ModelSpeakerDetectionTest, SpeakerEmbeddingOrderAfterProsody) {
    // ONNX feed order: input, input_lengths, scales, sid, prosody_features,
    // speaker_embedding, speaker_embedding_mask. The export side
    // (export_onnx.py:505-515) appends them last; matching the runtime
    // order keeps debugging output predictable.
    TestModelSession session;
    session.hasMultiSpeaker = true;
    session.hasProsodyInput = true;
    session.hasSpeakerEmbeddingInput = true;

    auto inputs = buildInputNames(session);
    int prosodyPos = -1, embPos = -1, maskPos = -1;
    for (size_t i = 0; i < inputs.size(); i++) {
        if (std::string(inputs[i]) == "prosody_features") prosodyPos = static_cast<int>(i);
        if (std::string(inputs[i]) == "speaker_embedding") embPos = static_cast<int>(i);
        if (std::string(inputs[i]) == "speaker_embedding_mask") maskPos = static_cast<int>(i);
    }
    EXPECT_NE(prosodyPos, -1);
    EXPECT_NE(embPos, -1);
    EXPECT_NE(maskPos, -1);
    EXPECT_LT(prosodyPos, embPos);
    EXPECT_LT(embPos, maskPos);
}

TEST(ModelSpeakerDetectionTest, SpeakerEmbeddingDefaultDim256) {
    // ECAPA-TDNN canonical fallback when the ONNX graph uses a dynamic
    // axis for emb_dim. Mirrors src/python_run/piper/voice.py:200-208 and
    // docker/python-inference/inference.py.
    TestModelSession session;
    EXPECT_EQ(session.speakerEmbeddingDim, 256);
}

// ----------------------------------------------------------------------------
// Main
// ----------------------------------------------------------------------------

int main(int argc, char **argv) {
    testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
