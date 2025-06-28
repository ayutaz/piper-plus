#include "openjtalk_wrapper.h"
#include "openjtalk_dictionary_manager.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef _WIN32
#include <unistd.h>
#include <sys/wait.h>
#endif

#ifndef _WIN32

// Real OpenJTalk implementation for Unix platforms using binary execution
struct OpenJTalk_impl {
    char* dic_path;
    char* openjtalk_bin;
    int initialized;
};

struct HTS_Label_Wrapper_impl {
    char** labels;
    size_t size;
    size_t capacity;
};

OpenJTalk* openjtalk_initialize() {
    struct OpenJTalk_impl* oj = (struct OpenJTalk_impl*)calloc(1, sizeof(struct OpenJTalk_impl));
    if (!oj) return NULL;
    
    // Ensure dictionary is available (will download if necessary)
    const char* dic_path = NULL;
    if (openjtalk_ensure_dictionary(&dic_path) != 0) {
        fprintf(stderr, "Failed to ensure OpenJTalk dictionary is available\n");
        free(oj);
        return NULL;
    }
    
    // Find open_jtalk binary
    const char* possible_paths[] = {
        // Check relative to piper binary first (for packaged version)
        "../bin/open_jtalk",              // When piper is in bin/ directory
        "./open_jtalk",                   // Same directory as piper
        // Build directory paths
        "./oj/bin/open_jtalk",
        "../oj/bin/open_jtalk",
        "../../build/oj/bin/open_jtalk",
        // System paths
        "/usr/local/bin/open_jtalk",
        "/usr/bin/open_jtalk",
        "/opt/homebrew/bin/open_jtalk",  // macOS ARM64 homebrew
        "/opt/local/bin/open_jtalk",      // macOS MacPorts
        NULL
    };
    
    const char* found_bin = NULL;
    for (int i = 0; possible_paths[i] != NULL; i++) {
        if (access(possible_paths[i], X_OK) == 0) {
            found_bin = possible_paths[i];
            break;
        }
    }
    
    if (!found_bin) {
        // Try to find it relative to build directory
        char build_path[512];
        snprintf(build_path, sizeof(build_path), "%s/../oj/bin/open_jtalk", dic_path);
        if (access(build_path, X_OK) == 0) {
            found_bin = build_path;
        }
    }
    
    if (!found_bin) {
        fprintf(stderr, "open_jtalk binary not found. Searched paths:\n");
        for (int i = 0; possible_paths[i] != NULL; i++) {
            fprintf(stderr, "  %s\n", possible_paths[i]);
        }
        fprintf(stderr, "Please ensure OpenJTalk is installed or built\n");
        free(oj);
        return NULL;
    }
    
    oj->dic_path = strdup(dic_path);
    oj->openjtalk_bin = strdup(found_bin);
    oj->initialized = 1;
    
    return (OpenJTalk*)oj;
}

void openjtalk_finalize(OpenJTalk* oj) {
    if (!oj) return;
    
    struct OpenJTalk_impl* impl = (struct OpenJTalk_impl*)oj;
    
    if (impl->dic_path) free(impl->dic_path);
    if (impl->openjtalk_bin) free(impl->openjtalk_bin);
    
    free(oj);
}

// Parse phoneme from OpenJTalk label format
static char* extract_phoneme_from_label(const char* label) {
    // OpenJTalk label format includes phoneme after "-" and before "+"
    // Example: "xx^xx-sil+xx=xx/A:xx..."
    const char* start = strchr(label, '-');
    if (!start) return NULL;
    start++; // Skip '-'
    
    const char* end = strchr(start, '+');
    if (!end) return NULL;
    
    size_t len = end - start;
    if (len == 0) return NULL;
    
    // Skip if phoneme contains invalid characters like '>'
    if (memchr(start, '>', len) != NULL) return NULL;
    
    char* phoneme = (char*)malloc(len + 1);
    if (!phoneme) return NULL;
    
    strncpy(phoneme, start, len);
    phoneme[len] = '\0';
    
    return phoneme;
}

