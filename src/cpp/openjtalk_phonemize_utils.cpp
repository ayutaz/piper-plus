#include "openjtalk_phonemize_utils.hpp"
#include <unordered_set>

namespace piper {

// Convert OpenJTalk phonemes to PUA characters for multi-phoneme support
// This MUST match the Python implementation in jp_id_map.py exactly
const std::unordered_map<std::string, char32_t> phonemeToPua = {
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
std::string getQuestionType(const std::string& text) {
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
bool isSpecialToken(const std::string& token) {
    static const std::unordered_set<std::string> specialTokens = {
        "_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"
    };
    return specialTokens.count(token) > 0;
}

// Apply context-dependent N phoneme rules (matches Python _apply_n_phoneme_rules)
void applyNPhonemeRules(std::vector<std::string>& tokens) {
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

} // namespace piper
