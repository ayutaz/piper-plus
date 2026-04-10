#ifndef PIPER_H_
#define PIPER_H_

#include <fstream>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include <onnxruntime_cxx_api.h>

// Self-contained phoneme types.
// Provides: Phoneme (char32_t), PhonemeId (int64_t), PhonemeIdMap, PhonemeIdConfig
#include "phoneme_ids.hpp"

#include "json.hpp"

namespace piper {

typedef int64_t SpeakerId;
typedef int64_t LanguageId;

struct PiperConfig {
  // No external dependencies needed for MultilingualPhonemes
};

enum PhonemeType {
  OpenJTalkPhonemes,
  MultilingualPhonemes
};

// Helper: true for phoneme types that use OpenJTalk-based phonemization
inline bool usesOpenJTalk(PhonemeType type) {
  return type == OpenJTalkPhonemes || type == MultilingualPhonemes;
}

// Prosody info for a phoneme (A1/A2/A3 values from OpenJTalk)
struct ProsodyFeature {
    int a1;  // Relative position from accent nucleus
    int a2;  // Position in accent phrase (1-based)
    int a3;  // Total morae in accent phrase
};

struct PhonemizeConfig {
  PhonemeType phonemeType = MultilingualPhonemes;
  std::optional<std::map<Phoneme, std::vector<Phoneme>>> phonemeMap;
  std::map<Phoneme, std::vector<PhonemeId>> phonemeIdMap;

  PhonemeId idPad = 0; // padding (optionally interspersed)
  PhonemeId idBos = 1; // beginning of sentence
  PhonemeId idEos = 2; // end of sentence
  bool interspersePad = true;
};

struct SynthesisConfig {
  // VITS inference settings
  float noiseScale = 0.667f;
  float lengthScale = 1.0f;
  float noiseW = 0.8f;

  // Audio settings
  int sampleRate = 22050;
  int sampleWidth = 2; // 16-bit
  int channels = 1;    // mono

  // Speaker id from 0 to numSpeakers - 1
  std::optional<SpeakerId> speakerId;

  // Language id from 0 to numLanguages - 1
  std::optional<LanguageId> languageId;

  // Extra silence
  float sentenceSilenceSeconds = 0.2f;
  std::optional<std::map<piper::Phoneme, float>> phonemeSilenceSeconds;

  // Voice cloning: speaker embedding from speaker encoder (M3-04).
  // When non-empty, passed as the speaker_embedding ONNX input with mask=1.
  std::vector<float> speakerEmbedding;
};

struct ModelConfig {
  int numSpeakers = 0;
  int numLanguages = 1;

  // speaker name -> id
  std::optional<std::map<std::string, SpeakerId>> speakerIdMap;

  // language code -> id (e.g. "ja" -> 0, "en" -> 1)
  std::optional<std::map<std::string, LanguageId>> languageIdMap;
};

struct ModelSession {
  Ort::Session onnx;
  Ort::AllocatorWithDefaultOptions allocator;
  Ort::SessionOptions options;
  Ort::Env env;
  bool hasDurationOutput = false;  // Whether model outputs duration information
  bool hasProsodyInput = false;    // Whether model accepts prosody_features input
  bool hasMultiSpeaker = false;    // Whether model has sid (speaker ID) input
  bool hasLidInput = false;        // Whether model has lid (language ID) input

  ModelSession() : onnx(nullptr){};
};

// Collects all inputs needed to build ONNX tensors for VITS inference.
// Used by synthesize(), synthesizeFloat(), and warmupModel() to avoid
// duplicating tensor-construction logic.
struct InferenceInputs {
  std::vector<int64_t> phonemeIds;
  float noiseScale  = 0.667f;
  float lengthScale = 1.0f;
  float noiseW      = 0.8f;
  std::optional<int64_t> speakerId;
  std::optional<int64_t> languageId;
  // Flat [a1,a2,a3, a1,a2,a3, ...] per phoneme. Empty = no prosody.
  std::vector<int64_t> prosodyFeatures;
};

struct PhonemeInfo {
  std::string phoneme;     // Phoneme string
  float start_time;        // Start time in seconds
  float end_time;          // End time in seconds
  int start_frame;         // Start frame index
  int end_frame;           // End frame index
};

struct SynthesisResult {
  double inferSeconds = 0.0;
  double audioSeconds = 0.0;
  double realTimeFactor = 0.0;
  std::vector<PhonemeInfo> phonemeTimings;  // Phoneme timing information
  bool hasTimingInfo = false;                // Whether timing info is available
};

struct Voice {
  nlohmann::json configRoot;
  PhonemizeConfig phonemizeConfig;
  SynthesisConfig synthesisConfig;
  ModelConfig modelConfig;
  ModelSession session;

