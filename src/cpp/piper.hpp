#ifndef PIPER_H_
#define PIPER_H_

#include <fstream>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include <onnxruntime_cxx_api.h>
#include <piper-phonemize/phoneme_ids.hpp>
#include <piper-phonemize/phonemize.hpp>
#include <piper-phonemize/tashkeel.hpp>

#include "json.hpp"

using json = nlohmann::json;

namespace piper {

typedef int64_t SpeakerId;

struct eSpeakConfig {
  std::string voice = "en-us";
};

struct PiperConfig {
  std::string eSpeakDataPath;
  bool useESpeak = true;

  bool useTashkeel = false;
  std::optional<std::string> tashkeelModelPath;
  std::unique_ptr<tashkeel::State> tashkeelState;
};

enum PhonemeType {
  eSpeakPhonemes,
  TextPhonemes,
  OpenJTalkPhonemes
};

// Prosody info for a phoneme (A1/A2/A3 values from OpenJTalk)
struct ProsodyFeature {
    int a1;  // Relative position from accent nucleus
    int a2;  // Position in accent phrase (1-based)
    int a3;  // Total morae in accent phrase
};

struct PhonemizeConfig {
  PhonemeType phonemeType = eSpeakPhonemes;
  std::optional<std::map<Phoneme, std::vector<Phoneme>>> phonemeMap;
  std::map<Phoneme, std::vector<PhonemeId>> phonemeIdMap;

  PhonemeId idPad = 0; // padding (optionally interspersed)
  PhonemeId idBos = 1; // beginning of sentence
  PhonemeId idEos = 2; // end of sentence
  bool interspersePad = true;

  eSpeakConfig eSpeak;
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

  // Extra silence
  float sentenceSilenceSeconds = 0.2f;
  std::optional<std::map<piper::Phoneme, float>> phonemeSilenceSeconds;
};

struct ModelConfig {
  int numSpeakers;

  // speaker name -> id
  std::optional<std::map<std::string, SpeakerId>> speakerIdMap;
};

struct ModelSession {
  Ort::Session onnx;
  Ort::AllocatorWithDefaultOptions allocator;
  Ort::SessionOptions options;
  Ort::Env env;
  bool hasDurationOutput = false;  // Whether model outputs duration information
  bool hasProsodyInput = false;    // Whether model accepts prosody_features input
  bool hasMultiSpeaker = false;    // Whether model has sid (speaker ID) input

  ModelSession() : onnx(nullptr){};
};

struct PhonemeInfo {
  std::string phoneme;     // Phoneme string
  float start_time;        // Start time in seconds
  float end_time;          // End time in seconds
  int start_frame;         // Start frame index
  int end_frame;           // End frame index
};

struct SynthesisResult {
  double inferSeconds;
  double audioSeconds;
  double realTimeFactor;
  std::vector<PhonemeInfo> phonemeTimings;  // Phoneme timing information
  bool hasTimingInfo = false;                // Whether timing info is available
};

struct Voice {
  json configRoot;
  PhonemizeConfig phonemizeConfig;
  SynthesisConfig synthesisConfig;
  ModelConfig modelConfig;
  ModelSession session;
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
               std::optional<SpeakerId> &speakerId, bool useCuda,
               int gpuDeviceId = 0);

// Phonemize text and synthesize audio
void textToAudio(PiperConfig &config, Voice &voice, std::string text,
                 std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                 const std::function<void()> &audioCallback,
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

} // namespace piper

#endif // PIPER_H_
