// Windows-specific OpenJTalk implementation header
#ifndef OPENJTALK_WINDOWS_H
#define OPENJTALK_WINDOWS_H

#ifdef _WIN32

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Windows-specific OpenJTalk structure
typedef struct OpenJTalk_impl {
    char* openjtalk_binary_path;
    char* dict_path;
    char* voice_path;
    HANDLE process_handle;
} OpenJTalk;

// Windows-specific label wrapper
typedef struct HTS_Label_Wrapper_impl {
    char** labels;
    size_t size;
    size_t capacity;
} HTS_Label_Wrapper;

// Helper functions for Windows
char* create_temp_file_windows(const char* prefix, const char* suffix);
int execute_openjtalk_windows(OpenJTalk* oj, const char* input_file, const char* output_file);
HTS_Label_Wrapper* parse_labels_from_file(const char* filename);

#endif // _WIN32

#endif // OPENJTALK_WINDOWS_H