HTS_Label_Wrapper* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !text || strlen(text) == 0) return NULL;
    
    struct OpenJTalk_impl* impl = (struct OpenJTalk_impl*)oj;
    if (!impl->initialized) return NULL;
    
    // Create temporary files
    char input_file[] = "/tmp/openjtalk_input_XXXXXX";
    char output_file[] = "/tmp/openjtalk_output_XXXXXX";
    char trace_file[] = "/tmp/openjtalk_trace_XXXXXX";
    
    int input_fd = mkstemp(input_file);
    if (input_fd < 0) return NULL;
    
    int output_fd = mkstemp(output_file);
    if (output_fd < 0) {
        close(input_fd);
        unlink(input_file);
        return NULL;
    }
    
    int trace_fd = mkstemp(trace_file);
    if (trace_fd < 0) {
        close(input_fd);
        close(output_fd);
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    // Write input text
    FILE* fp = fdopen(input_fd, "w");
    if (!fp) {
        close(input_fd);
        close(output_fd);
        close(trace_fd);
        unlink(input_file);
        unlink(output_file);
        unlink(trace_file);
        return NULL;
    }
    
    // Write the text exactly as provided
    fprintf(fp, "%s", text);
    // Ensure proper line ending
    if (text[strlen(text)-1] != '\n') {
        fprintf(fp, "\n");
    }
    fclose(fp);
    close(output_fd);
    close(trace_fd);
    
    // Run open_jtalk with trace output only (no voice synthesis)
    pid_t pid = fork();
    if (pid == 0) {
        // Child process
        // Try to ensure HTS voice is available
        const char* voice_path = NULL;
        if (openjtalk_ensure_hts_voice(&voice_path) == 0 && voice_path) {
            // Use provided or auto-downloaded voice model
            execl(impl->openjtalk_bin, "open_jtalk",
                  "-x", impl->dic_path,
                  "-m", voice_path,
                  "-ot", trace_file,
                  "-ow", "/dev/null",  // Discard audio output
                  input_file,
                  NULL);
        } else {
            // Try without voice model (may not work with all OpenJTalk versions)
            execl(impl->openjtalk_bin, "open_jtalk",
                  "-x", impl->dic_path,
                  "-ot", trace_file,
                  input_file,
                  NULL);
        }
        _exit(1);
    } else if (pid < 0) {
        // Fork failed
        unlink(input_file);
        unlink(output_file);
        unlink(trace_file);
        return NULL;
    }
    
    // Wait for process
    int status;
    waitpid(pid, &status, 0);
    
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        unlink(input_file);
        unlink(output_file);
        unlink(trace_file);
        return NULL;
    }
    
    // Read trace file for labels
    fp = fopen(trace_file, "r");
    if (!fp) {
        unlink(input_file);
        unlink(output_file);
        unlink(trace_file);
        return NULL;
    }
    
    // Create wrapper
    struct HTS_Label_Wrapper_impl* wrapper = (struct HTS_Label_Wrapper_impl*)calloc(1, sizeof(struct HTS_Label_Wrapper_impl));
    if (!wrapper) {
        fclose(fp);
        unlink(input_file);
        unlink(output_file);
        unlink(trace_file);
        return NULL;
    }
    
    // Read labels
    char line[4096];
    size_t capacity = 64;
    wrapper->labels = (char**)calloc(capacity, sizeof(char*));
    if (!wrapper->labels) {
        free(wrapper);
        fclose(fp);
        unlink(input_file);
        unlink(output_file);
        unlink(trace_file);
        return NULL;
    }
    
    wrapper->size = 0;
    wrapper->capacity = capacity;
    
    while (fgets(line, sizeof(line), fp)) {
        // Remove newline
        size_t len = strlen(line);
        if (len > 0 && line[len-1] == '\n') {
            line[len-1] = '\0';
        }
        
        // Skip empty lines
        if (strlen(line) == 0) continue;
        
        // Check if this is a label line (contains phoneme information)
        // Also skip any error/warning lines that might contain ">"
        if (strstr(line, "-") && strstr(line, "+") && strstr(line, "/") && !strstr(line, ">")) {
            // Grow array if needed
            if (wrapper->size >= wrapper->capacity) {
                size_t new_capacity = wrapper->capacity * 2;
                char** new_labels = (char**)realloc(wrapper->labels, new_capacity * sizeof(char*));
                if (!new_labels) {
                    // Cleanup on error
                    for (size_t i = 0; i < wrapper->size; i++) {
                        free(wrapper->labels[i]);
                    }
                    free(wrapper->labels);
                    free(wrapper);
                    fclose(fp);
                    unlink(input_file);
                    unlink(output_file);
                    unlink(trace_file);
                    return NULL;
                }
                wrapper->labels = new_labels;
                wrapper->capacity = new_capacity;
            }
            
            // Store the full label
            wrapper->labels[wrapper->size] = strdup(line);
            if (!wrapper->labels[wrapper->size]) {
                // Cleanup on error
                for (size_t i = 0; i < wrapper->size; i++) {
                    free(wrapper->labels[i]);
                }
                free(wrapper->labels);
                free(wrapper);
                fclose(fp);
                unlink(input_file);
                unlink(output_file);
                unlink(trace_file);
                return NULL;
            }
            wrapper->size++;
        }
    }
    
    fclose(fp);
    
    // Cleanup temp files
    unlink(input_file);
    unlink(output_file);
    unlink(trace_file);
    
    if (wrapper->size == 0) {
        free(wrapper->labels);
        free(wrapper);
        return NULL;
    }
    
    return (HTS_Label_Wrapper*)wrapper;
}

