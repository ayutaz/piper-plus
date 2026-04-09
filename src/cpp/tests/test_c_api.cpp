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
#include <cstdio>
#include <fstream>
#include <set>
#include <string>
#include <thread>
#include <filesystem>
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
    for (int i = 0; i < static_cast<int>(sizeof(opts._reserved) / sizeof(opts._reserved[0])); i++) {
        EXPECT_EQ(opts._reserved[i], 0);
    }
}

// ===== NULL safety tests =====

TEST(CApiNullSafety, CreateWithNullConfig) {
    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(nullptr, &engine);
    EXPECT_NE(rc, PIPER_PLUS_OK);
    EXPECT_EQ(engine, nullptr);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiNullSafety, CreateWithNullModelPath) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = nullptr;
    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);
    EXPECT_EQ(rc, PIPER_PLUS_ERR_MODEL);
    EXPECT_EQ(engine, nullptr);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiNullSafety, SynthesizeWithNullEngine) {
    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;
    PiperPlusStatus status = piper_plus_synthesize(
        nullptr, "hello", nullptr, &samples, &num_samples, &sample_rate);
    EXPECT_LT(status, 0);
}

TEST(CApiNullSafety, SynthesizeWithNullText) {
    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;
    PiperPlusStatus status = piper_plus_synthesize(
        nullptr, nullptr, nullptr, &samples, &num_samples, &sample_rate);
    EXPECT_LT(status, 0);
}

TEST(CApiNullSafety, SynthesizeWithNullOutputParams) {
    PiperPlusStatus status = piper_plus_synthesize(
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
    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);
    EXPECT_EQ(rc, PIPER_PLUS_ERR_MODEL);
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
    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);
    EXPECT_NE(rc, PIPER_PLUS_OK);
    EXPECT_EQ(engine, nullptr);
}

// ===== Error message tests =====

TEST(CApiErrorMessage, ErrorAvailableAfterFailure) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent";
    PiperPlusEngine* engine = nullptr;
    piper_plus_create(&config, &engine);
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
    EXPECT_LT(PIPER_PLUS_ERR_ORT, 0);
}

TEST(CApiStatusCodes, ErrorCodesAreDistinct) {
    std::set<int32_t> codes = {
        PIPER_PLUS_OK, PIPER_PLUS_DONE,
        PIPER_PLUS_ERR, PIPER_PLUS_ERR_MODEL,
        PIPER_PLUS_ERR_CONFIG, PIPER_PLUS_ERR_TEXT,
        PIPER_PLUS_ERR_BUSY, PIPER_PLUS_ERR_ORT
    };
    EXPECT_EQ(codes.size(), 8u);
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
    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);
    EXPECT_EQ(rc, PIPER_PLUS_ERR_MODEL);
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
    PiperPlusEngine* engine = nullptr;
    piper_plus_create(&config, &engine);
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
    EXPECT_EQ(PIPER_PLUS_ERR_ORT, -6);
}

// ===== Phase 2: Streaming tests (M2-4) =====

// --- Iterator: NULL safety ---

