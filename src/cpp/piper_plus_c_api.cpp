/**
 * piper_plus_c_api.cpp — C API implementation for piper-plus shared library.
 *
 * Wraps the C++ piper API (piper.hpp) with an extern "C" interface
 * for FFI consumers (Flutter/Dart, Godot, Swift, etc.).
 *
 * TDD Green Phase: implements the functions declared in piper_plus.h
 * to satisfy the tests in test_c_api.cpp.
 */

#include "piper_plus.h"
#include "piper.hpp"

#include <atomic>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

// ===== Thread-local error message =====

static thread_local std::string g_last_error;

static void set_error(const char *msg) {
    g_last_error = msg ? msg : "Unknown error";
}

static void set_error(const std::string &msg) {
    g_last_error = msg;
}

// ===== Opaque engine structure =====

struct PiperPlusEngine {
    piper::PiperConfig config;
    piper::Voice voice;
    std::atomic<bool> inProgress{false};
};

// ===== Helpers =====

// Use 32768.0f to normalize symmetrically: -32768/32768 = -1.0, 32767/32768 ≈ 1.0
static const float NORM_FACTOR = 32768.0f;

// Convert int16_t audio buffer to float32 [-1.0, 1.0]
static float *int16_to_float(const std::vector<int16_t> &buf, int32_t *out_count) {
    if (buf.empty()) {
        *out_count = 0;
        return nullptr;
    }
    if (buf.size() > static_cast<size_t>(INT32_MAX)) {
        *out_count = 0;
        return nullptr;
    }
    *out_count = static_cast<int32_t>(buf.size());
    float *samples = static_cast<float *>(std::malloc(buf.size() * sizeof(float)));
    if (!samples) {
        *out_count = 0;
        return nullptr;
    }
    for (size_t i = 0; i < buf.size(); i++) {
        samples[i] = static_cast<float>(buf[i]) / NORM_FACTOR;
    }
    return samples;
}

// ===== API implementation =====

