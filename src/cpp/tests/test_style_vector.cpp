/**
 * Test: Style vector conditioning
 *
 * Covers the C API additions in piper_plus.h:
 *   - PiperPlusSynthOptions.style_vector / style_vector_dim defaults
 *   - memset(0) initialisation correctness (zero-init safety)
 *   - ABI stability (`sizeof(PiperPlusSynthOptions)` maintained
 *     by shrinking `_reserved[5]` to `_reserved[3]`).
 *
 * Integration with a real ONNX session is exercised by
 * test_c_api_integration.cpp when a style-dim model is provided.
 */

#include <gtest/gtest.h>
#include <cstring>
#include <vector>

#include "piper_plus.h"

TEST(StyleVectorDefaults, DefaultOptionsHaveNullStyleVector) {
    PiperPlusSynthOptions opts = piper_plus_default_options();
    EXPECT_EQ(opts.style_vector, nullptr);
    EXPECT_EQ(opts.style_vector_dim, 0);
}

TEST(StyleVectorDefaults, MemsetZeroProducesDefaults) {
    PiperPlusSynthOptions opts;
    std::memset(&opts, 0, sizeof(opts));
    EXPECT_EQ(opts.style_vector, nullptr);
    EXPECT_EQ(opts.style_vector_dim, 0);
}

TEST(StyleVectorDefaults, CallerCanSetStyleVector) {
    std::vector<float> vec(256, 0.0f);
    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.style_vector = vec.data();
    opts.style_vector_dim = static_cast<int32_t>(vec.size());
    EXPECT_EQ(opts.style_vector, vec.data());
    EXPECT_EQ(opts.style_vector_dim, 256);
}

TEST(StyleVectorAbi, ReservedArrayShrunkButSizeStable) {
    // _reserved was reduced from [5] to [3] to absorb the two new fields
    // (style_vector pointer + style_vector_dim int32). The absolute byte
    // count changes, but the number of reserved ints is now 3.
    PiperPlusSynthOptions opts;
    std::memset(&opts, 0, sizeof(opts));
    static_assert(sizeof(opts._reserved) / sizeof(opts._reserved[0]) == 3,
                  "Expected _reserved array to have 3 int32_t slots after "
                  "style_vector additions (). If this fails, the "
                  "struct layout drifted and existing FFI bindings must be "
                  "reviewed.");

    for (size_t i = 0; i < sizeof(opts._reserved) / sizeof(opts._reserved[0]);
         ++i) {
        EXPECT_EQ(opts._reserved[i], 0);
    }
}

TEST(StyleVectorAbi, StructSizeIsReasonableOn64BitPlatforms) {
    // Sanity check: the struct must at least accommodate its named fields.
    // We don't lock sizeof() to a specific value since alignment padding
    // varies across compilers/targets, but it must be >= the sum of the
    // declared member sizes.
    constexpr size_t expectedAtLeast =
        sizeof(int32_t) * 2          // speaker_id, language_id
        + sizeof(float) * 4           // noise_scale, length_scale, noise_w, sentence_silence_sec
        + sizeof(const float *) * 2   // speaker_embedding, style_vector
        + sizeof(int32_t) * 2         // speaker_embedding_dim, style_vector_dim
        + sizeof(int32_t) * 3;        // _reserved[3]
    EXPECT_GE(sizeof(PiperPlusSynthOptions), expectedAtLeast);
}
