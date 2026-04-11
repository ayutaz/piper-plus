#ifndef _WIN32
#define _GNU_SOURCE
#endif

#include "openjtalk_optimized.h"
#include "openjtalk_dictionary_manager.h"
#include "openjtalk_error.h"
#include "openjtalk_security.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <process.h>
#define F_OK 0
#define access _access
#define popen _popen
#define pclose _pclose
#define strtok_r strtok_s
#else
#include <unistd.h>
#include <pthread.h>
#include <sys/wait.h>
#include <errno.h>
#include <poll.h>
#include <signal.h>
#endif

// Cache entry structure
typedef struct CacheEntry {
    char* text;
    char* phonemes;
    time_t timestamp;
    size_t memory_size;
    struct CacheEntry* next;
    struct CacheEntry* prev;
} CacheEntry;

// Cache structure (LRU implementation)
typedef struct {
    CacheEntry* head;
    CacheEntry* tail;
    size_t count;
    size_t memory_bytes;
    OpenJTalkCacheConfig config;
    OpenJTalkCacheStats stats;
#ifdef _WIN32
    CRITICAL_SECTION mutex;
#else
    pthread_mutex_t mutex;
#endif
} PhonemeCache;

// Global cache instance
static PhonemeCache* g_cache = NULL;

// Thread-local storage for dictionary path caching
#ifdef _WIN32
__declspec(thread) static char g_cached_dic_path[1024] = {0};
__declspec(thread) static time_t g_dic_path_timestamp = 0;
#else
static __thread char g_cached_dic_path[1024] = {0};
static __thread time_t g_dic_path_timestamp = 0;
#endif

// Forward declarations
static char* find_openjtalk_binary(void);
static CacheEntry* cache_lookup(const char* text);
static void cache_insert(const char* text, const char* phonemes);
static void cache_evict_lru(void);
static void cache_remove_entry(CacheEntry* entry);
static char* execute_with_pipes(const char* openjtalk_bin, const char* dic_path, const char* text);

#ifdef _WIN32
static char* execute_with_pipes_windows(const char* openjtalk_bin, const char* dic_path, const char* text);
#else
static char* execute_with_pipes_unix(const char* openjtalk_bin, const char* dic_path, const char* text);
#endif

// Initialize optimized OpenJTalk
bool openjtalk_optimized_init(const OpenJTalkCacheConfig* cache_config) {
    if (cache_config) {
        if (g_cache) {
            openjtalk_optimized_cleanup();
        }
        
        g_cache = calloc(1, sizeof(PhonemeCache));
        if (!g_cache) {
            return false;
        }
        
        g_cache->config = *cache_config;
        
#ifdef _WIN32
        InitializeCriticalSection(&g_cache->mutex);
#else
        pthread_mutex_init(&g_cache->mutex, NULL);
#endif
    }
    
    return true;
}

// Cleanup resources
void openjtalk_optimized_cleanup(void) {
    if (g_cache) {
#ifdef _WIN32
        EnterCriticalSection(&g_cache->mutex);
#else
        pthread_mutex_lock(&g_cache->mutex);
#endif
        
        // Free all cache entries
        CacheEntry* entry = g_cache->head;
        while (entry) {
            CacheEntry* next = entry->next;
            free(entry->text);
            free(entry->phonemes);
            free(entry);
            entry = next;
        }
        
#ifdef _WIN32
        LeaveCriticalSection(&g_cache->mutex);
        DeleteCriticalSection(&g_cache->mutex);
#else
        pthread_mutex_unlock(&g_cache->mutex);
        pthread_mutex_destroy(&g_cache->mutex);
#endif
        
        free(g_cache);
        g_cache = NULL;
    }
}

// Get cached dictionary path with TTL
static const char* get_cached_dictionary_path(void) {
    time_t now = time(NULL);
    
    // Cache dictionary path for 5 minutes
    if (g_cached_dic_path[0] != 0 && (now - g_dic_path_timestamp) < 300) {
        return g_cached_dic_path;
    }
    
    const char* dic_path = get_openjtalk_dictionary_path();
    if (dic_path) {
        strncpy(g_cached_dic_path, dic_path, sizeof(g_cached_dic_path) - 1);
        g_cached_dic_path[sizeof(g_cached_dic_path) - 1] = '\0';
        g_dic_path_timestamp = now;
    }
    
    return dic_path;
}