TEST(CApiIterator, SynthStartNullEngine) {
    PiperPlusStatus rc = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiIterator, SynthStartNullText) {
    PiperPlusStatus rc = piper_plus_synth_start(nullptr, nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiIterator, SynthStartEmptyText) {
    PiperPlusStatus rc = piper_plus_synth_start(nullptr, "", nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiIterator, SynthNextNullEngine) {
    PiperPlusAudioChunk chunk = {};
    PiperPlusStatus rc = piper_plus_synth_next(nullptr, &chunk);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiIterator, SynthNextNullChunk) {
    PiperPlusStatus rc = piper_plus_synth_next(nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// --- Iterator: state machine ---

TEST(CApiIterator, SynthStartRepeatedNullEngine) {
    // NULL engine should not corrupt state
    PiperPlusStatus rc1 = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc1, PIPER_PLUS_ERR);
    PiperPlusStatus rc2 = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc2, PIPER_PLUS_ERR);
}

// --- Callback: NULL safety ---

// Helper: dummy callback for testing
static void dummy_callback(const float*, int32_t, int32_t, void*) {}

TEST(CApiCallback, StreamingNullEngine) {
    PiperPlusStatus rc = piper_plus_synthesize_streaming(
        nullptr, "hello", nullptr, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiCallback, StreamingNullText) {
    PiperPlusStatus rc = piper_plus_synthesize_streaming(
        nullptr, nullptr, nullptr, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiCallback, StreamingEmptyText) {
    PiperPlusStatus rc = piper_plus_synthesize_streaming(
        nullptr, "", nullptr, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiCallback, StreamingNullCallback) {
    PiperPlusStatus rc = piper_plus_synthesize_streaming(
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

// ===== Review fix tests =====

// R7: Text length limit
TEST(CApiTextLimit, SynthesizeRejectsHugeText) {
    // Create a string longer than 1 MB
    std::string hugeText(1024 * 1024 + 1, 'a');
    float *samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;

    // engine is NULL so ERR takes precedence over text limit,
    // but we can verify the function doesn't crash with huge text
    PiperPlusStatus rc = piper_plus_synthesize(
        nullptr, hugeText.c_str(), nullptr,
        &samples, &num_samples, &sample_rate);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiTextLimit, SynthStartRejectsHugeText) {
    std::string hugeText(1024 * 1024 + 1, 'a');
    PiperPlusStatus rc = piper_plus_synth_start(nullptr, hugeText.c_str(), nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// R1 regression: config save/restore order
// (Full verification requires a model; unit test verifies the code path doesn't crash)
TEST(CApiIterator, SynthStartWithOptsNullEngine) {
    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.noise_scale = 0.3f;
    opts.length_scale = 1.5f;
    // NULL engine should return ERR without crashing
    PiperPlusStatus rc = piper_plus_synth_start(nullptr, "hello", &opts);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// Streaming with opts
TEST(CApiCallback, StreamingWithOptsNullEngine) {
    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.noise_scale = 0.3f;
    PiperPlusStatus rc = piper_plus_synthesize_streaming(
        nullptr, "hello", &opts, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// ===== Phase 4: Custom dictionary tests (M4-1) =====

TEST(CApiCustomDict, LoadNullEngine) {
    EXPECT_EQ(piper_plus_load_custom_dict(nullptr, "dict.json"), PIPER_PLUS_ERR);
}

TEST(CApiCustomDict, LoadNullPath) {
    EXPECT_EQ(piper_plus_load_custom_dict(nullptr, nullptr), PIPER_PLUS_ERR);
}

TEST(CApiCustomDict, ClearNullEngine) {
    EXPECT_EQ(piper_plus_clear_custom_dict(nullptr), PIPER_PLUS_ERR);
}

TEST(CApiCustomDict, AddWordNullEngine) {
    EXPECT_EQ(piper_plus_add_dict_word(nullptr, "test", "t ɛ s t", 0), PIPER_PLUS_ERR);
}

TEST(CApiCustomDict, AddWordNullWord) {
    EXPECT_EQ(piper_plus_add_dict_word(nullptr, nullptr, "t ɛ s t", 0), PIPER_PLUS_ERR);
}

TEST(CApiCustomDict, EntryCountNullEngine) {
    EXPECT_EQ(piper_plus_dict_entry_count(nullptr), 0);
}

// ===== Phase 4: Phoneme timing tests (M4-2) =====

TEST(CApiTiming, GetTimingNullEngine) {
    PiperPlusTimingResult timing = {};
    EXPECT_EQ(piper_plus_get_phoneme_timing(nullptr, &timing), PIPER_PLUS_ERR);
}

TEST(CApiTiming, GetTimingNullResult) {
    EXPECT_EQ(piper_plus_get_phoneme_timing(nullptr, nullptr), PIPER_PLUS_ERR);
}

// ===== Phase 4: G2P tests (M4-3) =====

TEST(CApiG2P, PhonemizeNullEngine) {
    PiperPlusPhonemeResult result = {};
    EXPECT_EQ(piper_plus_phonemize(nullptr, "hello", nullptr, &result), PIPER_PLUS_ERR);
}

TEST(CApiG2P, PhonemizeNullText) {
    PiperPlusPhonemeResult result = {};
    EXPECT_EQ(piper_plus_phonemize(nullptr, nullptr, nullptr, &result), PIPER_PLUS_ERR);
}

TEST(CApiG2P, PhonemizeNullResult) {
    EXPECT_EQ(piper_plus_phonemize(nullptr, "hello", nullptr, nullptr), PIPER_PLUS_ERR);
}

TEST(CApiG2P, AvailableLanguagesNullEngine) {
    const char *langs = piper_plus_available_languages(nullptr);
    EXPECT_NE(langs, nullptr);
    EXPECT_EQ(std::strlen(langs), 0u);
}

// ===== Phase 5: Zero-init safety tests (M5-9) =====

TEST(CApiZeroInit, ZeroInitOptsNotCrash) {
    // memset で0初期化した opts を使用してもクラッシュしないことを確認
    // NULL engine なので ERR が返るが、opts のゼロ値でクラッシュしないことが重要
    PiperPlusSynthOptions opts;
    memset(&opts, 0, sizeof(opts));

    // One-shot synthesis with zero-init opts (NULL engine -> ERR)
    float *samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    PiperPlusStatus rc = piper_plus_synthesize(
        nullptr, "hello", &opts, &samples, &num_samples, &sample_rate);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);

    // Iterator with zero-init opts (NULL engine -> ERR)
    rc = piper_plus_synth_start(nullptr, "hello", &opts);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);

    // Streaming callback with zero-init opts (NULL engine -> ERR)
    rc = piper_plus_synthesize_streaming(
        nullptr, "hello", &opts, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiZeroInit, DefaultOptionsNotZero) {
    // piper_plus_default_options() の noise_scale, length_scale, noise_w がゼロでないことを確認
    PiperPlusSynthOptions opts = piper_plus_default_options();
    EXPECT_NE(opts.noise_scale, 0.0f);
    EXPECT_NE(opts.length_scale, 0.0f);
    EXPECT_NE(opts.noise_w, 0.0f);

    // 具体的なデフォルト値も検証
    EXPECT_FLOAT_EQ(opts.noise_scale, 0.667f);
    EXPECT_FLOAT_EQ(opts.length_scale, 1.0f);
    EXPECT_FLOAT_EQ(opts.noise_w, 0.8f);
}

// ===== Phase 5: Status enum tests (M5-13) =====

TEST(CApiStatusEnum, EnumSize) {
    // PiperPlusStatus must be the same size as int32_t for ABI compatibility
    EXPECT_EQ(sizeof(PiperPlusStatus), sizeof(int32_t));
}

TEST(CApiStatusEnum, EnumValues) {
    EXPECT_EQ(PIPER_PLUS_OK,         0);
    EXPECT_EQ(PIPER_PLUS_DONE,       1);
    EXPECT_EQ(PIPER_PLUS_ERR,       -1);
    EXPECT_EQ(PIPER_PLUS_ERR_MODEL, -2);
    EXPECT_EQ(PIPER_PLUS_ERR_CONFIG,-3);
    EXPECT_EQ(PIPER_PLUS_ERR_TEXT,  -4);
    EXPECT_EQ(PIPER_PLUS_ERR_BUSY,  -5);
    EXPECT_EQ(PIPER_PLUS_ERR_ORT,   -6);
}

TEST(CApiStatusEnum, EnumIsSignedInt) {
    // Negative values must work (signed representation)
    PiperPlusStatus s = PIPER_PLUS_ERR;
    EXPECT_LT(static_cast<int>(s), 0);
}

// ===== Phase 5: PhonemeResult _reserved tests (M5-12) =====

TEST(CApiPhonemeResult, ReservedSize) {
    // PiperPlusPhonemeResult must contain _reserved[4]
    // On 64-bit: ptr(8) + ptr(8) + int32(4) + int32[4](16) = 36, padded to 40
    // On 32-bit: ptr(4) + ptr(4) + int32(4) + int32[4](16) = 28
    PiperPlusPhonemeResult result;
    (void)result;  // suppress unused warning

    // Verify _reserved array has 4 elements
    EXPECT_EQ(sizeof(result._reserved), 4 * sizeof(int32_t));
}

TEST(CApiPhonemeResult, ZeroInitReserved) {
    // When zero-initialized, _reserved must all be zero
    PiperPlusPhonemeResult result = {};
    for (int i = 0; i < 4; i++) {
        EXPECT_EQ(result._reserved[i], 0);
    }
}

// ===== Phase 5: Cancellable streaming tests (M5-7) =====

// Helper: cancellable callback that always continues
static int dummy_callback_ex(const float*, int32_t, int32_t, void*) {
    return 0;  // continue
}

TEST(CApiStreamingEx, NullEngine) {
    PiperPlusStatus rc = piper_plus_synthesize_streaming_ex(
        nullptr, "hello", nullptr, dummy_callback_ex, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiStreamingEx, NullCallback) {
    PiperPlusStatus rc = piper_plus_synthesize_streaming_ex(
        nullptr, "hello", nullptr, nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiStreamingEx, NullText) {
    PiperPlusStatus rc = piper_plus_synthesize_streaming_ex(
        nullptr, nullptr, nullptr, dummy_callback_ex, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiStreamingEx, EmptyText) {
    PiperPlusStatus rc = piper_plus_synthesize_streaming_ex(
        nullptr, "", nullptr, dummy_callback_ex, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiStreamingEx, WithOptsNullEngine) {
    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.noise_scale = 0.3f;
    PiperPlusStatus rc = piper_plus_synthesize_streaming_ex(
        nullptr, "hello", &opts, dummy_callback_ex, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// ===== Phase 5: piper_plus_create status + out_engine pattern tests (M5-14) =====

TEST(CApiCreate, OutEngineNull) {
    // out_engine=NULL must return ERR without crashing
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/some/model.onnx";
    PiperPlusStatus rc = piper_plus_create(&config, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiCreate, InvalidModelPath) {
    // Non-existent model path must return ERR_MODEL
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/path/to/model.onnx";
    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);
    EXPECT_EQ(rc, PIPER_PLUS_ERR_MODEL);
    EXPECT_EQ(engine, nullptr);
}

TEST(CApiCreate, StatusCodeErrOrt) {
    // ERR_ORT must equal -6
    EXPECT_EQ(PIPER_PLUS_ERR_ORT, -6);
}

// ===== Boundary value tests for speaker_id / language_id =====

TEST(CApiBoundary, SpeakerIdNegative) {
    // speaker_id=-1 should be silently ignored by applySynthOptions
    // (the condition is "if (speaker_id >= 0)"), so it never sets speakerId.
    // With NULL engine the call returns ERR (null-safety), not a boundary error.
    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id = -1;

    float *samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    PiperPlusStatus rc = piper_plus_synthesize(
        nullptr, "hello", &opts, &samples, &num_samples, &sample_rate);
    // NULL engine -> ERR, but must not crash with speaker_id=-1
    EXPECT_EQ(rc, PIPER_PLUS_ERR);

    // Also verify iterator path
    rc = piper_plus_synth_start(nullptr, "hello", &opts);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);

    // And streaming path
    rc = piper_plus_synthesize_streaming(
        nullptr, "hello", &opts, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiBoundary, LanguageIdNegative) {
    // language_id=-1 means auto-detect and is the default value.
    // This must always be accepted (never treated as out-of-range).
    // With NULL engine the call returns ERR (null-safety), not a boundary error.
    PiperPlusSynthOptions opts = piper_plus_default_options();
    EXPECT_EQ(opts.language_id, -1);  // confirm default is -1

    float *samples = nullptr;
    int32_t num_samples = 0, sample_rate = 0;
    PiperPlusStatus rc = piper_plus_synthesize(
        nullptr, "hello", &opts, &samples, &num_samples, &sample_rate);
    // NULL engine -> ERR, but must not crash with language_id=-1
    EXPECT_EQ(rc, PIPER_PLUS_ERR);

    // Also verify iterator path
    rc = piper_plus_synth_start(nullptr, "hello", &opts);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);

    // And streaming path
    rc = piper_plus_synthesize_streaming(
        nullptr, "hello", &opts, dummy_callback, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// ===== Provider error handling tests =====

// Helper: create a minimal valid config JSON so that loadVoice config parsing
// succeeds and execution reaches the provider selection code in loadModel.
// Returns the path to the temporary file.  Caller is responsible for cleanup.
static std::string createMinimalConfigFile() {
    static int counter = 0;
    auto tmpDir = std::filesystem::temp_directory_path();
    std::string path = (tmpDir / ("piper_test_" + std::to_string(counter++) + ".json")).string();
    std::ofstream ofs(path);
    if (!ofs) return "";
    ofs << R"({"num_speakers": 1})";
    ofs.close();
    return path;
}

// Helper RAII guard to remove a temporary file on scope exit.
struct TempFileGuard {
    std::string path;
    explicit TempFileGuard(const std::string &p) : path(p) {}
    ~TempFileGuard() { std::remove(path.c_str()); }
};

TEST(CApiProviderError, UnknownProviderReturnsError) {
    // Use a minimal valid config so config parsing succeeds and the provider
    // check in loadModel is actually reached.
    std::string configPath = createMinimalConfigFile();
    TempFileGuard guard(configPath);

    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/model.onnx";
    config.config_path = configPath.c_str();
    config.provider = "opencl";

    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);

    EXPECT_NE(rc, PIPER_PLUS_OK);
    EXPECT_EQ(engine, nullptr);

    const char* err = piper_plus_get_last_error();
    ASSERT_NE(err, nullptr);
    EXPECT_NE(std::string(err).find("opencl"), std::string::npos)
        << "Error message should contain the provider name, got: " << err;
}

TEST(CApiProviderError, ProviderNullDefaultsToCpu) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/model.onnx";
    config.provider = nullptr;

    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);

    // Creation will fail (model/config not found), but the error must NOT be
    // about the provider -- it should be a model or config error instead.
    EXPECT_NE(rc, PIPER_PLUS_OK);
    EXPECT_EQ(engine, nullptr);

    const char* err = piper_plus_get_last_error();
    ASSERT_NE(err, nullptr);
    std::string errStr(err);
    EXPECT_EQ(errStr.find("provider"), std::string::npos)
        << "NULL provider should default to CPU without provider error, got: " << err;
    EXPECT_EQ(errStr.find("Unknown provider"), std::string::npos)
        << "NULL provider must not trigger unknown provider error, got: " << err;
}

TEST(CApiProviderError, ProviderEmptyStringDefaultsToCpu) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/model.onnx";
    config.provider = "";

    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);

    // Same as NULL: fails for model/config reasons, not provider.
    EXPECT_NE(rc, PIPER_PLUS_OK);
    EXPECT_EQ(engine, nullptr);

    const char* err = piper_plus_get_last_error();
    ASSERT_NE(err, nullptr);
    std::string errStr(err);
    EXPECT_EQ(errStr.find("provider"), std::string::npos)
        << "Empty provider should default to CPU without provider error, got: " << err;
    EXPECT_EQ(errStr.find("Unknown provider"), std::string::npos)
        << "Empty provider must not trigger unknown provider error, got: " << err;
}

#ifndef _WIN32
TEST(CApiProviderError, DirectmlOnNonWindowsReturnsError) {
    // On macOS/Linux, requesting DirectML must fail with a platform error.
    std::string configPath = createMinimalConfigFile();
    TempFileGuard guard(configPath);

    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/model.onnx";
    config.config_path = configPath.c_str();
    config.provider = "directml";

    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);

    EXPECT_NE(rc, PIPER_PLUS_OK);
    EXPECT_EQ(engine, nullptr);

    const char* err = piper_plus_get_last_error();
    ASSERT_NE(err, nullptr);
    EXPECT_NE(std::string(err).find("DirectML"), std::string::npos)
        << "Error should mention DirectML, got: " << err;
    EXPECT_NE(std::string(err).find("Windows"), std::string::npos)
        << "Error should mention Windows, got: " << err;
}
#endif // !_WIN32

#ifndef __APPLE__
TEST(CApiProviderError, CoremlOnNonAppleReturnsError) {
    // On Linux/Windows, requesting CoreML must fail with a platform error.
    std::string configPath = createMinimalConfigFile();
    TempFileGuard guard(configPath);

    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/model.onnx";
    config.config_path = configPath.c_str();
    config.provider = "coreml";

    PiperPlusEngine* engine = nullptr;
    PiperPlusStatus rc = piper_plus_create(&config, &engine);

    EXPECT_NE(rc, PIPER_PLUS_OK);
    EXPECT_EQ(engine, nullptr);

    const char* err = piper_plus_get_last_error();
    ASSERT_NE(err, nullptr);
    EXPECT_NE(std::string(err).find("CoreML"), std::string::npos)
        << "Error should mention CoreML, got: " << err;
    EXPECT_NE(std::string(err).find("macOS"), std::string::npos)
        << "Error should mention macOS, got: " << err;
}
#endif // !__APPLE__
