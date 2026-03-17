// Self-contained phoneme-to-ID conversion.
// Replaces piper-phonemize/phoneme_ids.hpp to eliminate the header dependency.
// The logic is a direct port of the original piper-phonemize implementation.

#ifndef PIPER_PHONEME_IDS_HPP
#define PIPER_PHONEME_IDS_HPP

#include <cstdint>
#include <map>
#include <memory>
#include <vector>

#include "phoneme_parser.hpp" // piper::Phoneme = char32_t

namespace piper {

typedef int64_t PhonemeId;
typedef std::map<Phoneme, std::vector<PhonemeId>> PhonemeIdMap;

struct PhonemeIdConfig {
  Phoneme pad = U'_';
  Phoneme bos = U'^';
  Phoneme eos = U'$';

  bool interspersePad = true;
  bool addBos = true;
  bool addEos = true;

  // Phoneme ID map loaded from the model's config.json.
  std::shared_ptr<PhonemeIdMap> phonemeIdMap;
};

// Convert a vector of phoneme codepoints to phoneme IDs using the provided map.
// Optionally adds BOS/EOS symbols and inter-phoneme padding.
// Missing phonemes are tracked in `missingPhonemes` (phoneme -> count).
inline void phonemes_to_ids(const std::vector<Phoneme> &phonemes,
                            PhonemeIdConfig &config,
                            std::vector<PhonemeId> &phonemeIds,
                            std::map<Phoneme, std::size_t> &missingPhonemes) {
  if (!config.phonemeIdMap) {
    return;
  }

  auto &idMap = *config.phonemeIdMap;

  // BOS
  if (config.addBos) {
    auto it = idMap.find(config.bos);
    if (it != idMap.end()) {
      phonemeIds.insert(phonemeIds.end(), it->second.begin(), it->second.end());
      if (config.interspersePad) {
        auto padIt = idMap.find(config.pad);
        if (padIt != idMap.end()) {
          phonemeIds.insert(phonemeIds.end(), padIt->second.begin(),
                            padIt->second.end());
        }
      }
    }
  }

  // Phonemes (with or without inter-phoneme padding)
  if (config.interspersePad) {
    auto padIt = idMap.find(config.pad);
    for (auto phoneme : phonemes) {
      auto it = idMap.find(phoneme);
      if (it == idMap.end()) {
        missingPhonemes[phoneme]++;
        continue;
      }
      phonemeIds.insert(phonemeIds.end(), it->second.begin(),
                        it->second.end());
      if (padIt != idMap.end()) {
        phonemeIds.insert(phonemeIds.end(), padIt->second.begin(),
                          padIt->second.end());
      }
    }
  } else {
    for (auto phoneme : phonemes) {
      auto it = idMap.find(phoneme);
      if (it == idMap.end()) {
        missingPhonemes[phoneme]++;
        continue;
      }
      phonemeIds.insert(phonemeIds.end(), it->second.begin(),
                        it->second.end());
    }
  }

  // EOS
  if (config.addEos) {
    auto it = idMap.find(config.eos);
    if (it != idMap.end()) {
      phonemeIds.insert(phonemeIds.end(), it->second.begin(),
                        it->second.end());
    }
  }
}

} // namespace piper

#endif // PIPER_PHONEME_IDS_HPP