// Optimized text to phonemes conversion
char* openjtalk_text_to_phonemes_optimized(const char* text) {
    if (!text || strlen(text) == 0) {
        return NULL;
    }
    
    // Check cache first
    if (g_cache) {
        CacheEntry* cached = cache_lookup(text);
        if (cached) {
            return strdup(cached->phonemes);
        }
    }
    
    // Get dictionary path (with caching)
    const char* dic_path = get_cached_dictionary_path();
    if (!dic_path) {
        fprintf(stderr, "Failed to get OpenJTalk dictionary path\n");
        return NULL;
    }
    
    // Get OpenJTalk binary
    const char* openjtalk_bin = find_openjtalk_binary();
    if (!openjtalk_bin) {
        fprintf(stderr, "OpenJTalk binary not found\n");
        return NULL;
    }
    
    // Execute with pipes
    char* phonemes = execute_with_pipes(openjtalk_bin, dic_path, text);
    
    // Cache the result
    if (phonemes && g_cache) {
        cache_insert(text, phonemes);
    }
    
    return phonemes;
}

// Platform-specific pipe execution
static char* execute_with_pipes(const char* openjtalk_bin, const char* dic_path, const char* text) {
#ifdef _WIN32
    return execute_with_pipes_windows(openjtalk_bin, dic_path, text);
#else
    return execute_with_pipes_unix(openjtalk_bin, dic_path, text);
#endif
}

#ifndef _WIN32
// Unix implementation using fork/exec and pipes
static char* execute_with_pipes_unix(const char* openjtalk_bin, const char* dic_path, const char* text) {
    int stdin_pipe[2], stdout_pipe[2];
    pid_t pid;
    
    // Validate paths before execution
    if (!openjtalk_is_safe_path(openjtalk_bin) ||
        !openjtalk_is_safe_path(dic_path)) {
        return NULL;
    }

    // Create pipes
    if (pipe(stdin_pipe) == -1 || pipe(stdout_pipe) == -1) {
        perror("pipe");
        return NULL;
    }

    // Fork process
    pid = fork();
    if (pid == -1) {
        perror("fork");
        close(stdin_pipe[0]); close(stdin_pipe[1]);
        close(stdout_pipe[0]); close(stdout_pipe[1]);
        return NULL;
    }
    
    if (pid == 0) {
        // Child process
        close(stdin_pipe[1]);  // Close write end of stdin pipe
        close(stdout_pipe[0]); // Close read end of stdout pipe
        
        // Redirect stdin and stdout
        dup2(stdin_pipe[0], STDIN_FILENO);
        dup2(stdout_pipe[1], STDOUT_FILENO);
        
        // Close original file descriptors
        close(stdin_pipe[0]);
        close(stdout_pipe[1]);
        
        // Prepare arguments
        // Standard open_jtalk does not support "-" for stdin/stdout;
        // use /dev/stdin and /dev/stdout instead.
        int is_phonemizer = strstr(openjtalk_bin, "phonemizer") != NULL ? 1 : 0;

        if (is_phonemizer) {
            execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path, "-ot", "/dev/stdout", "/dev/stdin", NULL);
        } else {
            // open_jtalk fallback: phoneme extraction only
            execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path,
                   "-ow", "/dev/null", "-ot", "/dev/stdout", "/dev/stdin", NULL);
        }
        
        // If exec fails, use _exit() to avoid running atexit handlers
        // or C++ destructors that may deadlock on inherited locks.
        perror("execlp");
        _exit(1);
    }
    
    // Parent process
    close(stdin_pipe[0]);  // Close read end of stdin pipe
    close(stdout_pipe[1]); // Close write end of stdout pipe
    
    // Write input text to child's stdin
    size_t text_len = strlen(text);
    ssize_t written = write(stdin_pipe[1], text, text_len);
    close(stdin_pipe[1]);
    
    if (written != (ssize_t)text_len) {
        close(stdout_pipe[0]);
        waitpid(pid, NULL, 0);
        return NULL;
    }
    
    // Read output from child's stdout with timeout to prevent hangs
    char buffer[4096];
    size_t total_size = 0;
    size_t buffer_size = 4096;
    char* result = malloc(buffer_size);
    if (!result) {
        close(stdout_pipe[0]);
        kill(pid, SIGKILL);
        waitpid(pid, NULL, 0);
        return NULL;
    }
    result[0] = '\0';

    ssize_t bytes_read;
    struct pollfd pfd = { .fd = stdout_pipe[0], .events = POLLIN };
    const int timeout_ms = 15000; // 15 second timeout per read
    while (poll(&pfd, 1, timeout_ms) > 0 &&
           (bytes_read = read(stdout_pipe[0], buffer, sizeof(buffer) - 1)) > 0) {
        buffer[bytes_read] = '\0';
        
        // Parse phonemes from output
        char* line = strtok(buffer, "\n");
        while (line) {
            // Extract phoneme from full-context label
            char* minus_pos = strchr(line, '-');
            if (minus_pos) {
                char* plus_pos = strchr(minus_pos + 1, '+');
                if (plus_pos && plus_pos > minus_pos + 1) {
                    size_t phoneme_len = plus_pos - minus_pos - 1;
                    
                    // Resize buffer if needed
                    if (total_size + phoneme_len + 2 > buffer_size) {
                        buffer_size *= 2;
                        char* new_result = realloc(result, buffer_size);
                        if (!new_result) {
                            free(result);
                            close(stdout_pipe[0]);
                            waitpid(pid, NULL, 0);
                            return NULL;
                        }
                        result = new_result;
                    }
                    
                    // Add space if not first phoneme
                    if (total_size > 0) {
                        result[total_size++] = ' ';
                    }
                    
                    // Copy phoneme
                    memcpy(result + total_size, minus_pos + 1, phoneme_len);
                    total_size += phoneme_len;
                    result[total_size] = '\0';
                }
            }
            line = strtok(NULL, "\n");
        }
    }

    close(stdout_pipe[0]);

    // Wait for child with timeout — if still running, kill it
    int status;
    pid_t wait_result = waitpid(pid, &status, WNOHANG);
    if (wait_result == 0) {
        // Child still running — give it 2 more seconds, then kill
        usleep(2000000);
        wait_result = waitpid(pid, &status, WNOHANG);
        if (wait_result == 0) {
            kill(pid, SIGKILL);
            waitpid(pid, &status, 0);
        }
    }

    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        free(result);
        return NULL;
    }
    
    if (total_size == 0) {
        free(result);
        return NULL;
    }
    
    return result;
}
#endif

