#include "openjtalk_phonemize.hpp"
#include <spdlog/spdlog.h>
#include <filesystem>
#include <cstdlib>
#include <sstream>
#include <memory>
#include <cstring>
#include <unordered_set>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace piper {

// Convert OpenJTalk phonemes to PUA characters for multi-phoneme support
// This MUST match the Python implementation in jp_id_map.py exactly
static const std::unordered_map<std::string, char32_t> phonemeToPua = {
    // Long vowels (matches Python order)
    {"a:", 0xE000}, {"i:", 0xE001}, {"u:", 0xE002}, {"e:", 0xE003}, {"o:", 0xE004},
    // Special consonants
    {"cl", 0xE005}, // 促音/終止閉鎖
    // Palatalized consonants - matches Python order exactly
    {"ky", 0xE006}, {"kw", 0xE007}, {"gy", 0xE008}, {"gw", 0xE009},
    {"ty", 0xE00A}, {"dy", 0xE00B}, {"py", 0xE00C}, {"by", 0xE00D},
    {"ch", 0xE00E}, {"ts", 0xE00F}, {"sh", 0xE010},
    {"zy", 0xE011}, {"hy", 0xE012}, {"ny", 0xE013},
    {"my", 0xE014}, {"ry", 0xE015},
    // Question type markers (Issue #204)
    {"?!", 0xE016}, {"?.", 0xE017}, {"?~", 0xE018},
    // N phoneme variants (Issue #207)
    {"N_m", 0xE019}, {"N_n", 0xE01A}, {"N_ng", 0xE01B}, {"N_uvular", 0xE01C}
    // Note: N, q, j are single characters and don't need PUA mapping
};

// Determine question type from the text ending (matches Python _get_question_type)
static std::string getQuestionType(const std::string& text) {
    // Strip trailing whitespace
    std::string stripped = text;
    while (!stripped.empty() && (stripped.back() == ' ' || stripped.back() == '\n' || stripped.back() == '\r' || stripped.back() == '\t')) {
        stripped.pop_back();
    }
    if (stripped.empty()) return "$";

    auto endsWith = [&](const std::string& suffix) -> bool {
        if (stripped.size() < suffix.size()) return false;
        return stripped.compare(stripped.size() - suffix.size(), suffix.size(), suffix) == 0;
    };

    // Emphatic question: ?! or !? or ？！ or ！？
    if (endsWith("?!") || endsWith("!?") ||
        endsWith("\xEF\xBC\x9F\xEF\xBC\x81") ||  // ？！
        endsWith("\xEF\xBC\x81\xEF\xBC\x9F")) {   // ！？
        return "?!";
    }
    // Neutral/rhetorical question: ?. or 。？ or ？。
    if (endsWith("?.") ||
        endsWith("\xE3\x80\x82\xEF\xBC\x9F") ||   // 。？
        endsWith("\xEF\xBC\x9F\xE3\x80\x82")) {    // ？。
        return "?.";
    }
    // Tag question: ?~ or ～？ or ？～
    if (endsWith("?~") ||
        endsWith("\xEF\xBD\x9E\xEF\xBC\x9F") ||   // ～？
        endsWith("\xEF\xBC\x9F\xEF\xBD\x9E")) {    // ？～
        return "?~";
    }

    // Simple question: ? or ？
    if (endsWith("?") || endsWith("\xEF\xBC\x9F")) {  // ？
        return "?";
    }

    return "$";  // Declarative (non-question)
}

// Check if a token is a special/prosody token (should be skipped for N-variant lookahead)
static bool isSpecialToken(const std::string& token) {
    static const std::unordered_set<std::string> specialTokens = {
        "_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"
    };
    return specialTokens.count(token) > 0;
}

// Apply context-dependent N phoneme rules (matches Python _apply_n_phoneme_rules)
static void applyNPhonemeRules(std::vector<std::string>& tokens) {
    static const std::unordered_set<std::string> bilabial = {"m", "my", "b", "by", "p", "py"};
    static const std::unordered_set<std::string> alveolar = {"n", "ny", "t", "ty", "d", "dy", "ts", "ch"};
    static const std::unordered_set<std::string> velar = {"k", "ky", "kw", "g", "gy", "gw"};

    for (size_t i = 0; i < tokens.size(); i++) {
        if (tokens[i] != "N") continue;

        // Find the next real phoneme (skip special tokens)
        std::string nextReal;
        for (size_t j = i + 1; j < tokens.size(); j++) {
            if (!isSpecialToken(tokens[j])) {
                nextReal = tokens[j];
                break;
            }
        }

        if (nextReal.empty()) {
            tokens[i] = "N_uvular";  // End of phrase
        } else if (bilabial.count(nextReal)) {
            tokens[i] = "N_m";
        } else if (alveolar.count(nextReal)) {
            tokens[i] = "N_n";
        } else if (velar.count(nextReal)) {
            tokens[i] = "N_ng";
        } else {
            tokens[i] = "N_uvular";  // Vowels, other consonants
        }
    }
}

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
