#include <emscripten.h>
#include <string>
#include <cstring>
#include <cstdlib>

// Simple wrapper that just exports test functions
// The actual OpenJTalk integration will be added after we get the basic build working

extern "C" {

EMSCRIPTEN_KEEPALIVE
const char* get_version() {
    return "OpenJTalk WebAssembly 0.1.1";
}

EMSCRIPTEN_KEEPALIVE
int test_function(int a, int b) {
    return a + b;
}

EMSCRIPTEN_KEEPALIVE
char* echo_string(const char* input) {
    if (!input) {
        return strdup("NULL input");
    }
    
    // Create a copy with prefix
    std::string result = "Echo: ";
    result += input;
    
    return strdup(result.c_str());
}

EMSCRIPTEN_KEEPALIVE
void free_string(char* str) {
    if (str) {
        free(str);
    }
}

// Placeholder functions for OpenJTalk API
EMSCRIPTEN_KEEPALIVE
int openjtalk_initialize(const char* dic_dir) {
    // For now, just return success
    return 0;
}

EMSCRIPTEN_KEEPALIVE
char* openjtalk_synthesis_labels(const char* text) {
    // For now, just return a dummy response
    std::string result = "Dummy labels for: ";
    result += text ? text : "NULL";
    return strdup(result.c_str());
}

EMSCRIPTEN_KEEPALIVE
void openjtalk_clear() {
    // Placeholder
}

EMSCRIPTEN_KEEPALIVE
void openjtalk_free_string(char* str) {
    free_string(str);
}

} // extern "C"