extern "C" {

PIPER_PLUS_API const char *piper_plus_version(void) {
    try {
        static std::string ver = piper::getVersion();
        return ver.c_str();
    } catch (...) {
        return "unknown";
    }
}

PIPER_PLUS_API int32_t piper_plus_api_version(void) {
    return PIPER_PLUS_API_VERSION;
}

PIPER_PLUS_API const char *piper_plus_get_last_error(void) {
    if (g_last_error.empty()) {
        return nullptr;
    }
    return g_last_error.c_str();
}

PIPER_PLUS_API PiperPlusSynthOptions piper_plus_default_options(void) {
    PiperPlusSynthOptions opts;
    std::memset(&opts, 0, sizeof(opts));
    opts.speaker_id = 0;
    opts.language_id = -1;
    opts.noise_scale = 0.667f;
    opts.length_scale = 1.0f;
    opts.noise_w = 0.8f;
    opts.sentence_silence_sec = 0.2f;
    return opts;
}

PIPER_PLUS_API PiperPlusEngine *piper_plus_create(const PiperPlusConfig *config) {
    if (!config) {
        set_error("config is NULL");
        return nullptr;
    }
    if (!config->model_path || config->model_path[0] == '\0') {
        set_error("model_path is NULL or empty");
        return nullptr;
    }

    try {
        auto engine = std::make_unique<PiperPlusEngine>();
        piper::initialize(engine->config);

        // dict_dir: set environment variable before loadVoice (M1-3)
        if (config->dict_dir && config->dict_dir[0] != '\0') {
#ifdef _WIN32
            _putenv_s("OPENJTALK_DICTIONARY_PATH", config->dict_dir);
#else
            setenv("OPENJTALK_DICTIONARY_PATH", config->dict_dir, 1);
#endif
        }

        // Determine config path
        std::string modelPath = config->model_path;
        std::string configPath;
        if (config->config_path && config->config_path[0] != '\0') {
            configPath = config->config_path;
        } else {
            configPath = modelPath + ".json";
        }

        // Determine CUDA usage
        bool useCuda = false;
        int gpuDeviceId = config->gpu_device_id;
        if (config->provider && std::strcmp(config->provider, "cuda") == 0) {
            useCuda = true;
        }

        std::optional<piper::SpeakerId> speakerId;  // loadVoice sets default

        piper::loadVoice(engine->config, modelPath, configPath,
                         engine->voice, speakerId, useCuda, gpuDeviceId);

        return engine.release();  // Transfer ownership to caller

    } catch (const std::exception &e) {
        set_error(e.what());
        return nullptr;  // unique_ptr auto-deletes engine
    } catch (...) {
        set_error("Unknown error during engine creation");
        return nullptr;  // unique_ptr auto-deletes engine
    }
}

PIPER_PLUS_API void piper_plus_free(PiperPlusEngine *engine) {
    if (!engine) return;
    try {
        piper::terminate(engine->config);
    } catch (...) {
        // Ignore errors during cleanup
    }
    delete engine;
}

PIPER_PLUS_API int32_t piper_plus_synthesize(
    PiperPlusEngine *engine,
    const char *text,
    const PiperPlusSynthOptions *opts,
    float **out_samples,
    int32_t *out_num_samples,
    int32_t *out_sample_rate)
{
    // NULL safety checks
    if (!engine) {
        set_error("engine is NULL");
        return PIPER_PLUS_ERR;
    }
    if (!text) {
        set_error("text is NULL");
        return PIPER_PLUS_ERR_TEXT;
    }
    if (!out_samples || !out_num_samples || !out_sample_rate) {
        set_error("output parameter is NULL");
        return PIPER_PLUS_ERR;
    }

    // Reentrancy guard
    bool expected = false;
    if (!engine->inProgress.compare_exchange_strong(expected, true)) {
        set_error("Engine is busy (synthesis in progress)");
        return PIPER_PLUS_ERR_BUSY;
    }

    // Save synthesisConfig before try block so catch can restore it
    auto savedConfig = engine->voice.synthesisConfig;

    try {
        // Apply options
        PiperPlusSynthOptions effectiveOpts;
        if (opts) {
            effectiveOpts = *opts;
        } else {
            effectiveOpts = piper_plus_default_options();
        }

        // Apply user options
        if (effectiveOpts.speaker_id >= 0) {
            engine->voice.synthesisConfig.speakerId = effectiveOpts.speaker_id;
        }
        if (effectiveOpts.language_id >= 0) {
            engine->voice.synthesisConfig.languageId = effectiveOpts.language_id;
        }
        engine->voice.synthesisConfig.noiseScale = effectiveOpts.noise_scale;
        engine->voice.synthesisConfig.lengthScale = effectiveOpts.length_scale;
        engine->voice.synthesisConfig.noiseW = effectiveOpts.noise_w;
        engine->voice.synthesisConfig.sentenceSilenceSeconds = effectiveOpts.sentence_silence_sec;

        // Synthesize
        std::vector<int16_t> audioBuffer;
        piper::SynthesisResult result;
        piper::textToAudio(engine->config, engine->voice, text,
                           audioBuffer, result, nullptr);

        // Restore config
        engine->voice.synthesisConfig = savedConfig;

        // Convert to float32
        *out_samples = int16_to_float(audioBuffer, out_num_samples);
        *out_sample_rate = engine->voice.synthesisConfig.sampleRate;

        engine->inProgress.store(false);
        return PIPER_PLUS_OK;

    } catch (const std::exception &e) {
        engine->voice.synthesisConfig = savedConfig;  // Restore on error
        set_error(e.what());
        engine->inProgress.store(false);
        return PIPER_PLUS_ERR;
    } catch (...) {
        engine->voice.synthesisConfig = savedConfig;  // Restore on error
        set_error("Unknown error during synthesis");
        engine->inProgress.store(false);
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API void piper_plus_free_audio(float *samples) {
    if (samples) {
        std::free(samples);
    }
}

PIPER_PLUS_API int32_t piper_plus_sample_rate(const PiperPlusEngine *engine) {
    if (!engine) return 0;
    return engine->voice.synthesisConfig.sampleRate;
}

PIPER_PLUS_API int32_t piper_plus_num_speakers(const PiperPlusEngine *engine) {
    if (!engine) return 0;
    return engine->voice.modelConfig.numSpeakers;
}

PIPER_PLUS_API int32_t piper_plus_num_languages(const PiperPlusEngine *engine) {
    if (!engine) return 0;
    return engine->voice.modelConfig.numLanguages;
}

PIPER_PLUS_API int32_t piper_plus_language_id(
    const PiperPlusEngine *engine,
    const char *language_name)
{
    if (!engine || !language_name) return -1;

    const auto &langMap = engine->voice.modelConfig.languageIdMap;
    if (!langMap) return -1;

    auto it = langMap->find(language_name);
    if (it == langMap->end()) return -1;

    return static_cast<int32_t>(it->second);
}

} // extern "C"