  // Multilingual dictionary data (loaded on demand)
  std::unordered_map<std::string, std::string> cmuDict;
  std::unordered_map<int, std::string> pinyinSingleDict;
  std::unordered_map<std::string, std::string> pinyinPhraseDict;
};

// True if the string is a single UTF-8 codepoint
bool isSingleCodepoint(std::string s);

// Get the first UTF-8 codepoint of a string
Phoneme getCodepoint(std::string s);

// Get version of Piper
std::string getVersion();

// Must be called before using textTo* functions
void initialize(PiperConfig &config);

// Clean up
void terminate(PiperConfig &config);

// Load Onnx model and JSON config file
void loadVoice(PiperConfig &config, std::string modelPath,
               std::string modelConfigPath, Voice &voice,
               std::optional<SpeakerId> &speakerId,
               const std::string &provider = "cpu",
               int gpuDeviceId = 0, int numThreads = 0);

/// Warm up the ONNX session with dummy inference runs.
/// Reduces first-inference latency by 500-800ms.
/// Any exception is caught and logged as a warning (non-fatal).
void warmupModel(ModelSession &session, int runs = 2);

// Phonemize text and synthesize audio
void textToAudio(PiperConfig &config, Voice &voice, std::string text,
                 std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                 const std::function<void()> &audioCallback,
                 const std::vector<ProsodyFeature> *externalProsody = nullptr);

// Float32 output variant — avoids int16 intermediate conversion.
// Audio samples are normalized to [-1.0, 1.0].
void textToAudioFloat(PiperConfig &config, Voice &voice, std::string text,
                      std::vector<float> &audioBuffer, SynthesisResult &result,
                      const std::function<void()> &audioCallback = nullptr,
                      const std::vector<ProsodyFeature> *externalProsody = nullptr);

// Phonemize text and synthesize audio to WAV file
void textToWavFile(PiperConfig &config, Voice &voice, std::string text,
                   std::ostream &audioFile, SynthesisResult &result,
                   const std::vector<ProsodyFeature> *externalProsody = nullptr);

// Synthesize audio directly from phonemes
void phonemesToAudio(PiperConfig &config, Voice &voice, 
                     const std::vector<Phoneme> &phonemes,
                     std::vector<int16_t> &audioBuffer, 
                     SynthesisResult &result,
                     const std::function<void()> &audioCallback = nullptr);

// Synthesize audio directly from phonemes to WAV file
void phonemesToWavFile(PiperConfig &config, Voice &voice,
                       const std::vector<Phoneme> &phonemes,
                       std::ostream &audioFile, SynthesisResult &result);

// Streaming text-to-audio synthesis with reduced latency
void textToAudioStreaming(PiperConfig &config, Voice &voice, std::string text,
                          std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                          const std::function<void(const std::vector<int16_t>&)> &chunkCallback,
                          size_t chunkSize = 4096);

// Streaming phonemes-to-audio synthesis with reduced latency
void phonemesToAudioStreaming(PiperConfig &config, Voice &voice,
                              const std::vector<Phoneme> &phonemes,
                              std::vector<int16_t> &audioBuffer,
                              SynthesisResult &result,
                              const std::function<void(const std::vector<int16_t>&)> &chunkCallback,
                              size_t phonemesPerChunk = 10);

// Output phoneme timing information as JSON
void outputTimingsAsJSON(const std::vector<PhonemeInfo> &timings,
                         std::ostream &output,
                         const std::string &text = "",
                         int sampleRate = 22050);

// Output phoneme timing information as TSV
void outputTimingsAsTSV(const std::vector<PhonemeInfo> &timings,
                        std::ostream &output);

// Phonemize result (extracted from textToAudio)
struct PhonemizeResult {
    std::vector<std::vector<Phoneme>> phonemes;        // Phonemes per sentence
    std::vector<std::vector<ProsodyFeature>> prosody;   // Prosody per sentence (optional)
    std::optional<int64_t> detectedLanguageId;          // Auto-detected dominant language ID
};

/// Phonemize text into per-sentence phoneme sequences.
/// Pure: does not modify voice.  Auto-detected language is returned
/// in result.detectedLanguageId.
void phonemizeText(const Voice &voice, const std::string &text,
                   PhonemizeResult &result,
                   const std::vector<ProsodyFeature> *externalProsody = nullptr);

/// Split text into sentences at natural boundaries.
/// @param phonemeType  Used to select Japanese vs English regex
/// @param maxChunkSize Maximum chunk size (0 = default 50)
std::vector<std::string> splitTextToSentences(
    const std::string &text,
    PhonemeType phonemeType,
    size_t maxChunkSize = 0);

} // namespace piper

#endif // PIPER_H_
