#include <emscripten.h>
#include <emscripten/bind.h>
#include <emscripten/val.h>
#include <string>
#include <iostream>
#include <vector>

// Simple test function
std::string greet(const std::string& name) {
    return "Hello from WebAssembly, " + name + "!";
}

// Test Japanese text handling
std::string processJapanese(const std::string& text) {
    return "Processing: " + text;
}

// Memory allocation test - using emscripten's memory management
emscripten::val allocateArray(int size) {
    std::vector<int> data(size, 0);
    return emscripten::val(emscripten::typed_memory_view(data.size(), data.data()));
}

// Simple memory test
std::string testMemory(int size) {
    std::vector<int> data(size, 42);
    int sum = 0;
    for (int val : data) {
        sum += val;
    }
    return "Allocated " + std::to_string(size) + " integers, sum: " + std::to_string(sum);
}

// Export functions using Embind
EMSCRIPTEN_BINDINGS(hello_wasm) {
    emscripten::function("greet", &greet);
    emscripten::function("processJapanese", &processJapanese);
    emscripten::function("allocateArray", &allocateArray);
    emscripten::function("testMemory", &testMemory);
}