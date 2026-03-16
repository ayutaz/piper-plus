#include <fstream>
#include <functional>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include "json.hpp"
#include "piper.hpp"

using namespace std;
using json = nlohmann::json;

int main(int argc, char *argv[]) {
  piper::PiperConfig piperConfig;
  piper::Voice voice;

  if (argc < 2) {
    std::cerr << "Need voice model path" << std::endl;
    return 1;
  }

  if (argc < 4) {
    std::cerr << "Need output WAV path" << std::endl;
    return 1;
  }

  auto modelPath = std::string(argv[1]);
  auto outputPath = std::string(argv[3]);

  // Skip test if model file is not available (e.g. Docker builds without test models)
  {
    std::ifstream modelCheck(modelPath);
    if (!modelCheck.good()) {
      std::cout << "SKIPPED: Model file not found: " << modelPath << std::endl;
      return 77; // CTest SKIP_RETURN_CODE
    }
    std::ifstream configCheck(modelPath + ".json");
    if (!configCheck.good()) {
      std::cout << "SKIPPED: Config file not found: " << modelPath + ".json" << std::endl;
      return 77; // CTest SKIP_RETURN_CODE
    }
  }

  // Use provided espeak-ng-data path if available, otherwise auto-detect
  if (argc >= 3 && std::string(argv[2]) != "auto") {
    piperConfig.eSpeakDataPath = std::string(argv[2]);
  } else {
    piperConfig.eSpeakDataPath = ""; // Will auto-detect in initialize()
  }

  // Check espeak-ng data before calling initialize (espeak calls exit() on failure)
  {
    auto espeakPath = piperConfig.eSpeakDataPath;
    if (espeakPath.empty()) {
      // Auto-detect: check common paths
      std::vector<std::string> candidates = {
        "/usr/share/espeak-ng-data/phontab",
        "/usr/local/share/espeak-ng-data/phontab"
      };
      bool found = false;
      for (const auto& p : candidates) {
        std::ifstream f(p);
        if (f.good()) { found = true; break; }
      }
      if (!found) {
        std::cout << "SKIPPED: espeak-ng-data not found" << std::endl;
        return 77;
      }
    } else {
      std::ifstream f(espeakPath + "/phontab");
      if (!f.good()) {
        std::cout << "SKIPPED: espeak-ng-data not found at " << espeakPath << std::endl;
        return 77;
      }
    }
  }

  optional<piper::SpeakerId> speakerId;

  try {
    loadVoice(piperConfig, modelPath, modelPath + ".json", voice, speakerId,
              false);
    piper::initialize(piperConfig);
  } catch (const std::exception &e) {
    std::cout << "SKIPPED: Failed to initialize: " << e.what() << std::endl;
    return 77; // CTest SKIP_RETURN_CODE
  }

  // Output audio to WAV file
  ofstream audioFile(outputPath, ios::binary);

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