size_t HTS_Label_get_size(HTS_Label_Wrapper* label) {
    if (!label) return 0;
    struct HTS_Label_Wrapper_impl* impl = (struct HTS_Label_Wrapper_impl*)label;
    return impl->size;
}

const char* HTS_Label_get_string(HTS_Label_Wrapper* label, size_t index) {
    if (!label) return NULL;
    struct HTS_Label_Wrapper_impl* impl = (struct HTS_Label_Wrapper_impl*)label;
    if (index >= impl->size) return NULL;
    return impl->labels[index];
}

void HTS_Label_clear(HTS_Label_Wrapper* label) {
    if (!label) return;
    struct HTS_Label_Wrapper_impl* impl = (struct HTS_Label_Wrapper_impl*)label;
    
    if (impl->labels) {
        for (size_t i = 0; i < impl->size; i++) {
            free(impl->labels[i]);
        }
        free(impl->labels);
    }
    
    free(label);
}

#else

// Windows implementation
#include "openjtalk_windows.h"
#include "openjtalk_dictionary_manager.h"
#include <io.h>
#include <fcntl.h>

// Windows temporary file creation
char* create_temp_file_windows(const char* prefix, const char* suffix) {
    char temp_path[MAX_PATH];
    char temp_filename[MAX_PATH];
    
    // Get temporary directory
    if (GetTempPath(MAX_PATH, temp_path) == 0) {
        return NULL;
    }
    
    // Generate unique filename
    if (GetTempFileName(temp_path, prefix, 0, temp_filename) == 0) {
        return NULL;
    }
    
    // Rename with suffix if needed
    if (suffix && strlen(suffix) > 0) {
        char new_filename[MAX_PATH];
        snprintf(new_filename, MAX_PATH, "%s%s", temp_filename, suffix);
        if (MoveFile(temp_filename, new_filename) == 0) {
            DeleteFile(temp_filename);
            return NULL;
        }
        return strdup(new_filename);
    }
    
    return strdup(temp_filename);
}

