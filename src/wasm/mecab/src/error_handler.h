/**
 * MeCab WebAssembly Error Handler
 * 
 * Provides comprehensive error handling for WebAssembly environment
 */

#ifndef MECAB_ERROR_HANDLER_H
#define MECAB_ERROR_HANDLER_H

#include <string>
#include <exception>
#include <emscripten.h>
#include <emscripten/val.h>

namespace mecab {

// Error types
enum class ErrorType {
    INITIALIZATION_ERROR,
    DICTIONARY_ERROR,
    MEMORY_ERROR,
    PARSING_ERROR,
    ENCODING_ERROR,
    INVALID_INPUT,
    RUNTIME_ERROR
};

// Custom exception class
class MeCabException : public std::exception {
private:
    ErrorType type_;
    std::string message_;
    std::string details_;
    
public:
    MeCabException(ErrorType type, const std::string& message, const std::string& details = "")
        : type_(type), message_(message), details_(details) {}
    
    const char* what() const noexcept override {
        return message_.c_str();
    }
    
    ErrorType getType() const { return type_; }
    const std::string& getDetails() const { return details_; }
    
    // Convert to JavaScript error object
    emscripten::val toJSError() const {
        emscripten::val error = emscripten::val::object();
        error.set("type", static_cast<int>(type_));
        error.set("message", message_);
        error.set("details", details_);
        error.set("name", "MeCabException");
        return error;
    }
};

// Error handler class
class ErrorHandler {
private:
    static bool debug_mode_;
    static std::string last_error_;
    
public:
    // Enable/disable debug mode
    static void setDebugMode(bool debug) {
        debug_mode_ = debug;
    }
    
    // Log error to console
    static void logError(const std::string& message) {
        last_error_ = message;
        if (debug_mode_) {
            EM_ASM({
                console.error('MeCab Error:', UTF8ToString($0));
            }, message.c_str());
        }
    }
    
    // Log warning to console
    static void logWarning(const std::string& message) {
        if (debug_mode_) {
            EM_ASM({
                console.warn('MeCab Warning:', UTF8ToString($0));
            }, message.c_str());
        }
    }
    
    // Log info to console
    static void logInfo(const std::string& message) {
        if (debug_mode_) {
            EM_ASM({
                console.info('MeCab Info:', UTF8ToString($0));
            }, message.c_str());
        }
    }
    
    // Get last error
    static std::string getLastError() {
        return last_error_;
    }
    
    // Clear last error
    static void clearLastError() {
        last_error_.clear();
    }
    
    // Throw JavaScript exception
    static void throwJS(const MeCabException& e) {
        EM_ASM({
            throw new Error(UTF8ToString($0));
        }, e.what());
    }
    
    // Check memory constraints
    static bool checkMemory(size_t required_bytes) {
        size_t available = EM_ASM_INT({
            if (typeof HEAP8 !== 'undefined') {
                return HEAP8.byteLength - HEAP8.byteOffset;
            }
            return 0;
        });
        
        if (available < required_bytes) {
            logError("Insufficient memory: required " + std::to_string(required_bytes) + 
                    " bytes, available " + std::to_string(available) + " bytes");
            return false;
        }
        return true;
    }
    
    // Safe UTF-8 validation
    static bool validateUTF8(const std::string& str) {
        size_t i = 0;
        while (i < str.length()) {
            unsigned char c = str[i];
            size_t bytes = 0;
            
            if (c <= 0x7F) {
                bytes = 1;
            } else if ((c & 0xE0) == 0xC0) {
                bytes = 2;
            } else if ((c & 0xF0) == 0xE0) {
                bytes = 3;
            } else if ((c & 0xF8) == 0xF0) {
                bytes = 4;
            } else {
                return false;
            }
            
            if (i + bytes > str.length()) {
                return false;
            }
            
            for (size_t j = 1; j < bytes; ++j) {
                if ((str[i + j] & 0xC0) != 0x80) {
                    return false;
                }
            }
            
            i += bytes;
        }
        return true;
    }
};

// Static member initialization
bool ErrorHandler::debug_mode_ = false;
std::string ErrorHandler::last_error_ = "";

// Macros for error handling
#define MECAB_TRY try {

#define MECAB_CATCH_RETURN(default_value) \
    } catch (const MeCabException& e) { \
        ErrorHandler::logError(e.what()); \
        return default_value; \
    } catch (const std::exception& e) { \
        ErrorHandler::logError(std::string("Unexpected error: ") + e.what()); \
        return default_value; \
    } catch (...) { \
        ErrorHandler::logError("Unknown error occurred"); \
        return default_value; \
    }

#define MECAB_CATCH_THROW \
    } catch (const MeCabException& e) { \
        ErrorHandler::throwJS(e); \
    } catch (const std::exception& e) { \
        MeCabException mecab_e(ErrorType::RUNTIME_ERROR, e.what()); \
        ErrorHandler::throwJS(mecab_e); \
    } catch (...) { \
        MeCabException mecab_e(ErrorType::RUNTIME_ERROR, "Unknown error occurred"); \
        ErrorHandler::throwJS(mecab_e); \
    }

} // namespace mecab

#endif // MECAB_ERROR_HANDLER_H