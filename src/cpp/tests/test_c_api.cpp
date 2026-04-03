/**
 * Test: C API (piper_plus.h)
 *
 * TDD Red Phase -- tests written BEFORE the implementation (piper_plus_c_api.cpp).
 * Tests exercise the public C API surface declared in piper_plus.h.
 *
 * Categories:
 *   - CApiVersion:      version query functions
 *   - CApiDefaultOptions: default synthesis options
 *   - CApiNullSafety:   NULL pointer robustness (must never crash)
 *   - CApiQueryNull:    query functions with NULL engine handle
 *   - CApiCreateError:  engine creation with invalid paths
 *   - CApiErrorMessage: error message availability after failure
 *   - CApiStatusCodes:  status code constants sanity
 *   - CApiConfigStruct: struct layout / memset safety
 */

#include <gtest/gtest.h>
#include <cstring>
#include <set>
#include "piper_plus.h"

// ===== Version tests =====

TEST(CApiVersion, VersionReturnsNonNull) {
    const char* ver = piper_plus_version();
    ASSERT_NE(ver, nullptr);
    EXPECT_GT(strlen(ver), 0u);
}

TEST(CApiVersion, VersionContainsDot) {
    const char* ver = piper_plus_version();
    EXPECT_NE(strchr(ver, '.'), nullptr);
}

TEST(CApiVersion, ApiVersionMatchesConstant) {
    EXPECT_EQ(piper_plus_api_version(), PIPER_PLUS_API_VERSION);
}

// ===== Default options tests =====

TEST(CApiDefaultOptions, HasExpectedDefaults) {
    PiperPlusSynthOptions opts = piper_plus_default_options();
    EXPECT_EQ(opts.speaker_id, 0);
    EXPECT_EQ(opts.language_id, -1);
    EXPECT_FLOAT_EQ(opts.noise_scale, 0.667f);
    EXPECT_FLOAT_EQ(opts.length_scale, 1.0f);
    EXPECT_FLOAT_EQ(opts.noise_w, 0.8f);
    EXPECT_FLOAT_EQ(opts.sentence_silence_sec, 0.2f);
}

TEST(CApiDefaultOptions, ReservedFieldsAreZero) {
    PiperPlusSynthOptions opts = piper_plus_default_options();
    for (int i = 0; i < 8; i++) {
        EXPECT_EQ(opts._reserved[i], 0);
    }
}

// ===== NULL safety tests =====

TEST(CApiNullSafety, CreateWithNullConfig) {
    PiperPlusEngine* engine = piper_plus_create(nullptr);
    EXPECT_EQ(engine, nullptr);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiNullSafety, CreateWithNullModelPath) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = nullptr;
    PiperPlusEngine* engine = piper_plus_create(&config);
    EXPECT_EQ(engine, nullptr);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiNullSafety, SynthesizeWithNullEngine) {
    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;
    int32_t status = piper_plus_synthesize(
        nullptr, "hello", nullptr, &samples, &num_samples, &sample_rate);
    EXPECT_LT(status, 0);
}

TEST(CApiNullSafety, SynthesizeWithNullText) {
    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;
    int32_t status = piper_plus_synthesize(
        nullptr, nullptr, nullptr, &samples, &num_samples, &sample_rate);
    EXPECT_LT(status, 0);
}

TEST(CApiNullSafety, SynthesizeWithNullOutputParams) {
    int32_t status = piper_plus_synthesize(
        nullptr, "hello", nullptr, nullptr, nullptr, nullptr);
    EXPECT_LT(status, 0);
}

TEST(CApiNullSafety, FreeNullEngine) {
    piper_plus_free(nullptr);  // Must not crash
}

TEST(CApiNullSafety, FreeAudioNull) {
    piper_plus_free_audio(nullptr);  // Must not crash
}

// ===== Query functions with NULL engine =====

TEST(CApiQueryNull, SampleRateReturnsZero) {
    EXPECT_EQ(piper_plus_sample_rate(nullptr), 0);
}

TEST(CApiQueryNull, NumSpeakersReturnsZero) {
    EXPECT_EQ(piper_plus_num_speakers(nullptr), 0);
}

TEST(CApiQueryNull, NumLanguagesReturnsZero) {
    EXPECT_EQ(piper_plus_num_languages(nullptr), 0);
}

TEST(CApiQueryNull, LanguageIdReturnsNegative) {
    EXPECT_EQ(piper_plus_language_id(nullptr, "ja"), -1);
}

TEST(CApiQueryNull, LanguageIdNullNameReturnsNegative) {
    EXPECT_EQ(piper_plus_language_id(nullptr, nullptr), -1);
}

// ===== Invalid model path tests =====

TEST(CApiCreateError, InvalidModelPath) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/path/model.onnx";
    PiperPlusEngine* engine = piper_plus_create(&config);
    EXPECT_EQ(engine, nullptr);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
    EXPECT_GT(strlen(err), 0u);
}

TEST(CApiCreateError, InvalidModelPathAutoConfig) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/path/model.onnx";
    config.config_path = nullptr;
    PiperPlusEngine* engine = piper_plus_create(&config);
    EXPECT_EQ(engine, nullptr);
}

// ===== Error message tests =====

TEST(CApiErrorMessage, ErrorAvailableAfterFailure) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent";
    piper_plus_create(&config);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

// ===== Status code sanity =====

TEST(CApiStatusCodes, ValuesAreDefined) {
    EXPECT_EQ(PIPER_PLUS_OK, 0);
    EXPECT_GT(PIPER_PLUS_DONE, 0);
    EXPECT_LT(PIPER_PLUS_ERR, 0);
    EXPECT_LT(PIPER_PLUS_ERR_MODEL, 0);
    EXPECT_LT(PIPER_PLUS_ERR_CONFIG, 0);
    EXPECT_LT(PIPER_PLUS_ERR_TEXT, 0);
    EXPECT_LT(PIPER_PLUS_ERR_BUSY, 0);
}

TEST(CApiStatusCodes, ErrorCodesAreDistinct) {
    std::set<int32_t> codes = {
        PIPER_PLUS_OK, PIPER_PLUS_DONE,
        PIPER_PLUS_ERR, PIPER_PLUS_ERR_MODEL,
        PIPER_PLUS_ERR_CONFIG, PIPER_PLUS_ERR_TEXT,
        PIPER_PLUS_ERR_BUSY
    };
    EXPECT_EQ(codes.size(), 7u);
}

// ===== Config struct tests =====

TEST(CApiConfigStruct, MemsetSafe) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    EXPECT_EQ(config.model_path, nullptr);
    EXPECT_EQ(config.config_path, nullptr);
    EXPECT_EQ(config.provider, nullptr);
    EXPECT_EQ(config.num_threads, 0);
    EXPECT_EQ(config.gpu_device_id, 0);
    EXPECT_EQ(config.dict_dir, nullptr);
}

TEST(CApiConfigStruct, SynthOptionsMemsetSafe) {
    PiperPlusSynthOptions opts;
    memset(&opts, 0, sizeof(opts));
    EXPECT_EQ(opts.speaker_id, 0);
    EXPECT_EQ(opts.language_id, 0);
    EXPECT_FLOAT_EQ(opts.noise_scale, 0.0f);
    EXPECT_FLOAT_EQ(opts.length_scale, 0.0f);
}
