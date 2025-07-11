#include "openjtalk_error.h"
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

const char* openjtalk_error_to_string(OpenJTalkError error) {
    switch (error) {
        case OPENJTALK_SUCCESS:
            return "Success";
        // Input validation errors
        case OPENJTALK_ERROR_NULL_INPUT:
            return "Null input provided";
        case OPENJTALK_ERROR_EMPTY_INPUT:
            return "Empty input provided";
        case OPENJTALK_ERROR_INPUT_TOO_LARGE:
            return "Input size exceeds limit";
        case OPENJTALK_ERROR_INVALID_PATH:
            return "Invalid path characters";
        // Resource errors
        case OPENJTALK_ERROR_DICTIONARY_NOT_FOUND:
            return "Dictionary not found";
        case OPENJTALK_ERROR_VOICE_NOT_FOUND:
            return "Voice file not found";
        case OPENJTALK_ERROR_BINARY_NOT_FOUND:
            return "OpenJTalk binary not found";
        // Memory errors
        case OPENJTALK_ERROR_MEMORY:
            return "Memory allocation failed";
        case OPENJTALK_ERROR_BUFFER_TOO_SMALL:
            return "Buffer too small";
        // I/O errors
        case OPENJTALK_ERROR_IO_READ:
            return "Failed to read file";
        case OPENJTALK_ERROR_IO_WRITE:
            return "Failed to write file";
        case OPENJTALK_ERROR_TEMP_FILE:
            return "Temporary file operation failed";
        // Execution errors
        case OPENJTALK_ERROR_COMMAND_FAILED:
            return "Command execution failed";
        case OPENJTALK_ERROR_PARSE_OUTPUT:
            return "Failed to parse output";
        // Security errors
        case OPENJTALK_ERROR_SECURITY:
            return "Security validation failed";
        // Unknown error
        case OPENJTALK_ERROR_UNKNOWN:
        default:
            return "Unknown error";
    }
}

void openjtalk_set_result(OpenJTalkResult* result, OpenJTalkError code, const char* format, ...) {
    if (!result) return;
    
    result->code = code;
    
    if (format) {
        va_list args;
        va_start(args, format);
        vsnprintf(result->message, sizeof(result->message), format, args);
        va_end(args);
        
        // Ensure null termination
        result->message[sizeof(result->message) - 1] = '\0';
    } else {
        strncpy(result->message, openjtalk_error_to_string(code), sizeof(result->message) - 1);
        result->message[sizeof(result->message) - 1] = '\0';
    }
}