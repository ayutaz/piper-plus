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

#include <algorithm>
#include <atomic>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#include <sys/stat.h>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#ifndef S_ISDIR
#define S_ISDIR(m) (((m) & _S_IFMT) == _S_IFDIR)
#endif
#endif

// ===== ABI safety: enum must be int32_t-sized =====
static_assert(sizeof(PiperPlusStatus) == sizeof(int32_t),
              "PiperPlusStatus must be the same size as int32_t");

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
    piper::SynthesisConfig configSnapshot_;  // saved by synth_start, restored by finish()

    // M5-3: crossfade between sentence chunks
    static constexpr size_t CROSSFADE_SAMPLES = 220; // 10ms @ 22050Hz
    std::vector<float> prevTail; // previous chunk's tail samples for crossfade

    /// Restore synthesisConfig from snapshot, mark inactive, release inProgress.
    void finish(piper::SynthesisConfig &liveConfig, std::atomic<bool> &inProgress) {
        liveConfig = configSnapshot_;
        active = false;
        prevTail.clear();
        inProgress.store(false, std::memory_order_release);
    }
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

// ===== RAII guards (M5-1) =====

namespace {

/// Saves a SynthesisConfig on construction and restores it on destruction.
/// Guarantees config is restored even if an exception is thrown.
class ConfigGuard {
public:
    ConfigGuard(piper::SynthesisConfig &config)
        : config_(config), saved_(config) {}
    ~ConfigGuard() { config_ = saved_; }

    ConfigGuard(const ConfigGuard &) = delete;
    ConfigGuard &operator=(const ConfigGuard &) = delete;

private:
    piper::SynthesisConfig &config_;
    piper::SynthesisConfig  saved_;
};

/// Acquires an atomic bool flag (CAS) on construction, releases on destruction.
/// Construction fails with std::runtime_error if the flag is already set.
/// Call disarm() to prevent the destructor from releasing (e.g. synth_start
/// keeps inProgress=true so that synth_next can continue).
class BusyGuard {
public:
    BusyGuard(std::atomic<bool> &flag) : flag_(flag), armed_(true) {
        bool expected = false;
        if (!flag_.compare_exchange_strong(expected, true)) {
            throw std::runtime_error("Engine is busy");
        }
    }
    ~BusyGuard() {
        if (armed_) flag_.store(false, std::memory_order_release);
    }

    /// Prevent the destructor from releasing the flag.
    void disarm() { armed_ = false; }

    BusyGuard(const BusyGuard &) = delete;
    BusyGuard &operator=(const BusyGuard &) = delete;

private:
    std::atomic<bool> &flag_;
    bool armed_;
};

} // anonymous namespace

// ===== Text length limit =====

// Maximum text input length (bytes). Prevents excessive memory allocation
// and unbounded synthesis time from very large inputs.
static constexpr size_t MAX_TEXT_LENGTH = 1024 * 1024; // 1 MB

// ===== Shared helper: apply synthesis options =====

static void applySynthOptions(piper::SynthesisConfig &synthConfig,
                              const PiperPlusSynthOptions *opts) {
    PiperPlusSynthOptions effectiveOpts;
    if (opts) {
        effectiveOpts = *opts;
    } else {
        effectiveOpts = piper_plus_default_options();
    }

    // Zero-init safety: replace 0.0 with sensible defaults
    // 注意: ゼロ値置換により意図的な deterministic 推論 (noise_scale=0) が無効化される
    if (effectiveOpts.noise_scale == 0.0f)
        effectiveOpts.noise_scale = 0.667f;
    if (effectiveOpts.length_scale == 0.0f)
        effectiveOpts.length_scale = 1.0f;
    if (effectiveOpts.noise_w == 0.0f)
        effectiveOpts.noise_w = 0.8f;

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

    // Voice cloning: speaker embedding
    if (effectiveOpts.speaker_embedding && effectiveOpts.speaker_embedding_dim > 0) {
        synthConfig.speakerEmbedding.assign(
            effectiveOpts.speaker_embedding,
            effectiveOpts.speaker_embedding + effectiveOpts.speaker_embedding_dim);
    } else {
        synthConfig.speakerEmbedding.clear();
    }
}

// ===== Boundary validation for speaker_id / language_id =====

