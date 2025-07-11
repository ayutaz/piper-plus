#ifndef OPENJTALK_ERROR_H
#define OPENJTALK_ERROR_H

#ifdef __cplusplus
extern "C" {
#endif

// Error codes for OpenJTalk operations
typedef enum {
    OPENJTALK_SUCCESS = 0,
    // Input validation errors
    OPENJTALK_ERROR_NULL_INPUT = 1,
    OPENJTALK_ERROR_EMPTY_INPUT = 2,
    OPENJTALK_ERROR_INPUT_TOO_LARGE = 3,
    OPENJTALK_ERROR_INVALID_PATH = 4,
    // Resource errors
    OPENJTALK_ERROR_DICTIONARY_NOT_FOUND = 10,
    OPENJTALK_ERROR_VOICE_NOT_FOUND = 11,
    OPENJTALK_ERROR_BINARY_NOT_FOUND = 12,
    // Memory errors
    OPENJTALK_ERROR_MEMORY = 20,
    OPENJTALK_ERROR_BUFFER_TOO_SMALL = 21,
    // I/O errors
    OPENJTALK_ERROR_IO_READ = 30,
    OPENJTALK_ERROR_IO_WRITE = 31,
    OPENJTALK_ERROR_TEMP_FILE = 32,
    // Execution errors
    OPENJTALK_ERROR_COMMAND_FAILED = 40,
    OPENJTALK_ERROR_PARSE_OUTPUT = 41,
    // Security errors
    OPENJTALK_ERROR_SECURITY = 50,
    // Unknown error
    OPENJTALK_ERROR_UNKNOWN = 99
} OpenJTalkError;

// Error result structure
typedef struct {
    OpenJTalkError code;
    char message[256];
} OpenJTalkResult;

// Helper functions
const char* openjtalk_error_to_string(OpenJTalkError error);
void openjtalk_set_result(OpenJTalkResult* result, OpenJTalkError code, const char* format, ...);

#ifdef __cplusplus
}
#endif

#endif // OPENJTALK_ERROR_H