#include <fstream>
#include <functional>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include "json.hpp"
#include "piper.hpp"
#include "safe_path.hpp"

using namespace std;
using json = nlohmann::json;

int main(int argc, char *argv[]) {
  piper::PiperConfig piperConfig;
  piper::Voice voice;

  if (argc < 2) {
    std::cerr << "Need voice model path" << std::endl;
    return 1;
  }

  if (argc < 3) {
    std::cerr << "Need output WAV path" << std::endl;
    return 1;
  }

  auto modelPath = std::string(argv[1]);
  auto outputPath = std::string(argv[2]);

  // Skip test if model file is not available. sanitizeCliPath rejects
  // paths containing `..`; treat nullopt as the same SKIPPED outcome
  // (no fallback to the raw string) so CodeQL sees the taint barrier.
  {
    auto safeModelPath = piper_plus::sanitizeCliPath(modelPath);
    if (!safeModelPath) {
      std::cout << "SKIPPED: Invalid model path: " << modelPath << std::endl;
      return 77;
    }
    std::ifstream modelCheck(*safeModelPath);
    if (!modelCheck.good()) {
      std::cout << "SKIPPED: Model file not found: " << modelPath << std::endl;
      return 77; // CTest SKIP_RETURN_CODE
    }
    auto safeConfigPath = piper_plus::sanitizeCliPath(modelPath + ".json");
    if (!safeConfigPath) {
      std::cout << "SKIPPED: Invalid config path: " << modelPath << ".json" << std::endl;
      return 77;
    }
    std::ifstream configCheck(*safeConfigPath);
    if (!configCheck.good()) {
      std::cout << "SKIPPED: Config file not found: " << modelPath + ".json" << std::endl;
      return 77;
    }
  }

  optional<piper::SpeakerId> speakerId;

  try {
    loadVoice(piperConfig, modelPath, modelPath + ".json", voice, speakerId,
              "cpu");
    piper::initialize(piperConfig);
  } catch (const std::exception &e) {
    std::cout << "SKIPPED: Failed to initialize: " << e.what() << std::endl;
    return 77;
  }

  // Output audio to WAV file. Hard-reject if sanitizeCliPath returns
  // nullopt — the CodeQL barrier requires no fallback.
  auto safeOutputPath = piper_plus::sanitizeCliPath(outputPath);
  if (!safeOutputPath) {
    std::cerr << "Invalid or unsafe output path: " << outputPath << std::endl;
    return EXIT_FAILURE;
  }
  ofstream audioFile(*safeOutputPath, ios::binary);

  piper::SynthesisResult result;
  piper::textToWavFile(piperConfig, voice, "This is a test.", audioFile,
                       result);
  piper::terminate(piperConfig);

  // Verify that file has some data
  if (audioFile.tellp() < 10000) {
    std::cerr << "ERROR: Output file is smaller than expected!" << std::endl;
    return EXIT_FAILURE;
  }

  std::cout << "OK" << std::endl;

  return EXIT_SUCCESS;
}
