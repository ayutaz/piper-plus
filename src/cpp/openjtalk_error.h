#ifndef OPENJTALK_ERROR_H
#define OPENJTALK_ERROR_H

#ifdef __cplusplus
extern "C" {
#endif

// Error codes for OpenJTalk operations
typedef enum {
    OPENJTALK_SUCCESS = 0,
    OPENJTALK_ERROR_INVALID_INPUT = 1,
    OPENJTALK_ERROR_DICTIONARY_NOT_FOUND = 2,
    OPENJTALK_ERROR_VOICE_NOT_FOUND = 3,
    OPENJTALK_ERROR_MEMORY = 4,
    OPENJTALK_ERROR_IO = 5,
    OPENJTALK_ERROR_COMMAND_FAILED = 6,
    OPENJTALK_ERROR_BINARY_NOT_FOUND = 7,
    OPENJTALK_ERROR_TEMP_FILE = 8,
    OPENJTALK_ERROR_PARSE_OUTPUT = 9,
    OPENJTALK_ERROR_BUFFER_TOO_SMALL = 10,
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