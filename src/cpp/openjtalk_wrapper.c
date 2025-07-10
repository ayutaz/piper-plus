#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

#ifdef _WIN32
#include <windows.h>
#include <io.h>
#define F_OK 0
#define access _access
#define popen _popen
#define pclose _pclose
#define unlink _unlink
#else
#include <unistd.h>
#endif

#include "openjtalk_dictionary_manager.h"
// #include "openjtalk_api.h"  // Temporarily disabled - requires OpenJTalk static libs

// Define a safe maximum value for buffer size calculations
#define OPENJTALK_SIZE_MAX ((size_t)-1)

// Constants
#define OPENJTALK_PATH_MAX 1024
#define OPENJTALK_BUFFER_SIZE 4096
#define OPENJTALK_COMMAND_SIZE 4096
#define OPENJTALK_MAX_INPUT_SIZE (1024 * 1024)  // 1MB limit

// Global variable to store OpenJTalk binary path
static char g_openjtalk_bin_path[OPENJTALK_PATH_MAX] = {0};

// Find OpenJTalk binary path
static const char* find_openjtalk_binary() {
    if (g_openjtalk_bin_path[0] != 0) {
        return g_openjtalk_bin_path;
    }
    
    // Check if open_jtalk_phonemizer binary exists (preferred)
    const char* paths[] = {
#ifdef _WIN32
        "open_jtalk_phonemizer.exe",
        "bin\\open_jtalk_phonemizer.exe",
        ".\\open_jtalk_phonemizer.exe",
        "..\\bin\\open_jtalk_phonemizer.exe",
        "piper\\bin\\open_jtalk_phonemizer.exe",
        // Fall back to regular open_jtalk if phonemizer not found
        "open_jtalk.exe",
        "bin\\open_jtalk.exe",
        ".\\open_jtalk.exe",
        "..\\bin\\open_jtalk.exe",
        "piper\\bin\\open_jtalk.exe",
#else
        "./open_jtalk_phonemizer",
        "./bin/open_jtalk_phonemizer",
        "../bin/open_jtalk_phonemizer",
        "./piper/bin/open_jtalk_phonemizer",
        "./oj/bin/open_jtalk_phonemizer",
        "../oj/bin/open_jtalk_phonemizer",
        "../../oj/bin/open_jtalk_phonemizer",
        "../../../oj/bin/open_jtalk_phonemizer",
        "/usr/bin/open_jtalk_phonemizer",
        "/usr/local/bin/open_jtalk_phonemizer",
        // Fall back to regular open_jtalk if phonemizer not found
        "./open_jtalk",
        "./bin/open_jtalk",
        "../bin/open_jtalk",
        "./piper/bin/open_jtalk",
        "/usr/bin/open_jtalk",
        "/usr/local/bin/open_jtalk",
#endif
        NULL
    };
    
    for (int i = 0; paths[i] != NULL; i++) {
        if (access(paths[i], F_OK) == 0) {
            strcpy(g_openjtalk_bin_path, paths[i]);
            return g_openjtalk_bin_path;
        }
    }
    
    // Try to find in PATH - first try phonemizer, then regular
#ifdef _WIN32
    FILE* fp = popen("where open_jtalk_phonemizer.exe 2>NUL", "r");
    if (!fp || fgets(g_openjtalk_bin_path, sizeof(g_openjtalk_bin_path), fp) == NULL) {
        if (fp) pclose(fp);
        fp = popen("where open_jtalk.exe 2>NUL", "r");
    }
#else
    FILE* fp = popen("which open_jtalk_phonemizer 2>/dev/null", "r");
    if (!fp || fgets(g_openjtalk_bin_path, sizeof(g_openjtalk_bin_path), fp) == NULL) {
        if (fp) pclose(fp);
        fp = popen("which open_jtalk 2>/dev/null", "r");
    }
#endif
    if (fp) {
        if (fgets(g_openjtalk_bin_path, sizeof(g_openjtalk_bin_path), fp) != NULL) {
            // Remove newline
            size_t len = strlen(g_openjtalk_bin_path);
            if (len > 0 && g_openjtalk_bin_path[len-1] == '\n') {
                g_openjtalk_bin_path[len-1] = '\0';
            }
            pclose(fp);
            return g_openjtalk_bin_path;
        }
        pclose(fp);
    }
    
    return NULL;
}

// Check if OpenJTalk binary is available
bool openjtalk_is_available() {
    return find_openjtalk_binary() != NULL;
}

