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
#include <thread>
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

// ===== Review fix: additional tests =====

TEST(CApiCreateError, EmptyModelPathReturnsNull) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "";
    PiperPlusEngine* engine = piper_plus_create(&config);
    EXPECT_EQ(engine, nullptr);
    const char* err = piper_plus_get_last_error();
    ASSERT_NE(err, nullptr);
    EXPECT_GT(strlen(err), 0u);
}

TEST(CApiErrorMessage, InitialStateReturnsNullInNewThread) {
    std::thread t([] {
        const char* err = piper_plus_get_last_error();
        EXPECT_EQ(err, nullptr);
    });
    t.join();
}

TEST(CApiThreadSafety, LastErrorIsThreadLocal) {
    // メインスレッドでエラーを発生させる
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = nullptr;
    piper_plus_create(&config);
    const char* main_err = piper_plus_get_last_error();
    ASSERT_NE(main_err, nullptr);

    // 子スレッドではエラーが独立している
    std::thread t([] {
        const char* child_err = piper_plus_get_last_error();
        EXPECT_EQ(child_err, nullptr);
    });
    t.join();

    // メインスレッドのエラーは保持されている
    const char* main_err2 = piper_plus_get_last_error();
    EXPECT_NE(main_err2, nullptr);
}

TEST(CApiDefaultOptions, ReturnValueIsIndependentCopy) {
    PiperPlusSynthOptions opts1 = piper_plus_default_options();
    opts1.speaker_id = 42;
    opts1.noise_scale = 0.0f;
    PiperPlusSynthOptions opts2 = piper_plus_default_options();
    EXPECT_EQ(opts2.speaker_id, 0);
    EXPECT_FLOAT_EQ(opts2.noise_scale, 0.667f);
}

TEST(CApiStatusCodes, SpecificValuesMatchHeader) {
    EXPECT_EQ(PIPER_PLUS_OK, 0);
    EXPECT_EQ(PIPER_PLUS_DONE, 1);
    EXPECT_EQ(PIPER_PLUS_ERR, -1);
    EXPECT_EQ(PIPER_PLUS_ERR_MODEL, -2);
    EXPECT_EQ(PIPER_PLUS_ERR_CONFIG, -3);
    EXPECT_EQ(PIPER_PLUS_ERR_TEXT, -4);
    EXPECT_EQ(PIPER_PLUS_ERR_BUSY, -5);
}

// ===== Phase 2: Streaming tests (M2-4) =====

// --- Iterator: NULL safety ---

TEST(CApiIterator, SynthStartNullEngine) {
    int32_t rc = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiIterator, SynthStartNullText) {
    int32_t rc = piper_plus_synth_start(nullptr, nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiIterator, SynthStartEmptyText) {
    int32_t rc = piper_plus_synth_start(nullptr, "", nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiIterator, SynthNextNullEngine) {
    PiperPlusAudioChunk chunk = {};
    int32_t rc = piper_plus_synth_next(nullptr, &chunk);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiIterator, SynthNextNullChunk) {
    int32_t rc = piper_plus_synth_next(nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// --- Iterator: state machine ---

TEST(CApiIterator, SynthStartRepeatedNullEngine) {
    // NULL engine should not corrupt state
    int32_t rc1 = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc1, PIPER_PLUS_ERR);
    int32_t rc2 = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc2, PIPER_PLUS_ERR);
}

// --- Callback: NULL safety ---

// Helper: dummy callback for testing
static void dummy_callback(const float*, int32_t, int32_t, void*) {}

TEST(CApiCallback, StreamingNullEngine) {
    int32_t rc = piper_plus_synthesize_streaming(
        nullptr, "hello", nullptr, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiCallback, StreamingNullText) {
    int32_t rc = piper_plus_synthesize_streaming(
        nullptr, nullptr, nullptr, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiCallback, StreamingEmptyText) {
    int32_t rc = piper_plus_synthesize_streaming(
        nullptr, "", nullptr, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiCallback, StreamingNullCallback) {
    int32_t rc = piper_plus_synthesize_streaming(
        nullptr, "hello", nullptr, nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// --- Audio chunk struct ---

TEST(CApiAudioChunk, DefaultInitialization) {
    PiperPlusAudioChunk chunk = {};
    EXPECT_EQ(chunk.samples, nullptr);
    EXPECT_EQ(chunk.num_samples, 0);
    EXPECT_EQ(chunk.sample_rate, 0);
    EXPECT_EQ(chunk.is_last, 0);
}

TEST(CApiAudioChunk, FieldsSettable) {
    PiperPlusAudioChunk chunk = {};
    float dummy[] = {0.1f, 0.2f, 0.3f};
    chunk.samples = dummy;
    chunk.num_samples = 3;
    chunk.sample_rate = 22050;
    chunk.is_last = 1;

    EXPECT_FLOAT_EQ(chunk.samples[0], 0.1f);
    EXPECT_FLOAT_EQ(chunk.samples[2], 0.3f);
    EXPECT_EQ(chunk.num_samples, 3);
    EXPECT_EQ(chunk.sample_rate, 22050);
    EXPECT_EQ(chunk.is_last, 1);
}

TEST(CApiAudioChunk, ReasonableSize) {
    // 64-bit: ptr(8) + 3*int32(12) = 20, padded to 24
    // 32-bit: ptr(4) + 3*int32(12) = 16
    EXPECT_GE(sizeof(PiperPlusAudioChunk), 16u);
    EXPECT_LE(sizeof(PiperPlusAudioChunk), 32u);
}
