// Enable POSIX features for mkstemp on Linux
#ifndef _WIN32
#define _GNU_SOURCE
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#include <io.h>
#define F_OK 0
#define access _access
#define popen _popen
#define pclose _pclose
#define unlink _unlink
#define strtok_r strtok_s
#else
#include <unistd.h>
#include <pthread.h>
#endif

#include "openjtalk_dictionary_manager.h"
#include "openjtalk_error.h"
#include "openjtalk_security.h"
// #include "openjtalk_api.h"  // Temporarily disabled - requires OpenJTalk static libs

// Define a safe maximum value for buffer size calculations
#define OPENJTALK_SIZE_MAX ((size_t)-1)

// Constants - Size limits
#define OPENJTALK_MAX_PATH 1024
#define OPENJTALK_MAX_BUFFER 4096
#define OPENJTALK_MAX_COMMAND 4096
#define OPENJTALK_MAX_INPUT (1024 * 1024)  // 1MB limit
#define OPENJTALK_MAX_OUTPUT_FIELD 256
#define OPENJTALK_MAX_TEMP_PATH 256

// Thread-safe storage for OpenJTalk binary path
#ifdef _WIN32
__declspec(thread) static char g_openjtalk_bin_path[OPENJTALK_MAX_PATH] = {0};
static CRITICAL_SECTION g_path_mutex;
static BOOL g_mutex_initialized = FALSE;
#else
static __thread char g_openjtalk_bin_path[OPENJTALK_MAX_PATH] = {0};
static pthread_mutex_t g_path_mutex = PTHREAD_MUTEX_INITIALIZER;
#endif

// Helper function prototypes
static OpenJTalkError create_temp_files(char* input_file, char* output_file, size_t size);
static OpenJTalkError write_input_text(const char* filename, const char* text);
static OpenJTalkError execute_openjtalk_command(const char* command, OpenJTalkResult* result);
static char* read_and_parse_output(const char* filename, OpenJTalkResult* result);
static void cleanup_temp_files(const char* input_file, const char* output_file);

// Initialize mutex for Windows
#ifdef _WIN32
static void ensure_mutex_initialized() {
    if (!g_mutex_initialized) {
        InitializeCriticalSection(&g_path_mutex);
        g_mutex_initialized = TRUE;
    }
}
#endif

// Find OpenJTalk binary path
static const char* find_openjtalk_binary() {
#ifdef _WIN32
    ensure_mutex_initialized();
    EnterCriticalSection(&g_path_mutex);
#else
    pthread_mutex_lock(&g_path_mutex);
#endif
    
    if (g_openjtalk_bin_path[0] != 0) {
#ifdef _WIN32
        LeaveCriticalSection(&g_path_mutex);
#else
        pthread_mutex_unlock(&g_path_mutex);
#endif
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
#ifdef _WIN32
            // Get absolute path on Windows to avoid execution issues
            char abs_path[OPENJTALK_MAX_PATH];
            if (_fullpath(abs_path, paths[i], OPENJTALK_MAX_PATH) != NULL) {
                strcpy(g_openjtalk_bin_path, abs_path);
            } else {
                strcpy(g_openjtalk_bin_path, paths[i]);
            }
#else
            strcpy(g_openjtalk_bin_path, paths[i]);
#endif
#ifdef _WIN32
            LeaveCriticalSection(&g_path_mutex);
#else
            pthread_mutex_unlock(&g_path_mutex);
#endif
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
#ifdef _WIN32
            LeaveCriticalSection(&g_path_mutex);
#else
            pthread_mutex_unlock(&g_path_mutex);
#endif
            return g_openjtalk_bin_path;
        }
        pclose(fp);
    }
    
#ifdef _WIN32
    LeaveCriticalSection(&g_path_mutex);
#else
    pthread_mutex_unlock(&g_path_mutex);
#endif
    return NULL;
}

// Check if OpenJTalk binary is available
int openjtalk_is_available() {
    return find_openjtalk_binary() != NULL ? 1 : 0;
}

// Ensure OpenJTalk dictionary is available
int openjtalk_ensure_dictionary() {
    return ensure_openjtalk_dictionary() == 0 ? 1 : 0;
}

