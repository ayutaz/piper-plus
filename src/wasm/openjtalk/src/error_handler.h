/**
 * Error Handler for OpenJTalk WebAssembly
 */

#ifndef OPENJTALK_ERROR_HANDLER_H
#define OPENJTALK_ERROR_HANDLER_H

#include <string>
#include <iostream>

namespace openjtalk {

class ErrorHandler {
private:
    static bool debug_mode;
    
public:
    static void setDebugMode(bool mode) {
        debug_mode = mode;
    }
    
    static void logInfo(const std::string& message) {
        if (debug_mode) {
            std::cout << "[INFO] " << message << std::endl;
        }
    }
    
    static void logError(const std::string& message) {
        std::cerr << "[ERROR] " << message << std::endl;
    }
    
    static void logWarning(const std::string& message) {
        if (debug_mode) {
            std::cout << "[WARN] " << message << std::endl;
        }
    }
};

} // namespace openjtalk

#endif // OPENJTALK_ERROR_HANDLER_H