// Ensure OpenJTalk dictionary is available
bool openjtalk_ensure_dictionary() {
    return ensure_openjtalk_dictionary() == 0;
}

// Convert text to phonemes using OpenJTalk
char* openjtalk_text_to_phonemes(const char* text) {
    if (!text || strlen(text) == 0) {
        return NULL;
    }
    
    // Check text length for reasonable bounds
    size_t text_len = strlen(text);
    if (text_len > OPENJTALK_MAX_INPUT_SIZE) {
        fprintf(stderr, "Input text too large: %zu bytes (max %d bytes)\n", text_len, OPENJTALK_MAX_INPUT_SIZE);
        return NULL;
    }
    
    // Get dictionary path
    const char* dic_path = get_openjtalk_dictionary_path();
    if (!dic_path) {
        fprintf(stderr, "Failed to get OpenJTalk dictionary path\n");
        return NULL;
    }
    
    // Create temporary files
    char input_file[256];
    char output_file[256];
    
#ifdef _WIN32
    // Use GetTempFileName for secure temporary file creation
    char temp_path[MAX_PATH];
    DWORD path_len = GetTempPath(MAX_PATH, temp_path);
    if (path_len == 0 || path_len > MAX_PATH) {
        fprintf(stderr, "Failed to get temp path\n");
        return NULL;
    }
    
    // Create unique temporary files
    if (GetTempFileName(temp_path, "ojt_in", 0, input_file) == 0) {
        fprintf(stderr, "Failed to create temp input file: error %lu\n", GetLastError());
        return NULL;
    }
    
    if (GetTempFileName(temp_path, "ojt_out", 0, output_file) == 0) {
        fprintf(stderr, "Failed to create temp output file: error %lu\n", GetLastError());
        // Clean up the input file that was already created
        unlink(input_file);
        return NULL;
    }
#else
    strcpy(input_file, "/tmp/openjtalk_input_XXXXXX");
    strcpy(output_file, "/tmp/openjtalk_output_XXXXXX");
    
    int fd = mkstemp(input_file);
    if (fd == -1) return NULL;
    close(fd);
    
    fd = mkstemp(output_file);
    if (fd == -1) {
        unlink(input_file);
        return NULL;
    }
    close(fd);
#endif
    
    // Write input text to file
#ifdef _WIN32
    // Use binary mode and UTF-8 BOM for Windows
    FILE* fp = fopen(input_file, "wb");
    if (!fp) {
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    // Write UTF-8 BOM for better compatibility
    const unsigned char utf8_bom[] = {0xEF, 0xBB, 0xBF};
    fwrite(utf8_bom, 1, 3, fp);
    fwrite(text, 1, strlen(text), fp);
#else
    FILE* fp = fopen(input_file, "w");
    if (!fp) {
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    fprintf(fp, "%s", text);
#endif
    fclose(fp);
    
    // Get OpenJTalk binary path
    const char* openjtalk_bin = find_openjtalk_binary();
    if (!openjtalk_bin) {
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    // Check if we're using the phonemizer binary (doesn't need HTS voice)
    bool is_phonemizer = strstr(openjtalk_bin, "phonemizer") != NULL;
    
    // Construct OpenJTalk command
    char command[OPENJTALK_COMMAND_SIZE];
    
    if (is_phonemizer) {
        // Use phonemizer binary - no HTS voice needed
#ifdef _WIN32
        snprintf(command, sizeof(command),
                 "cmd /c \"\"%s\" -x \"%s\" -ot \"%s\" \"%s\"\"",
                 openjtalk_bin, dic_path, output_file, input_file);
#else
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, output_file, input_file);
#endif
    } else {
        // Fall back to regular open_jtalk with HTS voice
        const char* voice_path = get_openjtalk_voice_path();
        if (!voice_path) {
            // Try to continue without voice for phoneme extraction
            fprintf(stderr, "Warning: HTS voice not found, attempting phoneme extraction only\n");
        }
        
#ifdef _WIN32
        if (voice_path) {
            snprintf(command, sizeof(command),
                     "cmd /c \"\"%s\" -x \"%s\" -m \"%s\" -ow NUL -ot \"%s\" \"%s\"\"",
                     openjtalk_bin, dic_path, voice_path, output_file, input_file);
        } else {
            snprintf(command, sizeof(command),
                     "cmd /c \"\"%s\" -x \"%s\" -ow NUL -ot \"%s\" \"%s\"\"",
                     openjtalk_bin, dic_path, output_file, input_file);
        }
#else
        if (voice_path) {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -m \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, voice_path, output_file, input_file);
        } else {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, output_file, input_file);
        }
#endif
    }
    
    
    // Execute OpenJTalk
    int result = system(command);
    
    // Clean up input file
    unlink(input_file);
    
    if (result != 0) {
        fprintf(stderr, "OpenJTalk command failed with code: %d\n", result);
        unlink(output_file);
        return NULL;
    }
    
    // Read trace output file
    fp = fopen(output_file, "r");
    if (!fp) {
        fprintf(stderr, "Failed to open output file: %s\n", output_file);
        unlink(output_file);
        return NULL;
    }
    
    // Check file size
    fseek(fp, 0, SEEK_END);
    long file_size = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    
    // Allocate buffer based on file size
    char* file_content = malloc(file_size + 1);
    if (!file_content) {
        fclose(fp);
        unlink(output_file);
        return NULL;
    }
    
    // Read entire file
    size_t read_size = fread(file_content, 1, file_size, fp);
    file_content[read_size] = '\0';
    fclose(fp);
    
    // Allocate buffer for phonemes based on file size
    // Phonemes are typically shorter than full-context labels, but allocate generously
    size_t phoneme_buffer_size = file_size > OPENJTALK_BUFFER_SIZE ? file_size : OPENJTALK_BUFFER_SIZE;
    char* phonemes = malloc(phoneme_buffer_size);
    if (!phonemes) {
        free(file_content);
        unlink(output_file);
        return NULL;
    }
    
    phonemes[0] = '\0';
    size_t total_phoneme_len = 0;
    
    // Parse full-context labels from open_jtalk_phonemizer output
    char* line = strtok(file_content, "\n");
    
    while (line != NULL) {
        // Skip empty lines
        if (strlen(line) == 0) {
            line = strtok(NULL, "\n");
            continue;
        }
        
        // Extract phoneme from full-context label using more robust parsing
        // Format: xx^xx-p3+xx=xx/A:...
        // We need to find the pattern "-phoneme+" where phoneme is between - and +
        
        // First, find the phoneme context section (before the first '/')
        char* context_end = strchr(line, '/');
        if (context_end) {
            // Create a temporary buffer for the context part
            size_t context_len = context_end - line;
            if (context_len > 0 && context_len < 256) {
                char context[256];
                strncpy(context, line, context_len);
                context[context_len] = '\0';
                
                // Find the pattern -phoneme+ in the context
                char* minus_pos = strchr(context, '-');
                if (minus_pos) {
                    char* plus_pos = strchr(minus_pos + 1, '+');
                    if (plus_pos && plus_pos > minus_pos + 1) {
                        // Extract phoneme
                        size_t phoneme_len = plus_pos - minus_pos - 1;
                        if (phoneme_len > 0 && phoneme_len < 32) {
                            char phoneme[32];
                            strncpy(phoneme, minus_pos + 1, phoneme_len);
                            phoneme[phoneme_len] = '\0';
                            
                            // Add phoneme with space separator
                            // All phonemes including sil and pau are passed through
                            size_t phoneme_str_len = strlen(phoneme);
                            size_t space_needed = (total_phoneme_len > 0 ? 1 : 0) + phoneme_str_len + 1;
                            
                            // Check buffer capacity
                            if (total_phoneme_len + space_needed > phoneme_buffer_size - 1) {
                                // Reallocate buffer if needed
                                // Check for potential overflow
                                if (phoneme_buffer_size > OPENJTALK_SIZE_MAX / 2) {
                                    fprintf(stderr, "Buffer size would overflow\n");
                                    free(phonemes);
                                    free(file_content);
                                    unlink(output_file);
                                    return NULL;
                                }
                                size_t new_size = phoneme_buffer_size * 2;
                                char* new_phonemes = realloc(phonemes, new_size);
                                if (!new_phonemes) {
                                    free(phonemes);
                                    free(file_content);
                                    unlink(output_file);
                                    return NULL;
                                }
                                phonemes = new_phonemes;
                                phoneme_buffer_size = new_size;
                            }
                            
                            // Add space if not first phoneme
                            if (total_phoneme_len > 0) {
                                phonemes[total_phoneme_len++] = ' ';
                            }
                            
                            // Copy phoneme
                            memcpy(phonemes + total_phoneme_len, phoneme, phoneme_str_len);
                            total_phoneme_len += phoneme_str_len;
                            phonemes[total_phoneme_len] = '\0';
                        }
                    }
                }
            }
        }
        
        line = strtok(NULL, "\n");
    }
    
    
    free(file_content);
    unlink(output_file);
    
    if (strlen(phonemes) == 0) {
        free(phonemes);
        return NULL;
    }
    
    return phonemes;
}


