#include "openjtalk_wrapper.h"
#include "openjtalk_dictionary_manager.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef _WIN32
#include <unistd.h>
#include <sys/wait.h>
#include <limits.h>  // for PATH_MAX
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
        NULL
    };
    
    oj->openjtalk_bin = NULL;
    for (int i = 0; possible_paths[i] != NULL; i++) {
        if (access(possible_paths[i], X_OK) == 0) {
            oj->openjtalk_bin = strdup(possible_paths[i]);
            break;
        }
    }
    
    if (!oj->openjtalk_bin) {
        // Try using 'which' command as last resort
        FILE* fp = popen("which open_jtalk 2>/dev/null", "r");
        if (fp) {
            char path[PATH_MAX];
            if (fgets(path, sizeof(path), fp)) {
                // Remove trailing newline
                size_t len = strlen(path);
                if (len > 0 && path[len-1] == '\n') {
                    path[len-1] = '\0';
                }
                oj->openjtalk_bin = strdup(path);
            }
            pclose(fp);
        }
    }
    
    if (!oj->openjtalk_bin) {
        fprintf(stderr, "open_jtalk binary not found\n");
        free(oj);
        return NULL;
    }
    
    oj->dic_path = strdup(dic_path);
    oj->initialized = 1;
    
    return (OpenJTalk*)oj;
}

void openjtalk_finalize(OpenJTalk* oj) {
    if (!oj) return;
    
    struct OpenJTalk_impl* impl = (struct OpenJTalk_impl*)oj;
    
    if (impl->dic_path) {
        free(impl->dic_path);
    }
    if (impl->openjtalk_bin) {
        free(impl->openjtalk_bin);
    }
    
    free(impl);
}

