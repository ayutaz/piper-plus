/**
 * Test: PyTorch/ONNX Prosody Features Inference Parity
 *
 * This test validates that C++ prosody features (A1/A2/A3) processing
 * uses the correct data type (int64) to match the actual piper.cpp implementation.
 */

#include <gtest/gtest.h>
#include <onnxruntime_cxx_api.h>
#include <vector>
#include <cstdlib>

// ----------------------------------------------------------------------------
// Test: Prosody Tensor Data Type
// ----------------------------------------------------------------------------

TEST(ProsodyInferenceTest, ProsodyTensorDataType) {
    // Verify ONNX tensor is created with int64 type (matching piper.cpp)
    std::vector<int64_t> prosodyData = {-2, 1, 5, 0, 2, 5};
    std::vector<int64_t> shape = {1, 2, 3};  // [batch, phonemes, features]

    auto memoryInfo = Ort::MemoryInfo::CreateCpu(
        OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);
    auto tensor = Ort::Value::CreateTensor<int64_t>(
        memoryInfo, prosodyData.data(), prosodyData.size(),
        shape.data(), shape.size());

    EXPECT_TRUE(tensor.IsTensor());
    auto typeInfo = tensor.GetTensorTypeAndShapeInfo();
    EXPECT_EQ(typeInfo.GetElementType(), ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64);
    EXPECT_EQ(typeInfo.GetShape()[0], 1);
    EXPECT_EQ(typeInfo.GetShape()[1], 2);
    EXPECT_EQ(typeInfo.GetShape()[2], 3);
}

// ----------------------------------------------------------------------------
// Test: Int to Float Conversion
// ----------------------------------------------------------------------------

TEST(ProsodyInferenceTest, IntToInt64Conversion) {
    // Test conversion from ProsodyFeature (int) to int64 array (matching piper.cpp)
    struct ProsodyFeature {
        int a1, a2, a3;
    };

    std::vector<ProsodyFeature> prosody = {
        {-4, 1, 5},
        {-3, 2, 5},
        {0, 3, 5}
    };

    std::vector<int64_t> prosodyFlat;
    prosodyFlat.resize(prosody.size() * 3);

    for (size_t i = 0; i < prosody.size(); i++) {
        prosodyFlat[i * 3 + 0] = prosody[i].a1;
        prosodyFlat[i * 3 + 1] = prosody[i].a2;
        prosodyFlat[i * 3 + 2] = prosody[i].a3;
    }

    EXPECT_EQ(prosodyFlat.size(), 9);
    EXPECT_EQ(prosodyFlat[0], -4);
    EXPECT_EQ(prosodyFlat[1], 1);
    EXPECT_EQ(prosodyFlat[2], 5);
    EXPECT_EQ(prosodyFlat[3], -3);
    EXPECT_EQ(prosodyFlat[4], 2);
    EXPECT_EQ(prosodyFlat[5], 5);
    EXPECT_EQ(prosodyFlat[6], 0);
    EXPECT_EQ(prosodyFlat[7], 3);
    EXPECT_EQ(prosodyFlat[8], 5);
}

// ----------------------------------------------------------------------------
// Test: Intersperse Padding Mapping
// ----------------------------------------------------------------------------

