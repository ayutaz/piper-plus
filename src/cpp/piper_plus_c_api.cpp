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
#include "custom_dictionary.hpp"
#include "library_path.h"

#include <atomic>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <sys/stat.h>

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

// ===== Iterator state for streaming synthesis =====

struct IteratorState {
    std::vector<std::string> sentences;
    size_t currentIndex = 0;
    std::vector<float> currentChunkSamples;
    bool active = false;
    piper::SynthesisConfig savedConfig;
};

// ===== Opaque engine structure =====

struct PiperPlusEngine {
    piper::PiperConfig config;
    piper::Voice voice;
    std::atomic<bool> inProgress{false};
    IteratorState iterState;          // Phase 2: streaming state

    // M4-1: Custom dictionary
    std::unique_ptr<piper::CustomDictionary> customDict;

    // M4-2: Phoneme timing cache
    piper::SynthesisResult lastSynthResult;
    std::vector<PiperPlusPhonemeInfo> cachedTimings;
    std::vector<std::string> timingStrings;  // storage for phoneme string pointers

    // M4-3: G2P cache
    std::string g2pPhonemeStr;
    std::string g2pLanguage;
    std::string availableLanguagesStr;
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

// ===== Shared helper: apply synthesis options =====

static void applySynthOptions(piper::SynthesisConfig &synthConfig,
                              const PiperPlusSynthOptions *opts) {
    PiperPlusSynthOptions effectiveOpts;
    if (opts) {
        effectiveOpts = *opts;
    } else {
        effectiveOpts = piper_plus_default_options();
    }
    if (effectiveOpts.speaker_id >= 0) {
        synthConfig.speakerId = effectiveOpts.speaker_id;
    }
    if (effectiveOpts.language_id >= 0) {
        synthConfig.languageId = effectiveOpts.language_id;
    }
    synthConfig.noiseScale = effectiveOpts.noise_scale;
    synthConfig.lengthScale = effectiveOpts.length_scale;
    synthConfig.noiseW = effectiveOpts.noise_w;
    synthConfig.sentenceSilenceSeconds = effectiveOpts.sentence_silence_sec;
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

        // Mutex to protect setenv + loadVoice (setenv is not thread-safe)
        static std::mutex g_create_mutex;
        std::lock_guard<std::mutex> lock(g_create_mutex);

        piper::initialize(engine->config);

        // dict_dir: explicit path or auto-detect from library location
        std::string dictPath;
        if (config->dict_dir && config->dict_dir[0] != '\0') {
            dictPath = config->dict_dir;
        } else {
            // Try to auto-detect from library path: ../share/open_jtalk/dic
            char libDir[4096];
            if (piper_plus_get_library_dir(libDir, sizeof(libDir)) == 0) {
                std::string candidate = std::string(libDir) + "/../share/open_jtalk/dic";
                struct stat st;
                if (stat(candidate.c_str(), &st) == 0 && S_ISDIR(st.st_mode)) {
                    dictPath = candidate;
                }
            }
        }

        if (!dictPath.empty()) {
#ifdef _WIN32
            _putenv_s("OPENJTALK_DICTIONARY_PATH", dictPath.c_str());
#else
            setenv("OPENJTALK_DICTIONARY_PATH", dictPath.c_str(), 1);
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
        std::string msg = e.what();
        if (msg.find("model") != std::string::npos ||
            msg.find("onnx") != std::string::npos ||
            msg.find("ONNX") != std::string::npos) {
            set_error("Model error: " + msg);
        } else if (msg.find("config") != std::string::npos ||
                   msg.find("json") != std::string::npos ||
                   msg.find("JSON") != std::string::npos) {
            set_error("Config error: " + msg);
        } else {
            set_error(msg);
        }
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
    // Text length limit (1 MB)
    if (std::strlen(text) > 1024 * 1024) {
        set_error("text exceeds maximum length (1 MB)");
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
        applySynthOptions(engine->voice.synthesisConfig, opts);

        // Synthesize
        std::vector<int16_t> audioBuffer;
        piper::SynthesisResult result;
        piper::textToAudio(engine->config, engine->voice, text,
                           audioBuffer, result, nullptr);

        // M4-2: Cache timing info from last synthesis
        engine->lastSynthResult = result;

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

// ===== Iterator / Streaming synthesis =====

PIPER_PLUS_API int32_t piper_plus_synth_start(
    PiperPlusEngine *engine,
    const char *text,
    const PiperPlusSynthOptions *opts)
{
    if (!engine) {
        set_error("engine is NULL");
        return PIPER_PLUS_ERR;
    }
    if (!text || text[0] == '\0') {
        set_error("text is NULL or empty");
        return PIPER_PLUS_ERR_TEXT;
    }
    // Text length limit (1 MB)
    if (std::strlen(text) > 1024 * 1024) {
        set_error("text exceeds maximum length (1 MB)");
        return PIPER_PLUS_ERR_TEXT;
    }

    // Reentrancy guard
    bool expected = false;
    if (!engine->inProgress.compare_exchange_strong(expected, true)) {
        set_error("Engine is busy (synthesis in progress)");
        return PIPER_PLUS_ERR_BUSY;
    }

    try {
        // Save config BEFORE applying options (so we can restore later)
        engine->iterState.savedConfig = engine->voice.synthesisConfig;

        // Apply options
        applySynthOptions(engine->voice.synthesisConfig, opts);

        // Split text into sentences
        engine->iterState.sentences = piper::splitTextToSentences(
            text,
            engine->voice.phonemizeConfig.phonemeType,
            0);

        engine->iterState.currentIndex = 0;
        engine->iterState.currentChunkSamples.clear();
        engine->iterState.active = true;

        // Empty sentences: mark done immediately
        if (engine->iterState.sentences.empty()) {
            engine->iterState.active = false;
            engine->inProgress.store(false);
        }

        return PIPER_PLUS_OK;

    } catch (const std::exception &e) {
        set_error(e.what());
        engine->inProgress.store(false);
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error in synth_start");
        engine->inProgress.store(false);
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API int32_t piper_plus_synth_next(
    PiperPlusEngine *engine,
    PiperPlusAudioChunk *out_chunk)
{
    if (!engine) {
        set_error("engine is NULL");
        return PIPER_PLUS_ERR;
    }
    if (!out_chunk) {
        set_error("out_chunk is NULL");
        return PIPER_PLUS_ERR;
    }
    if (!engine->iterState.active) {
        set_error("synth_start() was not called or iterator already finished");
        return PIPER_PLUS_ERR;
    }

    auto &state = engine->iterState;

    try {
        // All sentences done?
        if (state.currentIndex >= state.sentences.size()) {
            engine->voice.synthesisConfig = state.savedConfig;
            state.active = false;
            engine->inProgress.store(false);

            out_chunk->samples = nullptr;
            out_chunk->num_samples = 0;
            out_chunk->sample_rate = engine->voice.synthesisConfig.sampleRate;
            out_chunk->is_last = 1;
            return PIPER_PLUS_DONE;
        }

        // Synthesize current sentence
        const std::string &sentence = state.sentences[state.currentIndex];
        std::vector<int16_t> audioBuffer;
        piper::SynthesisResult synthResult;

        piper::textToAudio(engine->config, engine->voice, sentence,
                           audioBuffer, synthResult, nullptr);

        // M4-2: Cache timing info from last synthesis
        engine->lastSynthResult = synthResult;

        // Convert int16 -> float32
        state.currentChunkSamples.resize(audioBuffer.size());
        for (size_t i = 0; i < audioBuffer.size(); i++) {
            state.currentChunkSamples[i] =
                static_cast<float>(audioBuffer[i]) / NORM_FACTOR;
        }

        state.currentIndex++;
        bool isLast = (state.currentIndex >= state.sentences.size());

        // Fill output chunk
        if (state.currentChunkSamples.size() > static_cast<size_t>(INT32_MAX)) {
            set_error("Audio chunk too large");
            engine->voice.synthesisConfig = state.savedConfig;
            state.active = false;
            engine->inProgress.store(false);
            return PIPER_PLUS_ERR;
        }
        out_chunk->samples = state.currentChunkSamples.data();
        out_chunk->num_samples = static_cast<int32_t>(state.currentChunkSamples.size());
        out_chunk->sample_rate = engine->voice.synthesisConfig.sampleRate;
        out_chunk->is_last = isLast ? 1 : 0;

        if (isLast) {
            engine->voice.synthesisConfig = state.savedConfig;
            state.active = false;
            engine->inProgress.store(false);
        }

        return isLast ? PIPER_PLUS_DONE : PIPER_PLUS_OK;

    } catch (const std::exception &e) {
        engine->voice.synthesisConfig = state.savedConfig;
        set_error(e.what());
        state.active = false;
        engine->inProgress.store(false);
        return PIPER_PLUS_ERR;
    } catch (...) {
        engine->voice.synthesisConfig = state.savedConfig;
        set_error("Unknown error in synth_next");
        state.active = false;
        engine->inProgress.store(false);
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API int32_t piper_plus_synthesize_streaming(
    PiperPlusEngine *engine,
    const char *text,
    const PiperPlusSynthOptions *opts,
    PiperPlusAudioCallback callback,
    void *user_data)
{
    if (!engine) {
        set_error("engine is NULL");
        return PIPER_PLUS_ERR;
    }
    if (!text || text[0] == '\0') {
        set_error("text is NULL or empty");
        return PIPER_PLUS_ERR_TEXT;
    }
    if (!callback) {
        set_error("callback is NULL");
        return PIPER_PLUS_ERR;
    }

    // Start iterator (handles busy check internally)
    int32_t rc = piper_plus_synth_start(engine, text, opts);
    if (rc != PIPER_PLUS_OK) {
        return rc;
    }

    // Drive iterator to completion
    try {
        PiperPlusAudioChunk chunk;
        for (;;) {
            rc = piper_plus_synth_next(engine, &chunk);

            if (rc == PIPER_PLUS_ERR) {
                return PIPER_PLUS_ERR;
            }

            // Deliver chunk via callback
            if (chunk.num_samples > 0) {
                try {
                    callback(chunk.samples, chunk.num_samples,
                             chunk.sample_rate, user_data);
                } catch (...) {
                    // Callback threw - clean up
                    engine->iterState.active = false;
                    engine->inProgress.store(false);
                    engine->voice.synthesisConfig = engine->iterState.savedConfig;
                    set_error("callback threw an exception");
                    return PIPER_PLUS_ERR;
                }
            }

            if (rc == PIPER_PLUS_DONE) {
                break;
            }
        }

        return PIPER_PLUS_OK;

    } catch (const std::exception &e) {
        set_error(e.what());
        engine->iterState.active = false;
        engine->inProgress.store(false);
        engine->voice.synthesisConfig = engine->iterState.savedConfig;
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error in synthesize_streaming");
        engine->iterState.active = false;
        engine->inProgress.store(false);
        engine->voice.synthesisConfig = engine->iterState.savedConfig;
        return PIPER_PLUS_ERR;
    }
}

// ===== M4-1: Custom dictionary =====

PIPER_PLUS_API int32_t piper_plus_load_custom_dict(
    PiperPlusEngine *engine, const char *dict_path) {
    if (!engine) { set_error("engine is NULL"); return PIPER_PLUS_ERR; }
    if (!dict_path) { set_error("dict_path is NULL"); return PIPER_PLUS_ERR; }

    try {
        if (!engine->customDict) {
            engine->customDict = std::make_unique<piper::CustomDictionary>();
        }
        engine->customDict->loadDictionary(dict_path);
        return PIPER_PLUS_OK;
    } catch (const std::exception &e) {
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error loading dictionary");
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API int32_t piper_plus_clear_custom_dict(PiperPlusEngine *engine) {
    if (!engine) { set_error("engine is NULL"); return PIPER_PLUS_ERR; }
    engine->customDict.reset();
    return PIPER_PLUS_OK;
}

PIPER_PLUS_API int32_t piper_plus_add_dict_word(
    PiperPlusEngine *engine, const char *word,
    const char *pronunciation, int32_t priority) {
    if (!engine) { set_error("engine is NULL"); return PIPER_PLUS_ERR; }
    if (!word || !pronunciation) { set_error("word or pronunciation is NULL"); return PIPER_PLUS_ERR; }

    try {
        if (!engine->customDict) {
            engine->customDict = std::make_unique<piper::CustomDictionary>();
        }
        engine->customDict->addWord(word, pronunciation, static_cast<int>(priority));
        return PIPER_PLUS_OK;
    } catch (const std::exception &e) {
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error adding dictionary word");
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API int32_t piper_plus_dict_entry_count(const PiperPlusEngine *engine) {
    if (!engine || !engine->customDict) return 0;
    auto stats = engine->customDict->getStats();
    return static_cast<int32_t>(stats.totalEntries);
}

// ===== M4-2: Phoneme timing =====

PIPER_PLUS_API int32_t piper_plus_get_phoneme_timing(
    const PiperPlusEngine *engine, PiperPlusTimingResult *out_timing) {
    if (!engine) { set_error("engine is NULL"); return PIPER_PLUS_ERR; }
    if (!out_timing) { set_error("out_timing is NULL"); return PIPER_PLUS_ERR; }

    if (!engine->lastSynthResult.hasTimingInfo ||
        engine->lastSynthResult.phonemeTimings.empty()) {
        set_error("No timing information available (model may not support duration output)");
        out_timing->entries = nullptr;
        out_timing->count = 0;
        return PIPER_PLUS_ERR;
    }

    // Build C-compatible timing array (cached in mutable engine state)
    auto *mutableEngine = const_cast<PiperPlusEngine*>(engine);
    const auto &timings = engine->lastSynthResult.phonemeTimings;

    mutableEngine->timingStrings.clear();
    mutableEngine->cachedTimings.clear();
    mutableEngine->timingStrings.reserve(timings.size());
    mutableEngine->cachedTimings.reserve(timings.size());

    for (const auto &t : timings) {
        mutableEngine->timingStrings.push_back(t.phoneme);
        PiperPlusPhonemeInfo info;
        info.phoneme = mutableEngine->timingStrings.back().c_str();
        info.start_time = t.start_time;
        info.end_time = t.end_time;
        mutableEngine->cachedTimings.push_back(info);
    }

    out_timing->entries = mutableEngine->cachedTimings.data();
    out_timing->count = static_cast<int32_t>(mutableEngine->cachedTimings.size());
    return PIPER_PLUS_OK;
}

// ===== M4-3: G2P / Phonemization =====

PIPER_PLUS_API int32_t piper_plus_phonemize(
    PiperPlusEngine *engine, const char *text,
    const char *language, PiperPlusPhonemeResult *out_result) {
    if (!engine) { set_error("engine is NULL"); return PIPER_PLUS_ERR; }
    if (!text) { set_error("text is NULL"); return PIPER_PLUS_ERR_TEXT; }
    if (!out_result) { set_error("out_result is NULL"); return PIPER_PLUS_ERR; }

    try {
        // Save and optionally set language
        auto savedLangId = engine->voice.synthesisConfig.languageId;
        if (language && language[0] != '\0' && engine->voice.modelConfig.languageIdMap) {
            auto it = engine->voice.modelConfig.languageIdMap->find(language);
            if (it != engine->voice.modelConfig.languageIdMap->end()) {
                engine->voice.synthesisConfig.languageId = it->second;
            }
        }

        piper::PhonemizeResult phonResult;
        piper::phonemizeText(engine->voice, text, phonResult);

        // Detect language from current config
        engine->g2pLanguage = "unknown";
        if (engine->voice.synthesisConfig.languageId &&
            engine->voice.modelConfig.languageIdMap) {
            for (const auto &[code, id] : *engine->voice.modelConfig.languageIdMap) {
                if (id == *engine->voice.synthesisConfig.languageId) {
                    engine->g2pLanguage = code;
                    break;
                }
            }
        }

        // Build space-separated phoneme string from codepoints
        engine->g2pPhonemeStr.clear();
        int32_t count = 0;
        for (const auto &sentence : phonResult.phonemes) {
            for (auto ph : sentence) {
                if (!engine->g2pPhonemeStr.empty()) engine->g2pPhonemeStr += ' ';
                // Convert char32_t codepoint to UTF-8
                if (ph < 0x80) {
                    engine->g2pPhonemeStr += static_cast<char>(ph);
                } else if (ph < 0x800) {
                    engine->g2pPhonemeStr += static_cast<char>(0xC0 | (ph >> 6));
                    engine->g2pPhonemeStr += static_cast<char>(0x80 | (ph & 0x3F));
                } else if (ph < 0x10000) {
                    engine->g2pPhonemeStr += static_cast<char>(0xE0 | (ph >> 12));
                    engine->g2pPhonemeStr += static_cast<char>(0x80 | ((ph >> 6) & 0x3F));
                    engine->g2pPhonemeStr += static_cast<char>(0x80 | (ph & 0x3F));
                } else {
                    engine->g2pPhonemeStr += static_cast<char>(0xF0 | (ph >> 18));
                    engine->g2pPhonemeStr += static_cast<char>(0x80 | ((ph >> 12) & 0x3F));
                    engine->g2pPhonemeStr += static_cast<char>(0x80 | ((ph >> 6) & 0x3F));
                    engine->g2pPhonemeStr += static_cast<char>(0x80 | (ph & 0x3F));
                }
                count++;
            }
        }

        // Restore language
        engine->voice.synthesisConfig.languageId = savedLangId;

        out_result->phonemes = engine->g2pPhonemeStr.c_str();
        out_result->language = engine->g2pLanguage.c_str();
        out_result->num_phonemes = count;
        return PIPER_PLUS_OK;

    } catch (const std::exception &e) {
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error in phonemize");
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API const char *piper_plus_available_languages(const PiperPlusEngine *engine) {
    if (!engine) return "";

    auto *mutableEngine = const_cast<PiperPlusEngine*>(engine);
    if (!engine->voice.modelConfig.languageIdMap) {
        mutableEngine->availableLanguagesStr = "";
        return mutableEngine->availableLanguagesStr.c_str();
    }

    mutableEngine->availableLanguagesStr.clear();
    for (const auto &[code, id] : *engine->voice.modelConfig.languageIdMap) {
        if (!mutableEngine->availableLanguagesStr.empty())
            mutableEngine->availableLanguagesStr += ',';
        mutableEngine->availableLanguagesStr += code;
    }
    return mutableEngine->availableLanguagesStr.c_str();
}

} // extern "C"