#ifdef _WIN32
// Windows implementation using CreateProcess and pipes
static char* execute_with_pipes_windows(const char* openjtalk_bin, const char* dic_path, const char* text) {
    SECURITY_ATTRIBUTES sa;
    HANDLE stdin_read, stdin_write;
    HANDLE stdout_read, stdout_write;
    STARTUPINFO si;
    PROCESS_INFORMATION pi;
    
    // Set up security attributes
    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.bInheritHandle = TRUE;
    sa.lpSecurityDescriptor = NULL;
    
    // Create pipes
    if (!CreatePipe(&stdin_read, &stdin_write, &sa, 0) ||
        !CreatePipe(&stdout_read, &stdout_write, &sa, 0)) {
        return NULL;
    }
    
    // Ensure handles are not inherited
    SetHandleInformation(stdin_write, HANDLE_FLAG_INHERIT, 0);
    SetHandleInformation(stdout_read, HANDLE_FLAG_INHERIT, 0);
    
    // Set up startup info
    ZeroMemory(&si, sizeof(STARTUPINFO));
    si.cb = sizeof(STARTUPINFO);
    si.hStdInput = stdin_read;
    si.hStdOutput = stdout_write;
    si.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    si.dwFlags |= STARTF_USESTDHANDLES;
    
    // Validate paths before command construction
    if (!openjtalk_is_safe_path(openjtalk_bin) ||
        !openjtalk_is_safe_path(dic_path)) {
        CloseHandle(stdin_read);
        CloseHandle(stdin_write);
        CloseHandle(stdout_read);
        CloseHandle(stdout_write);
        return NULL;
    }

    // Prepare command line
    char command[4096];
    int is_phonemizer = strstr(openjtalk_bin, "phonemizer") != NULL ? 1 : 0;

    // Pre-flight buffer length check to prevent silent truncation
    if (strlen(openjtalk_bin) + strlen(dic_path) + 64 > sizeof(command)) {
        CloseHandle(stdin_read);
        CloseHandle(stdin_write);
        CloseHandle(stdout_read);
        CloseHandle(stdout_write);
        return NULL;
    }

    if (is_phonemizer) {
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ot - -",
                 openjtalk_bin, dic_path);
    } else {
        // open_jtalk fallback: phoneme extraction only
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ow NUL -ot - -",
                 openjtalk_bin, dic_path);
    }
    
    // Create process
    if (!CreateProcess(NULL, command, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(stdin_read);
        CloseHandle(stdin_write);
        CloseHandle(stdout_read);
        CloseHandle(stdout_write);
        return NULL;
    }
    
    // Close unused handles
    CloseHandle(stdin_read);
    CloseHandle(stdout_write);
    
    // Write input text
    DWORD bytes_written;
    if (!WriteFile(stdin_write, text, strlen(text), &bytes_written, NULL)) {
        CloseHandle(stdin_write);
        CloseHandle(stdout_read);
        TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return NULL;
    }
    CloseHandle(stdin_write);
    
    // Read output
    char buffer[4096];
    size_t total_size = 0;
    size_t buffer_size = 4096;
    char* result = malloc(buffer_size);
    if (!result) {
        CloseHandle(stdout_read);
        TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return NULL;
    }
    result[0] = '\0';
    
    DWORD bytes_read;
    while (ReadFile(stdout_read, buffer, sizeof(buffer) - 1, &bytes_read, NULL) && bytes_read > 0) {
        buffer[bytes_read] = '\0';
        
        // Parse phonemes from output
        char* context = NULL;
        char* line = strtok_s(buffer, "\n", &context);
        while (line) {
            // Extract phoneme from full-context label
            char* minus_pos = strchr(line, '-');
            if (minus_pos) {
                char* plus_pos = strchr(minus_pos + 1, '+');
                if (plus_pos && plus_pos > minus_pos + 1) {
                    size_t phoneme_len = plus_pos - minus_pos - 1;
                    
                    // Resize buffer if needed
                    if (total_size + phoneme_len + 2 > buffer_size) {
                        buffer_size *= 2;
                        char* new_result = realloc(result, buffer_size);
                        if (!new_result) {
                            free(result);
                            CloseHandle(stdout_read);
                            TerminateProcess(pi.hProcess, 1);
                            CloseHandle(pi.hProcess);
                            CloseHandle(pi.hThread);
                            return NULL;
                        }
                        result = new_result;
                    }
                    
                    // Add space if not first phoneme
                    if (total_size > 0) {
                        result[total_size++] = ' ';
                    }
                    
                    // Copy phoneme
                    memcpy(result + total_size, minus_pos + 1, phoneme_len);
                    total_size += phoneme_len;
                    result[total_size] = '\0';
                }
            }
            line = strtok_s(NULL, "\n", &context);
        }
    }
    
    CloseHandle(stdout_read);
    
    // Wait for process to finish
    WaitForSingleObject(pi.hProcess, INFINITE);
    
    DWORD exit_code;
    GetExitCodeProcess(pi.hProcess, &exit_code);
    
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    
    if (exit_code != 0) {
        free(result);
        return NULL;
    }
    
    if (total_size == 0) {
        free(result);
        return NULL;
    }
    
    return result;
}
#endif

