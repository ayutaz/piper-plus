#include <emscripten.h>
#include <emscripten/bind.h>
#include <string>
#include <vector>
#include <memory>
#include <iostream>

// Simplified MeCab implementation for prototype
class SimpleMeCab {
private:
    struct Token {
        std::string surface;
        std::string features;
        std::string reading;
    };
    
    std::vector<Token> dictionary;
    bool initialized = false;

public:
    SimpleMeCab() {}
    
    bool initialize(const std::string& dictPath) {
        try {
            // In a real implementation, load dictionary from file
            // For prototype, use hardcoded entries
            dictionary.push_back({"こんにちは", "感動詞,*,*,*,*,*,こんにちは,コンニチハ,コンニチワ", "コンニチハ"});
            dictionary.push_back({"世界", "名詞,一般,*,*,*,*,世界,セカイ,セカイ", "セカイ"});
            dictionary.push_back({"今日", "名詞,副詞可能,*,*,*,*,今日,キョウ,キョー", "キョウ"});
            dictionary.push_back({"は", "助詞,係助詞,*,*,*,*,は,ハ,ワ", "ハ"});
            dictionary.push_back({"良い", "形容詞,自立,*,*,形容詞・イイ,基本形,良い,ヨイ,ヨイ", "ヨイ"});
            dictionary.push_back({"天気", "名詞,一般,*,*,*,*,天気,テンキ,テンキ", "テンキ"});
            dictionary.push_back({"です", "助動詞,*,*,*,特殊・デス,基本形,です,デス,デス", "デス"});
            dictionary.push_back({"ね", "助詞,終助詞,*,*,*,*,ね,ネ,ネ", "ネ"});
            
            initialized = true;
            std::cout << "SimpleMeCab initialized with " << dictionary.size() << " entries" << std::endl;
            return true;
        } catch (const std::exception& e) {
            std::cerr << "Initialization failed: " << e.what() << std::endl;
            return false;
        }
    }
    
    std::string parse(const std::string& text) {
        if (!initialized) {
            return "ERROR: Not initialized";
        }
        
        std::string result;
        std::string remaining = text;
        
        while (!remaining.empty()) {
            bool found = false;
            
            // Try to match longest token first
            for (size_t len = remaining.length(); len > 0; len--) {
                std::string substr = remaining.substr(0, len);
                
                for (const auto& token : dictionary) {
                    if (token.surface == substr) {
                        result += token.surface + "\t" + token.features + "\n";
                        remaining = remaining.substr(len);
                        found = true;
                        break;
                    }
                }
                
                if (found) break;
            }
            
            // If no match found, treat first character as unknown
            if (!found) {
                std::string unknown = remaining.substr(0, 3); // UTF-8 character
                result += unknown + "\t名詞,サ変接続,*,*,*,*,*\n";
                remaining = remaining.substr(unknown.length());
            }
        }
        
        result += "EOS\n";
        return result;
    }
    
    std::string wakati(const std::string& text) {
        if (!initialized) {
            return "ERROR: Not initialized";
        }
        
        std::string result;
        std::string remaining = text;
        
        while (!remaining.empty()) {
            bool found = false;
            
            // Try to match longest token first
            for (size_t len = remaining.length(); len > 0; len--) {
                std::string substr = remaining.substr(0, len);
                
                for (const auto& token : dictionary) {
                    if (token.surface == substr) {
                        result += token.surface + " ";
                        remaining = remaining.substr(len);
                        found = true;
                        break;
                    }
                }
                
                if (found) break;
            }
            
            // If no match found, treat first character as unknown
            if (!found) {
                std::string unknown = remaining.substr(0, 3); // UTF-8 character
                result += unknown + " ";
                remaining = remaining.substr(unknown.length());
            }
        }
        
        return result;
    }
    
    std::string getReading(const std::string& text) {
        if (!initialized) {
            return "ERROR: Not initialized";
        }
        
        std::string result;
        std::string remaining = text;
        
        while (!remaining.empty()) {
            bool found = false;
            
            for (size_t len = remaining.length(); len > 0; len--) {
                std::string substr = remaining.substr(0, len);
                
                for (const auto& token : dictionary) {
                    if (token.surface == substr) {
                        result += token.reading;
                        remaining = remaining.substr(len);
                        found = true;
                        break;
                    }
                }
                
                if (found) break;
            }
            
            if (!found) {
                std::string unknown = remaining.substr(0, 3);
                result += unknown;
                remaining = remaining.substr(unknown.length());
            }
        }
        
        return result;
    }
};

// Global instance (in real implementation, use proper memory management)
std::unique_ptr<SimpleMeCab> mecabInstance;

// C-style interface for Emscripten
extern "C" {
    EMSCRIPTEN_KEEPALIVE
    int mecab_initialize(const char* dictPath) {
        mecabInstance = std::make_unique<SimpleMeCab>();
        return mecabInstance->initialize(dictPath ? dictPath : "/dict") ? 1 : 0;
    }
    
    EMSCRIPTEN_KEEPALIVE
    const char* mecab_parse(const char* text) {
        if (!mecabInstance) {
            return "ERROR: Not initialized";
        }
        static std::string result;
        result = mecabInstance->parse(text);
        return result.c_str();
    }
    
    EMSCRIPTEN_KEEPALIVE
    const char* mecab_wakati(const char* text) {
        if (!mecabInstance) {
            return "ERROR: Not initialized";
        }
        static std::string result;
        result = mecabInstance->wakati(text);
        return result.c_str();
    }
}

// Embind interface for modern JavaScript
EMSCRIPTEN_BINDINGS(mecab_module) {
    emscripten::class_<SimpleMeCab>("SimpleMeCab")
        .constructor<>()
        .function("initialize", &SimpleMeCab::initialize)
        .function("parse", &SimpleMeCab::parse)
        .function("wakati", &SimpleMeCab::wakati)
        .function("getReading", &SimpleMeCab::getReading);
}