HTS_Label_Wrapper* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    if (!oj || !text) return NULL;
    
    struct OpenJTalk_impl* impl = (struct OpenJTalk_impl*)oj;
    if (!impl->initialized) return NULL;
    
    // Create temporary files
    char input_file[] = "/tmp/openjtalk_input_XXXXXX";
    char output_file[] = "/tmp/openjtalk_output_XXXXXX";
    
    int input_fd = mkstemp(input_file);
    if (input_fd < 0) {
        fprintf(stderr, "Failed to create temp input file\n");
        return NULL;
    }
    
    // Write text to input file
    FILE* fp = fdopen(input_fd, "w");
    if (!fp) {
        close(input_fd);
        unlink(input_file);
        return NULL;
    }
    
    // Write UTF-8 BOM to ensure proper encoding
    fprintf(fp, "\xEF\xBB\xBF%s", text);
    fclose(fp);
    
    int output_fd = mkstemp(output_file);
    if (output_fd < 0) {
        unlink(input_file);
        return NULL;
    }
    close(output_fd);  // We just need the filename
    
    // Build command
    char* command = malloc(4096);
    if (!command) {
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    snprintf(command, 4096, "%s -x %s -ot %s %s > /dev/null 2>&1",
             impl->openjtalk_bin, impl->dic_path, output_file, input_file);
    
    // Execute OpenJTalk
    int ret = system(command);
    free(command);
    
    if (ret != 0) {
        fprintf(stderr, "OpenJTalk command failed with code %d\n", ret);
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    // Read output file
    fp = fopen(output_file, "r");
    if (!fp) {
        fprintf(stderr, "Failed to open output file\n");
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    // Create label wrapper
    struct HTS_Label_Wrapper_impl* label = calloc(1, sizeof(struct HTS_Label_Wrapper_impl));
    if (!label) {
        fclose(fp);
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    label->capacity = 100;
    label->labels = malloc(label->capacity * sizeof(char*));
    if (!label->labels) {
        free(label);
        fclose(fp);
        unlink(input_file);
        unlink(output_file);
        return NULL;
    }
    
    // Read labels from file, skipping BOM if present
    char line[4096];
    int first_line = 1;
    
    while (fgets(line, sizeof(line), fp)) {
        // Skip BOM on first line if present
        char* line_start = line;
        if (first_line && line[0] == '\xEF' && line[1] == '\xBB' && line[2] == '\xBF') {
            line_start += 3;
        }
        first_line = 0;
        
        // Remove newline
        size_t len = strlen(line_start);
        if (len > 0 && line_start[len-1] == '\n') {
            line_start[len-1] = '\0';
            len--;
        }
        if (len > 0 && line_start[len-1] == '\r') {
            line_start[len-1] = '\0';
        }
        
        // Skip empty lines
        if (strlen(line_start) == 0) continue;
        
        // Grow array if needed
        if (label->size >= label->capacity) {
            label->capacity *= 2;
            char** new_labels = realloc(label->labels, label->capacity * sizeof(char*));
            if (!new_labels) {
                // Clean up on error
                for (size_t i = 0; i < label->size; i++) {
                    free(label->labels[i]);
                }
                free(label->labels);
                free(label);
                fclose(fp);
                unlink(input_file);
                unlink(output_file);
                return NULL;
            }
            label->labels = new_labels;
        }
        
        // Store label
        label->labels[label->size] = strdup(line_start);
        if (!label->labels[label->size]) {
            // Clean up on error
            for (size_t i = 0; i < label->size; i++) {
                free(label->labels[i]);
            }
            free(label->labels);
            free(label);
            fclose(fp);
            unlink(input_file);
            unlink(output_file);
            return NULL;
        }
        label->size++;
    }
    
    fclose(fp);
    unlink(input_file);
    unlink(output_file);
    
    return (HTS_Label_Wrapper*)label;
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

int openjtalk_get_label_index(HTS_Label_Wrapper* label, size_t index, size_t* start_index, size_t* end_index) {
    if (!label || !start_index || !end_index) return -1;
    
    struct HTS_Label_Wrapper_impl* impl = (struct HTS_Label_Wrapper_impl*)label;
    if (index >= impl->size) return -1;
    
    const char* label_str = impl->labels[index];
    
    // Parse timing information from label
    // Format: "start_time end_time phoneme_context"
    char* endptr;
    long start = strtol(label_str, &endptr, 10);
    if (*endptr != ' ') return -1;
    
    long end = strtol(endptr + 1, &endptr, 10);
    if (*endptr != ' ') return -1;
    
    *start_index = (size_t)start;
    *end_index = (size_t)end;
    
    return 0;
}

const char* openjtalk_get_label_phoneme(HTS_Label_Wrapper* label, size_t index) {
    if (!label) return NULL;
    
    struct HTS_Label_Wrapper_impl* impl = (struct HTS_Label_Wrapper_impl*)label;
    if (index >= impl->size) return NULL;
    
    const char* label_str = impl->labels[index];
    
    // Skip timing information
    const char* p = label_str;
    
    // Skip start time
    while (*p && *p != ' ') p++;
    if (!*p) return NULL;
    p++;
    
    // Skip end time
    while (*p && *p != ' ') p++;
    if (!*p) return NULL;
    p++;
    
    // Extract phoneme from context
    // Look for "-" and "+" markers
    const char* phoneme_start = p;
    while (*p && *p != '-' && *p != '+') p++;
    
    static char phoneme_buffer[256];
    size_t len = p - phoneme_start;
    if (len >= sizeof(phoneme_buffer)) len = sizeof(phoneme_buffer) - 1;
    strncpy(phoneme_buffer, phoneme_start, len);
    phoneme_buffer[len] = '\0';
    
    return phoneme_buffer;
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

// Windows stub implementation - OpenJTalk is not yet supported on Windows
// These are placeholder definitions to allow compilation

struct OpenJTalk_impl {
    int dummy;  // Placeholder
};

struct HTS_Label_Wrapper_impl {
    int dummy;  // Placeholder
};

OpenJTalk* openjtalk_initialize() {
    // OpenJTalk is not yet supported on Windows
    return NULL;
}

void openjtalk_finalize(OpenJTalk* oj) {
    // No-op on Windows
    (void)oj;
}

HTS_Label_Wrapper* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text) {
    // OpenJTalk is not yet supported on Windows
    (void)oj;
    (void)text;
    return NULL;
}

size_t HTS_Label_get_size(HTS_Label_Wrapper* label) {
    // OpenJTalk is not yet supported on Windows
    (void)label;
    return 0;
}

const char* HTS_Label_get_string(HTS_Label_Wrapper* label, size_t index) {
    // OpenJTalk is not yet supported on Windows
    (void)label;
    (void)index;
    return NULL;
}

void HTS_Label_clear(HTS_Label_Wrapper* label) {
    // OpenJTalk is not yet supported on Windows
    (void)label;
}

#endif // _WIN32