// Execute OpenJTalk binary on Windows
int execute_openjtalk_windows(OpenJTalk* oj, const char* input_file, const char* output_file) {
    char command[4096];
    STARTUPINFO si;
    PROCESS_INFORMATION pi;
    DWORD exit_code;
    
    // Build command line
    snprintf(command, sizeof(command), 
        "\"%s\" -x \"%s\" -m \"%s\" -ow \"%s\" \"%s\"",
        oj->openjtalk_binary_path,
        oj->dict_path,
        oj->voice_path,
        output_file,
        input_file);
    
    // Initialize structures
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    
    // Create process
    if (!CreateProcess(NULL, command, NULL, NULL, FALSE, 
                      CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        return -1;
    }
    
    // Wait for completion
    WaitForSingleObject(pi.hProcess, INFINITE);
    
    // Get exit code
    if (!GetExitCodeProcess(pi.hProcess, &exit_code)) {
        exit_code = -1;
    }
    
    // Clean up
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    
    return (int)exit_code;
}

OpenJTalk* openjtalk_initialize() {
    OpenJTalk* oj = (OpenJTalk*)calloc(1, sizeof(OpenJTalk));
    if (!oj) return NULL;
    
    // Try to find OpenJTalk binary
    const char* openjtalk_exe = getenv("OPENJTALK_BINARY");
    if (!openjtalk_exe) {
        // Try common locations
        if (_access("open_jtalk.exe", 0) == 0) {
            openjtalk_exe = "open_jtalk.exe";
        } else if (_access("bin\\open_jtalk.exe", 0) == 0) {
            openjtalk_exe = "bin\\open_jtalk.exe";
        } else {
            // Use bundled binary if available
            char exe_path[MAX_PATH];
            GetModuleFileName(NULL, exe_path, MAX_PATH);
            char* last_slash = strrchr(exe_path, '\\');
            if (last_slash) {
                *last_slash = '\0';
                char bundled_path[MAX_PATH];
                snprintf(bundled_path, MAX_PATH, "%s\\open_jtalk.exe", exe_path);
                if (_access(bundled_path, 0) == 0) {
                    openjtalk_exe = strdup(bundled_path);
                }
            }
        }
    }
    
    if (!openjtalk_exe) {
        free(oj);
        return NULL;
    }
    
    oj->openjtalk_binary_path = strdup(openjtalk_exe);
    
    // Ensure dictionary is available
    const char* dict_path = NULL;
    if (openjtalk_ensure_dictionary(&dict_path) != 0) {
        free(oj->openjtalk_binary_path);
        free(oj);
        return NULL;
    }
    oj->dict_path = strdup(dict_path);
    
    // Set voice path
    const char* voice_path = getenv("OPENJTALK_VOICE");
    if (!voice_path) {
        // Try to use bundled voice
        char exe_path[MAX_PATH];
        GetModuleFileName(NULL, exe_path, MAX_PATH);
        char* last_slash = strrchr(exe_path, '\\');
        if (last_slash) {
            *last_slash = '\0';
            static char voice_buf[MAX_PATH];
            snprintf(voice_buf, MAX_PATH, "%s\\..\\share\\hts\\nitech_jp_atr503_m001.htsvoice", exe_path);
            if (_access(voice_buf, 0) == 0) {
                voice_path = voice_buf;
            }
        }
    }
    
    if (voice_path) {
        oj->voice_path = strdup(voice_path);
    }
    
    return oj;
}

void openjtalk_finalize(OpenJTalk* oj) {
    if (!oj) return;
    
    free(oj->openjtalk_binary_path);
    free(oj->dict_path);
    free(oj->voice_path);
    free(oj);
}

HTS_Label_Wrapper* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !text || !oj->openjtalk_binary_path || !oj->dict_path) {
        return NULL;
    }
    
    // Create temporary files
    char* input_file = create_temp_file_windows("ojin", ".txt");
    char* output_file = create_temp_file_windows("ojout", ".lab");
    
    if (!input_file || !output_file) {
        free(input_file);
        free(output_file);
        return NULL;
    }
    
    // Write input text
    FILE* fp = fopen(input_file, "w");
    if (!fp) {
        free(input_file);
        free(output_file);
        return NULL;
    }
    fprintf(fp, "%s", text);
    fclose(fp);
    
    // Build command for label generation only
    char command[4096];
    snprintf(command, sizeof(command), 
        "\"%s\" -x \"%s\" -ot \"%s\" \"%s\"",
        oj->openjtalk_binary_path,
        oj->dict_path,
        output_file,
        input_file);
    
    // Execute command
    STARTUPINFO si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    
    if (!CreateProcess(NULL, command, NULL, NULL, FALSE, 
                      CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        DeleteFile(input_file);
        free(input_file);
        free(output_file);
        return NULL;
    }
    
    WaitForSingleObject(pi.hProcess, INFINITE);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    
    // Parse labels
    HTS_Label_Wrapper* labels = parse_labels_from_file(output_file);
    
    // Clean up
    DeleteFile(input_file);
    DeleteFile(output_file);
    free(input_file);
    free(output_file);
    
    return labels;
}

HTS_Label_Wrapper* parse_labels_from_file(const char* filename) {
    FILE* fp = fopen(filename, "r");
    if (!fp) return NULL;
    
    HTS_Label_Wrapper* label = (HTS_Label_Wrapper*)calloc(1, sizeof(HTS_Label_Wrapper));
    if (!label) {
        fclose(fp);
        return NULL;
    }
    
    label->capacity = 100;
    label->labels = (char**)calloc(label->capacity, sizeof(char*));
    if (!label->labels) {
        free(label);
        fclose(fp);
        return NULL;
    }
    
    char line[1024];
    while (fgets(line, sizeof(line), fp)) {
        // Remove newline
        size_t len = strlen(line);
        if (len > 0 && line[len-1] == '\n') {
            line[len-1] = '\0';
        }
        
        // Skip empty lines
        if (strlen(line) == 0) continue;
        
        // Resize if needed
        if (label->size >= label->capacity) {
            label->capacity *= 2;
            char** new_labels = (char**)realloc(label->labels, 
                                               label->capacity * sizeof(char*));
            if (!new_labels) {
                HTS_Label_clear(label);
                fclose(fp);
                return NULL;
            }
            label->labels = new_labels;
        }
        
        // Store label
        label->labels[label->size] = strdup(line);
        label->size++;
    }
    
    fclose(fp);
    return label;
}

size_t HTS_Label_get_size(HTS_Label_Wrapper* label) {
    return label ? label->size : 0;
}

const char* HTS_Label_get_string(HTS_Label_Wrapper* label, size_t index) {
    if (!label || index >= label->size) return NULL;
    return label->labels[index];
}

void HTS_Label_clear(HTS_Label_Wrapper* label) {
    if (!label) return;
    
    if (label->labels) {
        for (size_t i = 0; i < label->size; i++) {
            free(label->labels[i]);
        }
        free(label->labels);
    }
    
    free(label);
}

#endif // _WIN32