// Cache implementation
static CacheEntry* cache_lookup(const char* text) {
    if (!g_cache) return NULL;
    
#ifdef _WIN32
    EnterCriticalSection(&g_cache->mutex);
#else
    pthread_mutex_lock(&g_cache->mutex);
#endif
    
    g_cache->stats.total_requests++;
    
    CacheEntry* entry = g_cache->head;
    while (entry) {
        if (strcmp(entry->text, text) == 0) {
            // Check TTL
            if (g_cache->config.ttl_seconds > 0) {
                time_t now = time(NULL);
                if (now - entry->timestamp > g_cache->config.ttl_seconds) {
                    // Entry expired
                    cache_remove_entry(entry);
                    g_cache->stats.cache_misses++;
#ifdef _WIN32
                    LeaveCriticalSection(&g_cache->mutex);
#else
                    pthread_mutex_unlock(&g_cache->mutex);
#endif
                    return NULL;
                }
            }
            
            // Move to front (LRU)
            if (entry != g_cache->head) {
                // Remove from current position
                if (entry->prev) entry->prev->next = entry->next;
                if (entry->next) entry->next->prev = entry->prev;
                if (entry == g_cache->tail) g_cache->tail = entry->prev;
                
                // Insert at head
                entry->prev = NULL;
                entry->next = g_cache->head;
                g_cache->head->prev = entry;
                g_cache->head = entry;
            }
            
            g_cache->stats.cache_hits++;
#ifdef _WIN32
            LeaveCriticalSection(&g_cache->mutex);
#else
            pthread_mutex_unlock(&g_cache->mutex);
#endif
            return entry;
        }
        entry = entry->next;
    }
    
    g_cache->stats.cache_misses++;
#ifdef _WIN32
    LeaveCriticalSection(&g_cache->mutex);
#else
    pthread_mutex_unlock(&g_cache->mutex);
#endif
    return NULL;
}

