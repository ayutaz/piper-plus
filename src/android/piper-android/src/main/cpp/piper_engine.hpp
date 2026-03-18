#ifndef PIPER_ENGINE_HPP_
#define PIPER_ENGINE_HPP_

#include <string>
#include <vector>
#include <functional>
#include <mutex>
#include <memory>
#include <cstdint>

// Forward declarations from piper
namespace piper {
struct PiperConfig;
struct Voice;
struct SynthesisResult;
} // namespace piper

/**
 * High-level wrapper around the piper C++ core for JNI usage.
 * Thread-safe: all synthesis operations are serialized via mutex.
 */
class PiperEngine {
public:
    /**
     * Create engine and load model.
     * @param modelPath  Path to ONNX model file
     * @param configPath Path to config.json file
     * @throws std::runtime_error on load failure
     */
    PiperEngine(const std::string &modelPath, const std::string &configPath);

    ~PiperEngine();

    // Non-copyable, non-movable
    PiperEngine(const PiperEngine &) = delete;
    PiperEngine &operator=(const PiperEngine &) = delete;
    PiperEngine(PiperEngine &&) = delete;
    PiperEngine &operator=(PiperEngine &&) = delete;

    /**
     * Synthesize text to audio samples.
     * @param text      Input text
     * @param language  Language code (e.g. "ja", "en", "zh", "es", "fr", "pt")
     * @param speakerId Speaker ID (0 for single-speaker models)
     * @return PCM audio samples (16-bit signed, mono, 22050 Hz)
     */
    std::vector<int16_t> synthesize(const std::string &text,
                                    const std::string &language,
                                    int speakerId);

    /**
     * Streaming synthesis with chunk callback.
     * @param text          Input text
     * @param language      Language code
     * @param speakerId     Speaker ID
     * @param chunkCallback Called for each audio chunk
     * @param chunkSize     Samples per chunk (default: 4096)
     */
    void synthesizeStreaming(
        const std::string &text, const std::string &language, int speakerId,
        const std::function<void(const std::vector<int16_t> &)> &chunkCallback,
        size_t chunkSize = 4096);

    /** Get sample rate (typically 22050). */
    int getSampleRate() const;

    /** Get number of speakers in the model. */
    int getNumSpeakers() const;

    /** Get number of languages in the model. */
    int getNumLanguages() const;

private:
    /**
     * Set the language on the voice's synthesisConfig.
     * Looks up the language code in the model's languageIdMap.
     * @param language Language code (e.g. "ja", "en")
     */
    void setLanguage(const std::string &language);

    std::unique_ptr<piper::PiperConfig> config_;
    std::unique_ptr<piper::Voice> voice_;
    mutable std::mutex synthMutex_; // Serialize synthesis calls
};

#endif // PIPER_ENGINE_HPP_
