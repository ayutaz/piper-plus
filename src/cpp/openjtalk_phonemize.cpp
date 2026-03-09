#include "openjtalk_phonemize.hpp"
#include "openjtalk_phonemize_utils.hpp"
#include <spdlog/spdlog.h>
#include <filesystem>
#include <cstdlib>
#include <sstream>
#include <memory>
#include <cstring>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace piper {

// Convert a string token to a PUA phoneme (char32_t)
static Phoneme toPuaPhoneme(const std::string& token) {
    auto it = phonemeToPua.find(token);
    if (it != phonemeToPua.end()) {
        return it->second;
    }
    if (token.length() == 1) {
        return static_cast<Phoneme>(token[0]);
    }
    // Unknown multi-character token
    spdlog::warn("Unknown multi-character phoneme in toPuaPhoneme: '{}'", token);
    return static_cast<Phoneme>('?');
}

void phonemize_openjtalk_with_prosody(
    const std::string &text,
    std::vector<std::vector<Phoneme>> &phonemes,
    std::vector<std::vector<ProsodyFeature>> &prosodyFeatures) {

    spdlog::debug("OpenJTalk phonemizer with prosody called with text: {}", text);
    phonemes.clear();
    prosodyFeatures.clear();

    if (!openjtalk_is_available()) {
        spdlog::warn("OpenJTalk is not available");
        return;
    }
    if (!openjtalk_ensure_dictionary()) {
        spdlog::error("Failed to ensure OpenJTalk dictionary");
        return;
    }

    // Get raw phonemes with prosody from OpenJTalk
    OpenJTalkProsodyResult* result = openjtalk_text_to_phonemes_with_prosody(text.c_str());
    if (!result) {
        spdlog::error("OpenJTalk failed to convert text with prosody");
        return;
    }

    // Pass 1: Collect raw phonemes with A1/A2/A3
    struct RawPhoneme {
        std::string phoneme;
        int a1, a2, a3;
    };
    std::vector<RawPhoneme> rawPhonemes;

    std::stringstream phonemeStream(std::string(result->phonemes));
    std::string phoneme;
    int phonemeIdx = 0;

    while (phonemeStream >> phoneme && phonemeIdx < result->count) {
        RawPhoneme rp;
        rp.phoneme = phoneme;
        rp.a1 = result->prosody_a1[phonemeIdx];
        rp.a2 = result->prosody_a2[phonemeIdx];
        rp.a3 = result->prosody_a3[phonemeIdx];
        rawPhonemes.push_back(rp);
        phonemeIdx++;
    }

    openjtalk_free_prosody_result(result);

    spdlog::debug("Collected {} raw phonemes", rawPhonemes.size());

    // Pass 2: Build sentence with BOS/EOS/prosody marks/N variants
    // Note: The C wrapper strips initial/final 'sil' from the label output,
    // so we unconditionally add BOS at the start and EOS at the end.
    std::vector<std::string> sentenceTokens;
    std::vector<ProsodyFeature> sentenceProsody;

    // Get question type from text
    std::string eosType = getQuestionType(text);
    spdlog::debug("getQuestionType('{}') = '{}'", text, eosType);

    // Add BOS unconditionally
    sentenceTokens.push_back("^");
    sentenceProsody.push_back({0, 0, 0});

    for (size_t i = 0; i < rawPhonemes.size(); i++) {
        const auto& rp = rawPhonemes[i];

        if (rp.phoneme == "sil") {
            // Sentence boundary within multi-sentence text
            // Finalize current sentence and start a new one
            if (sentenceTokens.size() > 1) { // More than just BOS
                sentenceTokens.push_back(eosType);
                sentenceProsody.push_back({0, 0, 0});

                // Apply N variant rules
                applyNPhonemeRules(sentenceTokens);

                // Convert to PUA and output
                std::vector<Phoneme> sentPhonemes;
                for (const auto& tok : sentenceTokens) {
                    sentPhonemes.push_back(toPuaPhoneme(tok));
                }
                phonemes.push_back(std::move(sentPhonemes));
                prosodyFeatures.push_back(std::move(sentenceProsody));

                // Start new sentence with BOS
                sentenceTokens.clear();
                sentenceProsody.clear();
                sentenceTokens.push_back("^");
                sentenceProsody.push_back({0, 0, 0});
            }
            continue;
        }

        if (rp.phoneme == "pau") {
            sentenceTokens.push_back("_");
            sentenceProsody.push_back({0, 0, 0});
            continue;
        }

        // Regular phoneme: insert prosody marks based on A2 lookahead
        int a1 = rp.a1;
        int a2 = rp.a2;
        int a3 = rp.a3;

        // Get A2 of the next phoneme (same as Python's labels[idx+1])
        int a2_next = -1;
        if (i + 1 < rawPhonemes.size()) {
            a2_next = rawPhonemes[i + 1].a2;
        }

        // Add the phoneme
        sentenceTokens.push_back(rp.phoneme);
        sentenceProsody.push_back({a1, a2, a3});

        // ]: Accent nucleus (falling pitch)
        if (a1 == 0 && a2_next == a2 + 1) {
            sentenceTokens.push_back("]");
            sentenceProsody.push_back({0, 0, 0});
        }

        // #: Accent phrase boundary
        if (a2 == a3 && a2_next == 1) {
            sentenceTokens.push_back("#");
            sentenceProsody.push_back({0, 0, 0});
        }

        // [: Pitch rise
        if (a2 == 1 && a2_next == 2) {
            sentenceTokens.push_back("[");
            sentenceProsody.push_back({0, 0, 0});
        }
    }

    // Finalize the last sentence (add EOS)
    if (sentenceTokens.size() > 1) { // More than just BOS
        sentenceTokens.push_back(eosType);
        sentenceProsody.push_back({0, 0, 0});

        applyNPhonemeRules(sentenceTokens);

        // Debug: dump final sentence tokens
        {
            std::string tokenDump;
            for (const auto& tok : sentenceTokens) {
                if (!tokenDump.empty()) tokenDump += " ";
                tokenDump += tok;
            }
            spdlog::debug("Final sentenceTokens: {}", tokenDump);
        }

        std::vector<Phoneme> sentPhonemes;
        for (const auto& tok : sentenceTokens) {
            sentPhonemes.push_back(toPuaPhoneme(tok));
        }
        phonemes.push_back(std::move(sentPhonemes));
        prosodyFeatures.push_back(std::move(sentenceProsody));
    }

    spdlog::debug("OpenJTalk phonemization with prosody complete: {} sentences", phonemes.size());
}

void phonemize_openjtalk(const std::string &text, std::vector<std::vector<Phoneme>> &phonemes) {
    spdlog::debug("OpenJTalk phonemizer called with text: {}", text);
    phonemes.clear();

    // Use prosody version and discard prosody data
    std::vector<std::vector<ProsodyFeature>> unusedProsody;
    phonemize_openjtalk_with_prosody(text, phonemes, unusedProsody);
}

} // namespace piper