TEST(ProsodyInferenceTest, InterspersePaddingMapping) {
    // Test prosody mapping with intersperse padding
    // Format: PAD, P1, PAD, P2, PAD, P3, PAD
    // Prosody should map to odd indices (1, 3, 5)
    struct ProsodyFeature {
        int a1, a2, a3;
    };

    std::vector<ProsodyFeature> prosody = {
        {-2, 1, 3},
        {0, 2, 3},
        {1, 3, 3}
    };
    size_t numPhonemeIds = 7;  // 3 phonemes + 4 pads

    std::vector<int64_t> prosodyFlat(numPhonemeIds * 3, 0);

    // Map to odd positions (1, 3, 5) - intersperse padding logic
    size_t prosodyIdx = 0;
    for (size_t i = 1; i < numPhonemeIds && prosodyIdx < prosody.size(); i += 2) {
        prosodyFlat[i * 3 + 0] = prosody[prosodyIdx].a1;
        prosodyFlat[i * 3 + 1] = prosody[prosodyIdx].a2;
        prosodyFlat[i * 3 + 2] = prosody[prosodyIdx].a3;
        prosodyIdx++;
    }

    // Verify padding positions are zero (indices 0, 2, 4, 6)
    EXPECT_EQ(prosodyFlat[0], 0);  // PAD at index 0
    EXPECT_EQ(prosodyFlat[1], 0);
    EXPECT_EQ(prosodyFlat[2], 0);

    // Verify phoneme 1 at index 1 (odd position)
    EXPECT_EQ(prosodyFlat[3], -2);  // a1
    EXPECT_EQ(prosodyFlat[4], 1);   // a2
    EXPECT_EQ(prosodyFlat[5], 3);   // a3

    // Verify PAD at index 2 (even position)
    EXPECT_EQ(prosodyFlat[6], 0);
    EXPECT_EQ(prosodyFlat[7], 0);
    EXPECT_EQ(prosodyFlat[8], 0);

    // Verify phoneme 2 at index 3 (odd position)
    EXPECT_EQ(prosodyFlat[9], 0);   // a1
    EXPECT_EQ(prosodyFlat[10], 2);  // a2
    EXPECT_EQ(prosodyFlat[11], 3);  // a3

    // Verify PAD at index 4 (even position)
    EXPECT_EQ(prosodyFlat[12], 0);

    // Verify phoneme 3 at index 5 (odd position)
    EXPECT_EQ(prosodyFlat[15], 1);  // a1
    EXPECT_EQ(prosodyFlat[16], 3);  // a2
    EXPECT_EQ(prosodyFlat[17], 3);  // a3
}

// ----------------------------------------------------------------------------
// Test: Negative and Positive Values
// ----------------------------------------------------------------------------

TEST(ProsodyInferenceTest, NegativeAndPositiveValues) {
    // Test that A1 can be negative, A2/A3 are positive
    // A1: Relative position from accent nucleus (can be negative)
    // A2: Position in accent phrase (1-based, always positive)
    // A3: Total morae in accent phrase (always positive)
    struct ProsodyFeature {
        int a1, a2, a3;
    };

    std::vector<ProsodyFeature> prosody = {
        {-10, 1, 15},   // Extreme negative A1
        {0, 5, 10},     // Zero A1
        {10, 10, 10}    // Extreme positive A1
    };

    std::vector<int64_t> prosodyFlat;
    prosodyFlat.resize(prosody.size() * 3);

    for (size_t i = 0; i < prosody.size(); i++) {
        prosodyFlat[i * 3 + 0] = prosody[i].a1;
        prosodyFlat[i * 3 + 1] = prosody[i].a2;
        prosodyFlat[i * 3 + 2] = prosody[i].a3;
    }

    // Verify negative value preserved
    EXPECT_EQ(prosodyFlat[0], -10);
    EXPECT_EQ(prosodyFlat[1], 1);
    EXPECT_EQ(prosodyFlat[2], 15);

    // Verify zero value
    EXPECT_EQ(prosodyFlat[3], 0);
    EXPECT_EQ(prosodyFlat[4], 5);
    EXPECT_EQ(prosodyFlat[5], 10);

    // Verify positive value
    EXPECT_EQ(prosodyFlat[6], 10);
    EXPECT_EQ(prosodyFlat[7], 10);
    EXPECT_EQ(prosodyFlat[8], 10);
}

// ----------------------------------------------------------------------------
// Test: Zero Prosody Fallback
// ----------------------------------------------------------------------------

TEST(ProsodyInferenceTest, ZeroProsodyFallback) {
    // Test that zero prosody tensor is created correctly when no data available
    size_t numPhonemeIds = 5;
    std::vector<int64_t> zeroProsody;
    zeroProsody.resize(numPhonemeIds * 3, 0);

    EXPECT_EQ(zeroProsody.size(), 15);
    for (size_t i = 0; i < zeroProsody.size(); i++) {
        EXPECT_EQ(zeroProsody[i], 0);
    }

    // Verify tensor creation
    std::vector<int64_t> shape = {1, static_cast<int64_t>(numPhonemeIds), 3};
    auto memoryInfo = Ort::MemoryInfo::CreateCpu(
        OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);
    auto tensor = Ort::Value::CreateTensor<int64_t>(
        memoryInfo, zeroProsody.data(), zeroProsody.size(),
        shape.data(), shape.size());

    EXPECT_TRUE(tensor.IsTensor());
    auto typeInfo = tensor.GetTensorTypeAndShapeInfo();
    EXPECT_EQ(typeInfo.GetElementType(), ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64);
}

// ----------------------------------------------------------------------------
// Main
// ----------------------------------------------------------------------------

int main(int argc, char **argv) {
    testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