static void cache_insert(const char* text, const char* phonemes) {
    if (!g_cache) return;
    
#ifdef _WIN32
    EnterCriticalSection(&g_cache->mutex);
#else
    pthread_mutex_lock(&g_cache->mutex);
#endif
    
    // Calculate memory size
    size_t text_len = strlen(text) + 1;
    size_t phonemes_len = strlen(phonemes) + 1;
    size_t entry_size = sizeof(CacheEntry) + text_len + phonemes_len;
    
    // Check memory limit
    while (g_cache->config.max_memory_bytes > 0 && 
           g_cache->memory_bytes + entry_size > g_cache->config.max_memory_bytes) {
        cache_evict_lru();
    }
    
    // Check entry count limit
    while (g_cache->config.max_entries > 0 && 
           g_cache->count >= g_cache->config.max_entries) {
        cache_evict_lru();
    }
    
    // Create new entry
    CacheEntry* entry = malloc(sizeof(CacheEntry));
    if (!entry) {
#ifdef _WIN32
        LeaveCriticalSection(&g_cache->mutex);
#else
        pthread_mutex_unlock(&g_cache->mutex);
#endif
        return;
    }
    
    entry->text = strdup(text);
    entry->phonemes = strdup(phonemes);
    entry->timestamp = time(NULL);
    entry->memory_size = entry_size;
    entry->prev = NULL;
    entry->next = g_cache->head;
    
    if (!entry->text || !entry->phonemes) {
        free(entry->text);
        free(entry->phonemes);
        free(entry);
#ifdef _WIN32
        LeaveCriticalSection(&g_cache->mutex);
#else
        pthread_mutex_unlock(&g_cache->mutex);
#endif
        return;
    }
    
    // Insert at head
    if (g_cache->head) {
        g_cache->head->prev = entry;
    } else {
        g_cache->tail = entry;
    }
    g_cache->head = entry;
    
    g_cache->count++;
    g_cache->memory_bytes += entry_size;
    g_cache->stats.current_entries = g_cache->count;
    g_cache->stats.current_memory_bytes = g_cache->memory_bytes;
    
#ifdef _WIN32
    LeaveCriticalSection(&g_cache->mutex);
#else
    pthread_mutex_unlock(&g_cache->mutex);
#endif
}

static void cache_evict_lru(void) {
    if (!g_cache || !g_cache->tail) return;
    cache_remove_entry(g_cache->tail);
}

static void cache_remove_entry(CacheEntry* entry) {
    if (!entry) return;
    
    // Update links
    if (entry->prev) {
        entry->prev->next = entry->next;
    } else {
        g_cache->head = entry->next;
    }
    
    if (entry->next) {
        entry->next->prev = entry->prev;
    } else {
        g_cache->tail = entry->prev;
    }
    
    // Update stats
    g_cache->count--;
    g_cache->memory_bytes -= entry->memory_size;
    g_cache->stats.current_entries = g_cache->count;
    g_cache->stats.current_memory_bytes = g_cache->memory_bytes;
    
    // Free memory
    free(entry->text);
    free(entry->phonemes);
    free(entry);
}

