#include "openjtalk_phonemize.hpp"
#include "utf8.h"
#include "openjtalk_api.h"
#include <spdlog/spdlog.h>

namespace piper {

static bool oj_initialized = false;
static OpenJTalk *oj = nullptr;
static void ensure_init() {
  if (oj_initialized)
    return;
  oj_initialized = true;
  
  // Initialize OpenJTalk
  spdlog::info("Initializing OpenJTalk...");
  
  oj = openjtalk_initialize();
  if (!oj) {
    spdlog::error("Failed to initialize OpenJTalk; falling back to codepoints");
  }
}

// Convert string to phoneme (char32_t)
Phoneme mapPhonemeStr(const std::string &phonemeStr) {
  if (phonemeStr.empty()) return 0;
  
  auto it = phonemeStr.begin();
  return utf8::next(it, phonemeStr.end());
}

void phonemize_openjtalk(const std::string &text,
                         std::vector<std::vector<Phoneme>> &sentences) {
  spdlog::debug("phonemize_openjtalk called with text: {}", text);
  
  ensure_init();
  if (!oj) {
    spdlog::warn("OpenJTalk not initialized, using fallback codepoints");
    // Fallback: treat whole text as one sentence of codepoints
    std::vector<Phoneme> line;
    for (auto it = text.begin(); it != text.end(); ) {
      auto cp = utf8::next(it, text.end());
      line.push_back(cp);
    }
    sentences.push_back(line);
    return;
  }

  // Use OpenJTalk to extract full-context labels
  spdlog::debug("Extracting full-context labels from OpenJTalk");
  OJ_Label *labels = openjtalk_extract_fullcontext(oj, text.c_str());
  if (!labels) {
    spdlog::error("OpenJTalk failed to extract labels; using fallback codepoints");
    std::vector<Phoneme> line;
    for (auto it = text.begin(); it != text.end(); ) {
      auto cp = utf8::next(it, text.end());
      line.push_back(cp);
    }
    sentences.push_back(line);
    return;
  }

  std::vector<Phoneme> currentSentence;
  size_t num = OJ_Label_get_size(labels);
  spdlog::debug("OpenJTalk generated {} labels", num);
  
  for (size_t i = 0; i < num; ++i) {
    const char *label = OJ_Label_get_string(labels, i);
    std::string lab(label);
    spdlog::debug("Label[{}]: {}", i, lab);
    
    // simple parse: find between '-' and '+'
    auto pos1 = lab.find('-');
    auto pos2 = lab.find('+');
    if (pos1 == std::string::npos || pos2 == std::string::npos || pos2 <= pos1) {
      spdlog::debug("  -> Skipping, could not parse phoneme");
      continue;
    }
    
    std::string token = lab.substr(pos1 + 1, pos2 - pos1 - 1);
    spdlog::debug("  -> Extracted phoneme: '{}'", token);
    
    if (token == "sil" && i == 0) {
      spdlog::debug("  -> Mapped to '^' (sentence start)");
      currentSentence.push_back(mapPhonemeStr("^"));
      continue;
    }
    if (token == "sil") {
      spdlog::debug("  -> Mapped to '$' (sentence end)");
      currentSentence.push_back(mapPhonemeStr("$"));
      if (!currentSentence.empty()) {
        sentences.push_back(currentSentence);
        currentSentence.clear();
      }
      continue;
    }
    if (token == "pau") {
      spdlog::debug("  -> Mapped to '_' (pause)");
      currentSentence.push_back(mapPhonemeStr("_"));
      continue;
    }
    // devoiced vowels
    if (token.size() == 1 && std::isupper(token[0])) {
      char lower = std::tolower(token[0]);
      spdlog::debug("  -> Devoiced vowel '{}' converted to '{}'", token[0], lower);
      token[0] = lower;
    }

    Phoneme ph = mapPhonemeStr(token);
    spdlog::debug("  -> Mapped to phoneme value: {}", static_cast<uint32_t>(ph));
    currentSentence.push_back(ph);
  }
  
  if (!currentSentence.empty()) {
    sentences.push_back(currentSentence);
  }
  
  spdlog::debug("Total sentences: {}", sentences.size());
  for (size_t i = 0; i < sentences.size(); ++i) {
    spdlog::debug("Sentence {}: {} phonemes", i, sentences[i].size());
  }

  OJ_Label_clear(labels);
}

} 