/// Validate that the current synthesisConfig speaker_id and language_id are
/// within the model's valid range. Returns PIPER_PLUS_OK on success, or an
/// error status (with set_error) if out of range.
///
/// speaker_id is only checked when numSpeakers > 0 (multi-speaker model).
/// language_id == -1 means auto-detect and is always valid.
static PiperPlusStatus validateSynthIds(const PiperPlusEngine *engine) {
    const auto &synthConfig = engine->voice.synthesisConfig;
    const auto &modelConfig = engine->voice.modelConfig;

    // speaker_id check: only for multi-speaker models (numSpeakers > 0)
    if (synthConfig.speakerId.has_value() && modelConfig.numSpeakers > 0) {
        int64_t sid = static_cast<int64_t>(synthConfig.speakerId.value());
        if (sid < 0 || sid >= static_cast<int64_t>(modelConfig.numSpeakers)) {
            set_error("speaker_id " + std::to_string(sid) +
                      " out of range [0, " +
                      std::to_string(modelConfig.numSpeakers) + ")");
            return PIPER_PLUS_ERR_TEXT;
        }
    }

    // language_id check: only for multi-language models (numLanguages > 1)
    if (synthConfig.languageId.has_value() && modelConfig.numLanguages > 1) {
        int64_t lid = static_cast<int64_t>(synthConfig.languageId.value());
        // lid == -1 means auto-detect → always valid (already handled by applySynthOptions)
        if (lid >= 0 && lid >= static_cast<int64_t>(modelConfig.numLanguages)) {
            set_error("language_id " + std::to_string(lid) +
                      " out of range [0, " +
                      std::to_string(modelConfig.numLanguages) + ")");
            return PIPER_PLUS_ERR_TEXT;
        }
    }

    return PIPER_PLUS_OK;
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

PIPER_PLUS_API PiperPlusStatus piper_plus_create(
    const PiperPlusConfig *config,
    PiperPlusEngine      **out_engine)
{
    if (!out_engine) {
        set_error("out_engine is NULL");
        return PIPER_PLUS_ERR;
    }
    *out_engine = nullptr;

    if (!config) {
        set_error("config is NULL");
        return PIPER_PLUS_ERR;
    }
    if (!config->model_path || config->model_path[0] == '\0') {
        set_error("model_path is NULL or empty");
        return PIPER_PLUS_ERR_MODEL;
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

        // Determine provider and GPU device
        std::string provider = (config->provider && config->provider[0] != '\0')
                               ? config->provider : "cpu";
        int gpuDeviceId = config->gpu_device_id;
        int numThreads = (config->num_threads < 0) ? 0 : config->num_threads;

        std::optional<piper::SpeakerId> speakerId;  // loadVoice sets default

        piper::loadVoice(engine->config, modelPath, configPath,
                         engine->voice, speakerId, provider, gpuDeviceId,
                         numThreads);

        *out_engine = engine.release();  // Transfer ownership to caller
        return PIPER_PLUS_OK;

    } catch (const std::exception &e) {
        std::string msg = e.what();

        // Classify exception by message content
        if (msg.find("onnxruntime") != std::string::npos ||
            msg.find("OrtException") != std::string::npos ||
            msg.find("ORT ") != std::string::npos ||
            msg.find("InferenceSession") != std::string::npos ||
            msg.find("SessionOptions") != std::string::npos) {
            set_error("ORT error: " + msg);
            return PIPER_PLUS_ERR_ORT;
        }
        if (msg.find("model") != std::string::npos ||
            msg.find("onnx") != std::string::npos ||
            msg.find("ONNX") != std::string::npos ||
            msg.find("No such file") != std::string::npos ||
            msg.find("not found") != std::string::npos ||
            msg.find("Failed to open") != std::string::npos) {
            set_error("Model error: " + msg);
            return PIPER_PLUS_ERR_MODEL;
        }
        if (msg.find("config") != std::string::npos ||
            msg.find("json") != std::string::npos ||
            msg.find("JSON") != std::string::npos) {
            set_error("Config error: " + msg);
            return PIPER_PLUS_ERR_CONFIG;
        }
        set_error(msg);
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error during engine creation");
        return PIPER_PLUS_ERR;
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

PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize(
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
    // Text length limit
    if (std::strlen(text) > MAX_TEXT_LENGTH) {
        set_error("text exceeds maximum length (1 MB)");
        return PIPER_PLUS_ERR_TEXT;
    }
    if (!out_samples || !out_num_samples || !out_sample_rate) {
        set_error("output parameter is NULL");
        return PIPER_PLUS_ERR;
    }

    try {
        BusyGuard busy(engine->inProgress);
        ConfigGuard cfgGuard(engine->voice.synthesisConfig);

        // Apply options
        applySynthOptions(engine->voice.synthesisConfig, opts);

        // Validate speaker_id / language_id bounds
        PiperPlusStatus idCheck = validateSynthIds(engine);
        if (idCheck != PIPER_PLUS_OK) return idCheck;

        // Apply custom dictionary
        std::string processedText = text;
        if (engine->customDict) {
            processedText = engine->customDict->applyToText(processedText);
        }

        // Synthesize directly to float32 (avoids int16 intermediate conversion)
        std::vector<float> audioBuffer;
        piper::SynthesisResult result;
        piper::textToAudioFloat(engine->config, engine->voice, processedText,
                                audioBuffer, result, nullptr);

        // M4-2: Cache timing info from last synthesis
        engine->lastSynthResult = result;

        // Copy to malloc'd buffer for caller
        if (audioBuffer.empty()) {
            *out_samples = nullptr;
            *out_num_samples = 0;
        } else if (audioBuffer.size() > static_cast<size_t>(INT32_MAX)) {
            *out_samples = nullptr;
            *out_num_samples = 0;
        } else {
            *out_num_samples = static_cast<int32_t>(audioBuffer.size());
            *out_samples = static_cast<float*>(std::malloc(audioBuffer.size() * sizeof(float)));
            if (*out_samples) {
                std::memcpy(*out_samples, audioBuffer.data(), audioBuffer.size() * sizeof(float));
            } else {
                *out_num_samples = 0;
            }
        }
        *out_sample_rate = engine->voice.synthesisConfig.sampleRate;

        return PIPER_PLUS_OK;

    } catch (const std::runtime_error &e) {
        // BusyGuard throws runtime_error when engine is busy
        if (std::string(e.what()) == "Engine is busy") {
            set_error("Engine is busy (synthesis in progress)");
            return PIPER_PLUS_ERR_BUSY;
        }
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (const std::exception &e) {
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error during synthesis");
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

PIPER_PLUS_API PiperPlusStatus piper_plus_synth_start(
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
    // Text length limit
    if (std::strlen(text) > MAX_TEXT_LENGTH) {
        set_error("text exceeds maximum length (1 MB)");
        return PIPER_PLUS_ERR_TEXT;
    }

    try {
        BusyGuard busy(engine->inProgress);

        // Save config BEFORE applying options (so we can restore in synth_next)
        engine->iterState.configSnapshot_ = engine->voice.synthesisConfig;

        // Apply options
        applySynthOptions(engine->voice.synthesisConfig, opts);

        // Validate speaker_id / language_id bounds
        PiperPlusStatus idCheck = validateSynthIds(engine);
        if (idCheck != PIPER_PLUS_OK) {
            // Restore config before returning (ConfigGuard not used here)
            engine->voice.synthesisConfig = engine->iterState.configSnapshot_;
            return idCheck;
        }

        // Apply custom dictionary
        std::string processedText = text;
        if (engine->customDict) {
            processedText = engine->customDict->applyToText(processedText);
        }

        // Split text into sentences
        engine->iterState.sentences = piper::splitTextToSentences(
            processedText,
            engine->voice.phonemizeConfig.phonemeType,
            0);

        engine->iterState.currentIndex = 0;
        engine->iterState.currentChunkSamples.clear();
        engine->iterState.prevTail.clear();  // M5-3: reset crossfade state
        engine->iterState.active = true;

        // Empty sentences: mark done immediately (let BusyGuard release)
        if (engine->iterState.sentences.empty()) {
            engine->iterState.active = false;
            // armed_ remains true → destructor releases inProgress
        } else {
            // Non-empty: keep inProgress=true for synth_next to use
            busy.disarm();
        }

        return PIPER_PLUS_OK;

    } catch (const std::runtime_error &e) {
        if (std::string(e.what()) == "Engine is busy") {
            set_error("Engine is busy (synthesis in progress)");
            return PIPER_PLUS_ERR_BUSY;
        }
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (const std::exception &e) {
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error in synth_start");
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API PiperPlusStatus piper_plus_synth_next(
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
            state.finish(engine->voice.synthesisConfig, engine->inProgress);

            out_chunk->samples = nullptr;
            out_chunk->num_samples = 0;
            out_chunk->sample_rate = engine->voice.synthesisConfig.sampleRate;
            out_chunk->is_last = 1;
            return PIPER_PLUS_DONE;
        }

        // Synthesize current sentence directly to float32
        const std::string &sentence = state.sentences[state.currentIndex];
        std::vector<float> audioBuffer;
        piper::SynthesisResult synthResult;

        piper::textToAudioFloat(engine->config, engine->voice, sentence,
                                audioBuffer, synthResult, nullptr);

        // M4-2: Cache timing info from last synthesis
        engine->lastSynthResult = synthResult;

        state.currentIndex++;
        bool isLast = (state.currentIndex >= state.sentences.size());

        // M5-3: Apply crossfade between sentence chunks
        // Step 1: Crossfade prevTail with the beginning of audioBuffer
        if (!state.prevTail.empty() &&
            audioBuffer.size() >= IteratorState::CROSSFADE_SAMPLES) {
            for (size_t i = 0; i < IteratorState::CROSSFADE_SAMPLES; ++i) {
                float alpha = static_cast<float>(i) / IteratorState::CROSSFADE_SAMPLES;
                audioBuffer[i] = state.prevTail[i] * (1.0f - alpha)
                               + audioBuffer[i] * alpha;
            }
            state.prevTail.clear();
        }

        // Step 2: Save tail / append prevTail depending on last-chunk status
        if (!isLast) {
            // Non-final chunk: save tail for next crossfade, trim from output
            if (audioBuffer.size() >= IteratorState::CROSSFADE_SAMPLES) {
                state.prevTail.assign(
                    audioBuffer.end() - static_cast<std::ptrdiff_t>(IteratorState::CROSSFADE_SAMPLES),
                    audioBuffer.end());
                audioBuffer.resize(audioBuffer.size() - IteratorState::CROSSFADE_SAMPLES);
            } else {
                state.prevTail.clear();
            }
        } else {
            // Final chunk: flush any remaining prevTail into output
            if (!state.prevTail.empty()) {
                // prevTail was not consumed by crossfade (e.g. audioBuffer was short)
                // Prepend it to the output
                audioBuffer.insert(audioBuffer.begin(),
                                   state.prevTail.begin(),
                                   state.prevTail.end());
                state.prevTail.clear();
            }
        }

        // Move to chunk buffer
        state.currentChunkSamples = std::move(audioBuffer);

        // Fill output chunk
        if (state.currentChunkSamples.size() > static_cast<size_t>(INT32_MAX)) {
            set_error("Audio chunk too large");
            state.finish(engine->voice.synthesisConfig, engine->inProgress);
            return PIPER_PLUS_ERR;
        }
        out_chunk->samples = state.currentChunkSamples.data();
        out_chunk->num_samples = static_cast<int32_t>(state.currentChunkSamples.size());
        out_chunk->sample_rate = engine->voice.synthesisConfig.sampleRate;
        out_chunk->is_last = isLast ? 1 : 0;

        if (isLast) {
            state.finish(engine->voice.synthesisConfig, engine->inProgress);
        }

        return isLast ? PIPER_PLUS_DONE : PIPER_PLUS_OK;

    } catch (const std::exception &e) {
        set_error(e.what());
        state.finish(engine->voice.synthesisConfig, engine->inProgress);
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error in synth_next");
        state.finish(engine->voice.synthesisConfig, engine->inProgress);
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize_streaming(
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
    PiperPlusStatus rc = piper_plus_synth_start(engine, text, opts);
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
                    // Callback threw - clean up via finish()
                    engine->iterState.finish(engine->voice.synthesisConfig,
                                             engine->inProgress);
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
        engine->iterState.finish(engine->voice.synthesisConfig, engine->inProgress);
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error in synthesize_streaming");
        engine->iterState.finish(engine->voice.synthesisConfig, engine->inProgress);
        return PIPER_PLUS_ERR;
    }
}

// ===== M5-7: Cancellable streaming callback =====

PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize_streaming_ex(
    PiperPlusEngine *engine,
    const char *text,
    const PiperPlusSynthOptions *opts,
    PiperPlusAudioCallbackEx callback,
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
    PiperPlusStatus rc = piper_plus_synth_start(engine, text, opts);
    if (rc != PIPER_PLUS_OK) {
        return rc;
    }

    // Drive iterator, checking callback return value for abort
    try {
        PiperPlusAudioChunk chunk;
        for (;;) {
            rc = piper_plus_synth_next(engine, &chunk);

            if (rc == PIPER_PLUS_ERR) {
                return PIPER_PLUS_ERR;
            }

            // Deliver chunk via callback
            if (chunk.num_samples > 0) {
                int cbResult;
                try {
                    cbResult = callback(chunk.samples, chunk.num_samples,
                                        chunk.sample_rate, user_data);
                } catch (...) {
                    // Callback threw - clean up via finish()
                    engine->iterState.finish(engine->voice.synthesisConfig,
                                             engine->inProgress);
                    set_error("callback threw an exception");
                    return PIPER_PLUS_ERR;
                }

                // Caller requested abort
                if (cbResult != 0) {
                    // If synth_next already marked done, state is already cleaned up
                    if (rc != PIPER_PLUS_DONE) {
                        engine->iterState.finish(engine->voice.synthesisConfig,
                                                 engine->inProgress);
                    }
                    return PIPER_PLUS_OK;  // Not an error
                }
            }

            if (rc == PIPER_PLUS_DONE) {
                break;
            }
        }

        return PIPER_PLUS_OK;

    } catch (const std::exception &e) {
        set_error(e.what());
        engine->iterState.finish(engine->voice.synthesisConfig, engine->inProgress);
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error in synthesize_streaming_ex");
        engine->iterState.finish(engine->voice.synthesisConfig, engine->inProgress);
        return PIPER_PLUS_ERR;
    }
}

// ===== M4-1: Custom dictionary =====

PIPER_PLUS_API PiperPlusStatus piper_plus_load_custom_dict(
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

PIPER_PLUS_API PiperPlusStatus piper_plus_clear_custom_dict(PiperPlusEngine *engine) {
    if (!engine) { set_error("engine is NULL"); return PIPER_PLUS_ERR; }
    engine->customDict.reset();
    return PIPER_PLUS_OK;
}

PIPER_PLUS_API PiperPlusStatus piper_plus_add_dict_word(
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

PIPER_PLUS_API PiperPlusStatus piper_plus_get_phoneme_timing(
    PiperPlusEngine *engine, PiperPlusTimingResult *out_timing) {
    if (!engine) { set_error("engine is NULL"); return PIPER_PLUS_ERR; }
    if (!out_timing) { set_error("out_timing is NULL"); return PIPER_PLUS_ERR; }

    if (!engine->lastSynthResult.hasTimingInfo ||
        engine->lastSynthResult.phonemeTimings.empty()) {
        set_error("No timing information available (model may not support duration output)");
        out_timing->entries = nullptr;
        out_timing->count = 0;
        return PIPER_PLUS_ERR;
    }

    // Build C-compatible timing array (cached in engine state)
    const auto &timings = engine->lastSynthResult.phonemeTimings;

    engine->timingStrings.clear();
    engine->cachedTimings.clear();
    engine->timingStrings.reserve(timings.size());
    engine->cachedTimings.reserve(timings.size());

    for (const auto &t : timings) {
        engine->timingStrings.push_back(t.phoneme);
        PiperPlusPhonemeInfo info;
        info.phoneme = engine->timingStrings.back().c_str();
        info.start_time = t.start_time;
        info.end_time = t.end_time;
        engine->cachedTimings.push_back(info);
    }

    out_timing->entries = engine->cachedTimings.data();
    out_timing->count = static_cast<int32_t>(engine->cachedTimings.size());
    return PIPER_PLUS_OK;
}

// ===== M4-3: G2P / Phonemization =====

PIPER_PLUS_API PiperPlusStatus piper_plus_phonemize(
    PiperPlusEngine *engine, const char *text,
    const char *language, PiperPlusPhonemeResult *out_result) {
    if (!engine) { set_error("engine is NULL"); return PIPER_PLUS_ERR; }
    if (!text) { set_error("text is NULL"); return PIPER_PLUS_ERR_TEXT; }
    if (!out_result) { set_error("out_result is NULL"); return PIPER_PLUS_ERR; }

    try {
        BusyGuard busy(engine->inProgress);
        ConfigGuard cfgGuard(engine->voice.synthesisConfig);

        // Resolve explicit language to ID (affects defaultLatin selection inside phonemizeText)
        std::optional<int64_t> explicitLangId;
        if (language && language[0] != '\0' && engine->voice.modelConfig.languageIdMap) {
            auto it = engine->voice.modelConfig.languageIdMap->find(language);
            if (it != engine->voice.modelConfig.languageIdMap->end()) {
                explicitLangId = it->second;
                engine->voice.synthesisConfig.languageId = it->second;
            }
        }

        // Apply custom dictionary
        std::string processedText = text;
        if (engine->customDict) {
            processedText = engine->customDict->applyToText(processedText);
        }

        piper::PhonemizeResult phonResult;
        piper::phonemizeText(engine->voice, processedText, phonResult);

        // Determine effective language ID: explicit > auto-detected > current config
        std::optional<int64_t> effectiveLangId = explicitLangId;
        if (!effectiveLangId && phonResult.detectedLanguageId) {
            effectiveLangId = phonResult.detectedLanguageId;
        }
        if (!effectiveLangId) {
            effectiveLangId = engine->voice.synthesisConfig.languageId;
        }

        // Reverse-lookup language code from effective ID
        engine->g2pLanguage = "unknown";
        if (effectiveLangId && engine->voice.modelConfig.languageIdMap) {
            for (const auto &[code, id] : *engine->voice.modelConfig.languageIdMap) {
                if (id == *effectiveLangId) {
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

        out_result->phonemes = engine->g2pPhonemeStr.c_str();
        out_result->language = engine->g2pLanguage.c_str();
        out_result->num_phonemes = count;
        std::memset(out_result->_reserved, 0, sizeof(out_result->_reserved));

        return PIPER_PLUS_OK;

    } catch (const std::runtime_error &e) {
        if (std::string(e.what()) == "Engine is busy") {
            set_error("Engine is busy");
            return PIPER_PLUS_ERR_BUSY;
        }
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (const std::exception &e) {
        set_error(e.what());
        return PIPER_PLUS_ERR;
    } catch (...) {
        set_error("Unknown error in phonemize");
        return PIPER_PLUS_ERR;
    }
}

PIPER_PLUS_API const char *piper_plus_available_languages(PiperPlusEngine *engine) {
    if (!engine) return "";

    if (!engine->voice.modelConfig.languageIdMap) {
        engine->availableLanguagesStr = "";
        return engine->availableLanguagesStr.c_str();
    }

    // Sort language codes for deterministic output
    std::vector<std::string> codes;
    for (const auto &[code, id] : *engine->voice.modelConfig.languageIdMap) {
        codes.push_back(code);
    }
    std::sort(codes.begin(), codes.end());

    engine->availableLanguagesStr.clear();
    for (const auto &code : codes) {
        if (!engine->availableLanguagesStr.empty())
            engine->availableLanguagesStr += ',';
        engine->availableLanguagesStr += code;
    }
    return engine->availableLanguagesStr.c_str();
}

// ===== Speaker Encoder (EXPERIMENTAL -- not yet implemented) =====

struct PiperPlusSpeakerEncoder {
    // EXPERIMENTAL: Placeholder for speaker encoder ONNX session.
    // The API surface is reserved for forward compatibility.
    std::string model_path;
};

PIPER_PLUS_API PiperPlusSpeakerEncoder* piper_plus_speaker_encoder_create(
    const char *model_path)
{
    if (!model_path || model_path[0] == '\0') {
        set_error("model_path is NULL or empty");
        return nullptr;
    }

    // Verify file exists
    struct stat st;
    if (stat(model_path, &st) != 0) {
        set_error("Speaker encoder model not found: " + std::string(model_path));
        return nullptr;
    }

    try {
        auto encoder = new PiperPlusSpeakerEncoder();
        encoder->model_path = model_path;
        return encoder;
    } catch (const std::exception &e) {
        set_error(e.what());
        return nullptr;
    } catch (...) {
        set_error("Unknown error creating speaker encoder");
        return nullptr;
    }
}

PIPER_PLUS_API int32_t piper_plus_speaker_encoder_encode(
    PiperPlusSpeakerEncoder *encoder,
    const float *audio_samples,
    int32_t num_samples,
    int32_t sample_rate,
    float *embedding_out,
    int32_t embedding_dim)
{
    if (!encoder) {
        set_error("encoder is NULL");
        return -1;
    }
    if (!audio_samples || num_samples <= 0) {
        set_error("audio_samples is NULL or empty");
        return -1;
    }
    if (!embedding_out || embedding_dim <= 0) {
        set_error("embedding_out is NULL or embedding_dim <= 0");
        return -1;
    }
    if (sample_rate <= 0) {
        set_error("sample_rate must be positive");
        return -1;
    }

    // EXPERIMENTAL: Speaker encoder is not yet implemented in C API.
    // The API surface is reserved for forward compatibility.
    set_error("Speaker encoder is not yet implemented in C API");
    return -1;
}

PIPER_PLUS_API void piper_plus_speaker_encoder_destroy(
    PiperPlusSpeakerEncoder *encoder)
{
    if (encoder) {
        delete encoder;
    }
}

} // extern "C"