// Clear cache
void openjtalk_clear_cache(void) {
    if (!g_cache) return;
    
#ifdef _WIN32
    EnterCriticalSection(&g_cache->mutex);
#else
    pthread_mutex_lock(&g_cache->mutex);
#endif
    
    CacheEntry* entry = g_cache->head;
    while (entry) {
        CacheEntry* next = entry->next;
        free(entry->text);
        free(entry->phonemes);
        free(entry);
        entry = next;
    }
    
    g_cache->head = NULL;
    g_cache->tail = NULL;
    g_cache->count = 0;
    g_cache->memory_bytes = 0;
    g_cache->stats.current_entries = 0;
    g_cache->stats.current_memory_bytes = 0;
    
#ifdef _WIN32
    LeaveCriticalSection(&g_cache->mutex);
#else
    pthread_mutex_unlock(&g_cache->mutex);
#endif
}

// Get cache statistics
void openjtalk_get_cache_stats(OpenJTalkCacheStats* stats) {
    if (!stats || !g_cache) return;
    
#ifdef _WIN32
    EnterCriticalSection(&g_cache->mutex);
#else
    pthread_mutex_lock(&g_cache->mutex);
#endif
    
    *stats = g_cache->stats;
    
#ifdef _WIN32
    LeaveCriticalSection(&g_cache->mutex);
#else
    pthread_mutex_unlock(&g_cache->mutex);
#endif
}

// Find OpenJTalk binary (reuse from original implementation)
static char* find_openjtalk_binary(void) {
    // Thread-local cache for binary path
#ifdef _WIN32
    __declspec(thread) static char binary_path[1024] = {0};
#else
    static __thread char binary_path[1024] = {0};
#endif
    
    if (binary_path[0] != '\0') {
        return binary_path;
    }
    
    // Check common locations
    const char* paths[] = {
#ifdef _WIN32
        "open_jtalk_phonemizer.exe",
        "bin\\open_jtalk_phonemizer.exe",
        "open_jtalk.exe",
        "bin\\open_jtalk.exe",
#else
        "./open_jtalk_phonemizer",
        "./bin/open_jtalk_phonemizer",
        "/usr/bin/open_jtalk_phonemizer",
        "/usr/local/bin/open_jtalk_phonemizer",
        "/opt/homebrew/bin/open_jtalk_phonemizer",
        "./open_jtalk",
        "./bin/open_jtalk",
        "/usr/bin/open_jtalk",
        "/usr/local/bin/open_jtalk",
        "/opt/homebrew/bin/open_jtalk",
#endif
        NULL
    };
    
    for (int i = 0; paths[i] != NULL; i++) {
        if (access(paths[i], F_OK) == 0) {
            strncpy(binary_path, paths[i], sizeof(binary_path) - 1);
            binary_path[sizeof(binary_path) - 1] = '\0';
            return binary_path;
        }
    }
    
    // Try PATH lookup
#ifdef _WIN32
    FILE* fp = popen("where open_jtalk_phonemizer.exe 2>NUL", "r");
    if (!fp || fgets(binary_path, sizeof(binary_path), fp) == NULL) {
        if (fp) pclose(fp);
        fp = popen("where open_jtalk.exe 2>NUL", "r");
    }
#else
    FILE* fp = popen("which open_jtalk_phonemizer 2>/dev/null", "r");
    if (!fp || fgets(binary_path, sizeof(binary_path), fp) == NULL) {
        if (fp) pclose(fp);
        fp = popen("which open_jtalk 2>/dev/null", "r");
    }
#endif
    
    if (fp) {
        if (fgets(binary_path, sizeof(binary_path), fp) != NULL) {
            // Remove newline
            size_t len = strlen(binary_path);
            if (len > 0 && binary_path[len-1] == '\n') {
                binary_path[len-1] = '\0';
            }
            pclose(fp);
            return binary_path;
        }
        pclose(fp);
    }
    
    binary_path[0] = '\0';
    return NULL;
}