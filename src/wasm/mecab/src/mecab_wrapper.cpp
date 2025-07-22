#include <emscripten/bind.h>
#include <emscripten/emscripten.h>
#include <mecab.h>
#include <string>
#include <memory>
#include <vector>

using namespace emscripten;

class MeCabWrapper {
private:
    MeCab::Tagger* tagger;
    MeCab::Model* model;
    
public:
    MeCabWrapper() : tagger(nullptr), model(nullptr) {}
    
    ~MeCabWrapper() {
        if (tagger) {
            delete tagger;
            tagger = nullptr;
        }
        if (model) {
            delete model;
            model = nullptr;
        }
    }
    
    bool initialize(const std::string& dictPath) {
        try {
            // For WebAssembly, we'll use a minimal configuration
            // that doesn't require a full dictionary
            const char* argv[] = {
                "mecab",
                "-r", "/dev/null",  // no resource file
                "-d", dictPath.c_str(),
                "-O", "wakati",     // wakati output for testing
                nullptr
            };
            
            // Try to create model with minimal settings
            model = MeCab::createModel(3, const_cast<char**>(argv));
            if (!model) {
                // Fallback: try without dictionary path
                const char* fallback_argv[] = {
                    "mecab",
                    "-r", "/dev/null",
                    nullptr
                };
                model = MeCab::createModel(2, const_cast<char**>(fallback_argv));
                if (!model) {
                    return false;
                }
            }
            
            tagger = model->createTagger();
            if (!tagger) {
                delete model;
                model = nullptr;
                return false;
            }
            
            return true;
        } catch (...) {
            return false;
        }
    }
    
    std::string parse(const std::string& text) {
        if (!tagger) {
            return "ERROR: MeCab not initialized";
        }
        
        const char* result = tagger->parse(text.c_str());
        if (result) {
            return std::string(result);
        }
        
        return "ERROR: Parse failed";
    }
    
    std::string parseToNode(const std::string& text) {
        if (!tagger) {
            return "[]";
        }
        
        const MeCab::Node* node = tagger->parseToNode(text.c_str());
        std::string result = "[";
        bool first = true;
        
        for (; node; node = node->next) {
            if (node->stat == MECAB_BOS_NODE || node->stat == MECAB_EOS_NODE) {
                continue;
            }
            
            if (!first) {
                result += ",";
            }
            first = false;
            
            result += "{";
            result += "\"surface\":\"" + std::string(node->surface, node->length) + "\",";
            result += "\"feature\":\"" + std::string(node->feature) + "\",";
            result += "\"cost\":" + std::to_string(node->cost);
            result += "}";
        }
        
        result += "]";
        return result;
    }
    
    std::string wakati(const std::string& text) {
        if (!tagger) {
            return "";
        }
        
        const MeCab::Node* node = tagger->parseToNode(text.c_str());
        std::string result;
        
        for (; node; node = node->next) {
            if (node->stat == MECAB_BOS_NODE || node->stat == MECAB_EOS_NODE) {
                continue;
            }
            
            if (!result.empty()) {
                result += " ";
            }
            result += std::string(node->surface, node->length);
        }
        
        return result;
    }
    
    bool isInitialized() const {
        return tagger != nullptr;
    }
    
    std::string getVersion() {
        return "0.996";  // MeCab version
    }
};

// Emscripten bindings
EMSCRIPTEN_BINDINGS(mecab_module) {
    class_<MeCabWrapper>("MeCab")
        .constructor<>()
        .function("initialize", &MeCabWrapper::initialize)
        .function("parse", &MeCabWrapper::parse)
        .function("parseToNode", &MeCabWrapper::parseToNode)
        .function("wakati", &MeCabWrapper::wakati)
        .function("isInitialized", &MeCabWrapper::isInitialized)
        .function("getVersion", &MeCabWrapper::getVersion);
}