// Convert text to phonemes using OpenJTalk
char* openjtalk_text_to_phonemes(const char* text) {
    OpenJTalkResult result = {OPENJTALK_SUCCESS, ""};
    char input_file[OPENJTALK_MAX_TEMP_PATH];
    char output_file[OPENJTALK_MAX_TEMP_PATH];
    
    // Validate input
    if (!text) {
        openjtalk_set_result(&result, OPENJTALK_ERROR_NULL_INPUT, "Input text is NULL");
        fprintf(stderr, "Error: %s\n", result.message);
        return NULL;
    }
    
    if (strlen(text) == 0) {
        openjtalk_set_result(&result, OPENJTALK_ERROR_EMPTY_INPUT, "Input text is empty");
        fprintf(stderr, "Error: %s\n", result.message);
        return NULL;
    }
    
    // Check text length for reasonable bounds
    size_t text_len = strlen(text);
    if (text_len > OPENJTALK_MAX_INPUT) {
        openjtalk_set_result(&result, OPENJTALK_ERROR_INPUT_TOO_LARGE, 
                            "Input text too large: %zu bytes (max %d bytes)", 
                            text_len, OPENJTALK_MAX_INPUT);
        fprintf(stderr, "Error: %s\n", result.message);
        return NULL;
    }
    
    // Get dictionary path
    const char* dic_path = get_openjtalk_dictionary_path();
    if (!dic_path) {
        openjtalk_set_result(&result, OPENJTALK_ERROR_DICTIONARY_NOT_FOUND,
                            "Failed to get OpenJTalk dictionary path");
        fprintf(stderr, "Error: %s\n", result.message);
        return NULL;
    }

#ifdef _WIN32
    // Convert dictionary path to absolute path on Windows
    char abs_dic_path[OPENJTALK_MAX_PATH];
    if (_fullpath(abs_dic_path, dic_path, OPENJTALK_MAX_PATH) != NULL) {
        dic_path = abs_dic_path;
    }
#endif
    
    // Create temporary files
    OpenJTalkError err = create_temp_files(input_file, output_file, OPENJTALK_MAX_TEMP_PATH);
    if (err != OPENJTALK_SUCCESS) {
        fprintf(stderr, "Error: %s\n", openjtalk_error_to_string(err));
        return NULL;
    }
    
    // Write input text to file
    err = write_input_text(input_file, text);
    if (err != OPENJTALK_SUCCESS) {
        cleanup_temp_files(input_file, output_file);
        fprintf(stderr, "Error: %s\n", openjtalk_error_to_string(err));
        return NULL;
    }
    
    // Get OpenJTalk binary path
    const char* openjtalk_bin = find_openjtalk_binary();
    if (!openjtalk_bin) {
        cleanup_temp_files(input_file, output_file);
        fprintf(stderr, "Error: %s\n", openjtalk_error_to_string(OPENJTALK_ERROR_BINARY_NOT_FOUND));
        return NULL;
    }
    
    // Validate paths for security
    if (!openjtalk_is_safe_path(openjtalk_bin) || 
        !openjtalk_is_safe_path(dic_path) ||
        !openjtalk_is_safe_path(input_file) ||
        !openjtalk_is_safe_path(output_file)) {
        cleanup_temp_files(input_file, output_file);
        openjtalk_set_result(&result, OPENJTALK_ERROR_SECURITY, 
                            "Unsafe characters detected in file paths");
        fprintf(stderr, "Error: %s\n", result.message);
        return NULL;
    }
    
    // Construct and execute OpenJTalk command
    char command[OPENJTALK_MAX_COMMAND];
    int is_phonemizer = strstr(openjtalk_bin, "phonemizer") != NULL ? 1 : 0;
    
    if (is_phonemizer) {
        // Use phonemizer binary - no HTS voice needed
#ifdef _WIN32
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ot \"%s\" \"%s\"",
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
            fprintf(stderr, "Warning: HTS voice not found, attempting phoneme extraction only\n");
        }
        
#ifdef _WIN32
        if (voice_path) {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -m \"%s\" -ow NUL -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, voice_path, output_file, input_file);
        } else {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -ow NUL -ot \"%s\" \"%s\"",
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
    
    // Log the command for debugging
    fprintf(stderr, "DEBUG: Executing command: %s\n", command);

    // Execute command
    err = execute_openjtalk_command(command, &result);
    unlink(input_file);  // Clean up input file immediately
    
    if (err != OPENJTALK_SUCCESS) {
        cleanup_temp_files(NULL, output_file);
        fprintf(stderr, "Error: %s\n", result.message);
        return NULL;
    }
    
    // Read and parse output
    char* phonemes = read_and_parse_output(output_file, &result);
    unlink(output_file);  // Clean up output file
    
    if (!phonemes && result.code != OPENJTALK_SUCCESS) {
        fprintf(stderr, "Error: %s\n", result.message);
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
    size_t phoneme_buffer_size = OPENJTALK_MAX_BUFFER;
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

// Helper function implementations

// Create temporary files for input and output
static OpenJTalkError create_temp_files(char* input_file, char* output_file, size_t size) {
    if (!input_file || !output_file || size < OPENJTALK_MAX_TEMP_PATH) {
        return OPENJTALK_ERROR_NULL_INPUT;
    }
    
#ifdef _WIN32
    // Create temp files in current directory to avoid path issues
    static int temp_counter = 0;
    DWORD pid = GetCurrentProcessId();

    // Generate unique filenames based on process ID and counter
    snprintf(input_file, OPENJTALK_MAX_TEMP_PATH, "ojt_in_%u_%d.txt", pid, temp_counter);
    snprintf(output_file, OPENJTALK_MAX_TEMP_PATH, "ojt_out_%u_%d.txt", pid, temp_counter);
    temp_counter++;

    // Touch the files to ensure they exist
    FILE* fp = fopen(input_file, "w");
    if (!fp) return OPENJTALK_ERROR_TEMP_FILE;
    fclose(fp);

    fp = fopen(output_file, "w");
    if (!fp) {
        unlink(input_file);
        return OPENJTALK_ERROR_TEMP_FILE;
    }
    fclose(fp);
#else
    strcpy(input_file, "/tmp/openjtalk_input_XXXXXX");
    strcpy(output_file, "/tmp/openjtalk_output_XXXXXX");
    
    int fd = mkstemp(input_file);
    if (fd == -1) return OPENJTALK_ERROR_TEMP_FILE;
    close(fd);
    
    fd = mkstemp(output_file);
    if (fd == -1) {
        unlink(input_file);
        return OPENJTALK_ERROR_TEMP_FILE;
    }
    close(fd);
#endif
    
    return OPENJTALK_SUCCESS;
}

// Write input text to file
static OpenJTalkError write_input_text(const char* filename, const char* text) {
    if (!filename || !text) {
        return OPENJTALK_ERROR_NULL_INPUT;
    }
    
#ifdef _WIN32
    // Use binary mode and UTF-8 BOM for Windows
    FILE* fp = fopen(filename, "wb");
    if (!fp) {
        return OPENJTALK_ERROR_IO_WRITE;
    }
    // Write UTF-8 BOM for better compatibility
    const unsigned char utf8_bom[] = {0xEF, 0xBB, 0xBF};
    if (fwrite(utf8_bom, 1, 3, fp) != 3) {
        fclose(fp);
        return OPENJTALK_ERROR_IO_WRITE;
    }
    if (fputs(text, fp) == EOF) {
        fclose(fp);
        return OPENJTALK_ERROR_IO_WRITE;
    }
#else
    FILE* fp = fopen(filename, "w");
    if (!fp) {
        return OPENJTALK_ERROR_IO_WRITE;
    }
    if (fprintf(fp, "%s", text) < 0) {
        fclose(fp);
        return OPENJTALK_ERROR_IO_WRITE;
    }
#endif
    fclose(fp);
    return OPENJTALK_SUCCESS;
}

// Execute OpenJTalk command
static OpenJTalkError execute_openjtalk_command(const char* command, OpenJTalkResult* result) {
    if (!command) {
        return OPENJTALK_ERROR_NULL_INPUT;
    }
    
    // Use system() for simplicity and compatibility
    int exit_code = system(command);

    if (exit_code != 0) {
        if (result) {
            openjtalk_set_result(result, OPENJTALK_ERROR_COMMAND_FAILED,
                                "OpenJTalk command failed with exit code: %d", exit_code);
        }
        return OPENJTALK_ERROR_COMMAND_FAILED;
    }
    
    return OPENJTALK_SUCCESS;
}

// Read and parse output file
static char* read_and_parse_output(const char* filename, OpenJTalkResult* result) {
    if (!filename) {
        if (result) {
            openjtalk_set_result(result, OPENJTALK_ERROR_NULL_INPUT, "Invalid filename");
        }
        return NULL;
    }
    
    FILE* fp = fopen(filename, "r");
    if (!fp) {
        if (result) {
            openjtalk_set_result(result, OPENJTALK_ERROR_IO_READ, 
                                "Failed to open output file: %s", filename);
        }
        return NULL;
    }
    
    // Read the output file
    size_t phoneme_buffer_size = OPENJTALK_MAX_BUFFER;
    char* phonemes = malloc(phoneme_buffer_size);
    if (!phonemes) {
        fclose(fp);
        if (result) {
            openjtalk_set_result(result, OPENJTALK_ERROR_MEMORY, "Memory allocation failed");
        }
        return NULL;
    }
    phonemes[0] = '\0';
    size_t total_phoneme_len = 0;
    
    // First read the entire file to parse full-context labels
    fseek(fp, 0, SEEK_END);
    long file_size = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    
    // Allocate buffer for file content
    char* file_content = malloc(file_size + 1);
    if (!file_content) {
        fclose(fp);
        free(phonemes);
        if (result) {
            openjtalk_set_result(result, OPENJTALK_ERROR_MEMORY, "Memory allocation failed for file content");
        }
        return NULL;
    }
    
    // Read entire file
    size_t read_size = fread(file_content, 1, file_size, fp);
    file_content[read_size] = '\0';
    fclose(fp);
    
    // Parse full-context labels
    char* saveptr = NULL;
    char* line_ptr = strtok_r(file_content, "\n", &saveptr);
    
    while (line_ptr != NULL) {
        // Skip empty lines
        if (strlen(line_ptr) == 0) {
            line_ptr = strtok_r(NULL, "\n", &saveptr);
            continue;
        }
        
        // Extract phoneme from full-context label
        // Format: xx^xx-phoneme+xx=xx/A:...
        char* context_end = strchr(line_ptr, '/');
        if (context_end) {
            size_t context_len = context_end - line_ptr;
            if (context_len > 0 && context_len < 256) {
                char context[256];
                strncpy(context, line_ptr, context_len);
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
                            
                            // Check buffer capacity
                            size_t space_needed = (total_phoneme_len > 0 ? 1 : 0) + strlen(phoneme) + 1;
                            if (total_phoneme_len + space_needed > phoneme_buffer_size - 1) {
                                // Reallocate buffer
                                if (phoneme_buffer_size > OPENJTALK_SIZE_MAX / 2) {
                                    free(phonemes);
                                    free(file_content);
                                    if (result) {
                                        openjtalk_set_result(result, OPENJTALK_ERROR_BUFFER_TOO_SMALL,
                                                            "Buffer size would overflow");
                                    }
                                    return NULL;
                                }
                                size_t new_size = phoneme_buffer_size * 2;
                                char* new_phonemes = realloc(phonemes, new_size);
                                if (!new_phonemes) {
                                    free(phonemes);
                                    free(file_content);
                                    if (result) {
                                        openjtalk_set_result(result, OPENJTALK_ERROR_MEMORY,
                                                            "Memory reallocation failed");
                                    }
                                    return NULL;
                                }
                                phonemes = new_phonemes;
                                phoneme_buffer_size = new_size;
                            }
                            
                            // Add space if not first phoneme
                            if (total_phoneme_len > 0) {
                                strcat(phonemes, " ");
                                total_phoneme_len++;
                            }
                            
                            // Add phoneme
                            strcat(phonemes, phoneme);
                            total_phoneme_len += strlen(phoneme);
                        }
                    }
                }
            }
        }
        
        line_ptr = strtok_r(NULL, "\n", &saveptr);
    }
    
    free(file_content);
    
    if (total_phoneme_len == 0) {
        free(phonemes);
        if (result) {
            openjtalk_set_result(result, OPENJTALK_ERROR_PARSE_OUTPUT, "No phonemes found in output");
        }
        return NULL;
    }
    
    return phonemes;
}

// Clean up temporary files
static void cleanup_temp_files(const char* input_file, const char* output_file) {
    if (input_file) {
        unlink(input_file);
    }
    if (output_file) {
        unlink(output_file);
    }
}