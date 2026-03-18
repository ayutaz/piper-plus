#include "piper_engine.hpp"
#include "piper_jni_utils.h"
#include "piper.hpp"

#include <stdexcept>

PiperEngine::PiperEngine(const std::string &modelPath, const std::string &configPath) {
    config_ = std::make_unique<piper::PiperConfig>();
    voice_ = std::make_unique<piper::Voice>();

    piper::initialize(*config_);

    std::optional<piper::SpeakerId> speakerId;
    piper::loadVoice(*config_, modelPath, configPath, *voice_, speakerId,
                     /*useCuda=*/false, /*gpuDeviceId=*/0);

    PIPER_LOGI("Model loaded: %s (speakers=%d, languages=%d, sampleRate=%d)",
               modelPath.c_str(),
               voice_->modelConfig.numSpeakers,
               voice_->modelConfig.numLanguages,
               voice_->synthesisConfig.sampleRate);
}

PiperEngine::~PiperEngine() {
    if (config_) {
        piper::terminate(*config_);
    }
    PIPER_LOGI("PiperEngine destroyed");
}

std::vector<int16_t> PiperEngine::synthesize(const std::string &text,
                                              const std::string &language,
                                              int speakerId) {
    std::lock_guard<std::mutex> lock(synthMutex_);

    // Set speaker and language
    voice_->synthesisConfig.speakerId = static_cast<piper::SpeakerId>(speakerId);
    setLanguage(language);

    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;

    piper::textToAudio(*config_, *voice_, text, audioBuffer, result,
                       nullptr, nullptr);

    PIPER_LOGI("Synthesized: %.2fs audio in %.3fs (RTF=%.2f)",
               result.audioSeconds, result.inferSeconds, result.realTimeFactor);

    return audioBuffer;
}

void PiperEngine::synthesizeStreaming(
    const std::string &text,
    const std::string &language,
    int speakerId,
    const std::function<void(const std::vector<int16_t> &)> &chunkCallback,
    size_t chunkSize) {

    std::lock_guard<std::mutex> lock(synthMutex_);

    voice_->synthesisConfig.speakerId = static_cast<piper::SpeakerId>(speakerId);
    setLanguage(language);

    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;

    piper::textToAudioStreaming(*config_, *voice_, text, audioBuffer, result,
                                chunkCallback, chunkSize);

    PIPER_LOGI("Streaming synthesized: %.2fs audio in %.3fs",
               result.audioSeconds, result.inferSeconds);
}

int PiperEngine::getSampleRate() const {
    return voice_ ? voice_->synthesisConfig.sampleRate : 22050;
}

int PiperEngine::getNumSpeakers() const {
    return voice_ ? voice_->modelConfig.numSpeakers : 0;
}

int PiperEngine::getNumLanguages() const {
    return voice_ ? voice_->modelConfig.numLanguages : 1;
}

void PiperEngine::setLanguage(const std::string &language) {
    if (language.empty()) return;

    auto &langMap = voice_->modelConfig.languageIdMap;
    if (langMap.has_value()) {
        auto it = langMap->find(language);
        if (it != langMap->end()) {
            voice_->synthesisConfig.languageId = it->second;
        } else {
            PIPER_LOGW("Language '%s' not found in model, using default", language.c_str());
        }
    }
}