// Free phoneme string
void openjtalk_free_phonemes(char* phonemes) {
    if (phonemes) {
        free(phonemes);
    }
}

// Convert text to phonemes using OpenJTalk internal API (more efficient)
// TEMPORARILY DISABLED - requires OpenJTalk static libs
/*
char* openjtalk_text_to_phonemes_api(const char* text) {
    if (!text || strlen(text) == 0) {
        return NULL;
    }
    
    // Check text length for reasonable bounds
    size_t text_len = strlen(text);
    if (text_len > OPENJTALK_MAX_INPUT_SIZE) {
        fprintf(stderr, "Input text too large: %zu bytes (max %d bytes)\n", text_len, OPENJTALK_MAX_INPUT_SIZE);
        return NULL;
    }
    
    // Ensure dictionary is available
    if (!openjtalk_ensure_dictionary()) {
        fprintf(stderr, "Failed to ensure OpenJTalk dictionary\n");
        return NULL;
    }
    
    // Initialize OpenJTalk
    OpenJTalk* oj = openjtalk_initialize();
    if (!oj) {
        fprintf(stderr, "Failed to initialize OpenJTalk\n");
        return NULL;
    }
    
    // Extract full context labels
    HTS_Label* label = openjtalk_extract_fullcontext(oj, text);
    if (!label) {
        fprintf(stderr, "Failed to extract full context\n");
        openjtalk_finalize(oj);
        return NULL;
    }
    
    // Allocate initial buffer for phonemes
    size_t phoneme_buffer_size = OPENJTALK_BUFFER_SIZE;
    char* phonemes = malloc(phoneme_buffer_size);
    if (!phonemes) {
        HTS_Label_clear(label);
        openjtalk_finalize(oj);
        return NULL;
    }
    
    phonemes[0] = '\0';
    size_t total_phoneme_len = 0;
    
    // Extract phonemes from labels
    size_t label_size = HTS_Label_get_size(label);
    for (size_t i = 0; i < label_size; i++) {
        const char* label_str = HTS_Label_get_string(label, i);
        if (!label_str) continue;
        
        // Skip silence at beginning and end
        if (i == 0 || i == label_size - 1) {
            if (strstr(label_str, "-sil+")) continue;
        }
        
        // Extract phoneme from full-context label
        // Format: xx^xx-phoneme+xx=xx/A:...
        const char* minus_pos = strchr(label_str, '-');
        if (minus_pos) {
            const char* plus_pos = strchr(minus_pos + 1, '+');
            if (plus_pos && plus_pos > minus_pos + 1) {
                size_t phoneme_len = plus_pos - minus_pos - 1;
                if (phoneme_len > 0 && phoneme_len < 32) {
                    // Check buffer capacity
                    size_t space_needed = (total_phoneme_len > 0 ? 1 : 0) + phoneme_len + 1;
                    if (total_phoneme_len + space_needed > phoneme_buffer_size - 1) {
                        // Reallocate buffer
                        // Check for potential overflow
                        if (phoneme_buffer_size > SIZE_MAX / 2) {
                            fprintf(stderr, "Buffer size would overflow\n");
                            free(phonemes);
                            HTS_Label_clear(label);
                            openjtalk_finalize(oj);
                            return NULL;
                        }
                        size_t new_size = phoneme_buffer_size * 2;
                        char* new_phonemes = realloc(phonemes, new_size);
                        if (!new_phonemes) {
                            free(phonemes);
                            HTS_Label_clear(label);
                            openjtalk_finalize(oj);
                            return NULL;
                        }
                        phonemes = new_phonemes;
                        phoneme_buffer_size = new_size;
                    }
                    
                    // Add space if not first phoneme
                    if (total_phoneme_len > 0) {
                        phonemes[total_phoneme_len++] = ' ';
                    }
                    
                    // Copy phoneme
                    memcpy(phonemes + total_phoneme_len, minus_pos + 1, phoneme_len);
                    total_phoneme_len += phoneme_len;
                    phonemes[total_phoneme_len] = '\0';
                }
            }
        }
    }
    
    // Clean up
    HTS_Label_clear(label);
    openjtalk_finalize(oj);
    
    if (total_phoneme_len == 0) {
        free(phonemes);
        return NULL;
    }
    
    return phonemes;
}
*/