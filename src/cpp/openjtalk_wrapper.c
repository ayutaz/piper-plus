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
    
    // Create temporary files in platform-appropriate directory
    const char* temp_dir = getenv("TMPDIR");
    if (!temp_dir) temp_dir = getenv("TMP");
    if (!temp_dir) temp_dir = getenv("TEMP");
    if (!temp_dir) temp_dir = "/tmp";
    
    char input_file[512];
    char output_file[512];
    char trace_file[512];
    
    snprintf(input_file, sizeof(input_file), "%s/openjtalk_input_XXXXXX", temp_dir);
    snprintf(output_file, sizeof(output_file), "%s/openjtalk_output_XXXXXX", temp_dir);
    snprintf(trace_file, sizeof(trace_file), "%s/openjtalk_trace_XXXXXX", temp_dir);
    
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

#else  // Windows implementation

#include <windows.h>
#include <process.h>
#include <io.h>
#include <fcntl.h>
#include <sys/stat.h>

// Windows implementation of OpenJTalk wrapper
struct OpenJTalk {
    char* openjtalk_path;
    char* dictionary_path;
};

struct HTS_Label_Wrapper {
    char** labels;
    size_t num_labels;
};

OpenJTalk* openjtalk_initialize() {
    OpenJTalk* oj = (OpenJTalk*)malloc(sizeof(OpenJTalk));
    if (!oj) return NULL;
    
    oj->openjtalk_path = NULL;
    oj->dictionary_path = NULL;
    
    // Find OpenJTalk binary
    const char* possible_paths[] = {
        "open_jtalk.exe",
        "./open_jtalk.exe",
        "../bin/open_jtalk.exe",
        "../../bin/open_jtalk.exe",
        "./build/oj/bin/open_jtalk.exe",
        "./build/Release/open_jtalk.exe"
    };
    
    for (int i = 0; i < sizeof(possible_paths)/sizeof(possible_paths[0]); i++) {
        if (_access(possible_paths[i], 0) == 0) {
            oj->openjtalk_path = _strdup(possible_paths[i]);
            break;
        }
    }
    
    if (!oj->openjtalk_path) {
        // Try to find in PATH
        char path[MAX_PATH];
        if (SearchPathA(NULL, "open_jtalk", ".exe", MAX_PATH, path, NULL)) {
            oj->openjtalk_path = _strdup(path);
        }
    }
    
    if (!oj->openjtalk_path) {
        LOG_ERROR("Failed to find open_jtalk.exe");
        free(oj);
        return NULL;
    }
    
    // Get dictionary path
    oj->dictionary_path = openjtalk_get_dict_path();
    if (!oj->dictionary_path) {
        LOG_ERROR("Failed to get dictionary path");
        free(oj->openjtalk_path);
        free(oj);
        return NULL;
    }
    
    return oj;
}

void openjtalk_finalize(OpenJTalk* oj) {
    if (oj) {
        if (oj->openjtalk_path) free(oj->openjtalk_path);
        if (oj->dictionary_path) free(oj->dictionary_path);
        free(oj);
    }
}

HTS_Label_Wrapper* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !text) return NULL;
    
    // Create temporary files
    char temp_path[MAX_PATH];
    char input_file[MAX_PATH];
    char output_file[MAX_PATH];
    
    GetTempPathA(MAX_PATH, temp_path);
    
    // Generate unique filenames
    snprintf(input_file, MAX_PATH, "%s\\openjtalk_input_%d.txt", temp_path, GetCurrentProcessId());
    snprintf(output_file, MAX_PATH, "%s\\openjtalk_output_%d.txt", temp_path, GetCurrentProcessId());
    
    // Write input text to file
    FILE* fp = fopen(input_file, "wb");
    if (!fp) {
        LOG_ERROR("Failed to create input file: %s", input_file);
        return NULL;
    }
    
    // Write UTF-8 BOM if text contains Japanese characters
    unsigned char utf8_bom[] = {0xEF, 0xBB, 0xBF};
    fwrite(utf8_bom, 1, 3, fp);
    fwrite(text, 1, strlen(text), fp);
    fclose(fp);
    
    // Build command line
    char command[4096];
    snprintf(command, sizeof(command),
             "\"%s\" -x \"%s\" -ot \"%s\" \"%s\"",
             oj->openjtalk_path,
             oj->dictionary_path,
             output_file,
             input_file);
    
    // Execute OpenJTalk
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));
    
    if (!CreateProcessA(NULL, command, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        LOG_ERROR("Failed to execute OpenJTalk: %s", command);
        _unlink(input_file);
        return NULL;
    }
    
    // Wait for process to complete
    WaitForSingleObject(pi.hProcess, INFINITE);
    
    DWORD exit_code;
    GetExitCodeProcess(pi.hProcess, &exit_code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    
    if (exit_code != 0) {
        LOG_ERROR("OpenJTalk exited with code %d", exit_code);
        _unlink(input_file);
        return NULL;
    }
    
    // Read output file
    fp = fopen(output_file, "rb");
    if (!fp) {
        LOG_ERROR("Failed to open output file: %s", output_file);
        _unlink(input_file);
        return NULL;
    }
    
    // Get file size
    fseek(fp, 0, SEEK_END);
    long file_size = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    
    // Skip BOM if present
    unsigned char bom[3];
    if (fread(bom, 1, 3, fp) == 3) {
        if (bom[0] != 0xEF || bom[1] != 0xBB || bom[2] != 0xBF) {
            fseek(fp, 0, SEEK_SET);
        }
    } else {
        fseek(fp, 0, SEEK_SET);
    }
    
    // Read file content
    char* buffer = (char*)malloc(file_size + 1);
    if (!buffer) {
        fclose(fp);
        _unlink(input_file);
        _unlink(output_file);
        return NULL;
    }
    
    size_t read_size = fread(buffer, 1, file_size, fp);
    buffer[read_size] = '\0';
    fclose(fp);
    
    // Parse labels
    HTS_Label_Wrapper* label = (HTS_Label_Wrapper*)malloc(sizeof(HTS_Label_Wrapper));
    if (!label) {
        free(buffer);
        _unlink(input_file);
        _unlink(output_file);
        return NULL;
    }
    
    // Count lines
    size_t num_lines = 0;
    char* p = buffer;
    while (*p) {
        if (*p == '\n') num_lines++;
        p++;
    }
    if (buffer[read_size-1] != '\n') num_lines++;
    
    // Allocate label array
    label->labels = (char**)malloc(num_lines * sizeof(char*));
    label->num_labels = 0;
    
    // Parse lines
    char* line = strtok(buffer, "\r\n");
    while (line) {
        if (strlen(line) > 0) {
            label->labels[label->num_labels] = _strdup(line);
            label->num_labels++;
        }
        line = strtok(NULL, "\r\n");
    }
    
    free(buffer);
    _unlink(input_file);
    _unlink(output_file);
    
    return label;
}

size_t HTS_Label_get_size(HTS_Label_Wrapper* label) {
    return label ? label->num_labels : 0;
}

const char* HTS_Label_get_string(HTS_Label_Wrapper* label, size_t index) {
    if (!label || index >= label->num_labels) return NULL;
    return label->labels[index];
}

void HTS_Label_clear(HTS_Label_Wrapper* label) {
    if (label) {
        for (size_t i = 0; i < label->num_labels; i++) {
            free(label->labels[i]);
        }
        free(label->labels);
        free(label);
    }
}

#endif // _WIN32