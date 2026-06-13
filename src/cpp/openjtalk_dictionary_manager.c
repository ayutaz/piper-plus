#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <sys/stat.h>
#include <ctype.h>

#include "piper_proc_exec.h"
#include "safe_exec.h"

#ifdef _WIN32
#include <windows.h>
#include <direct.h>
#include <io.h>
#define mkdir(path, mode) _mkdir(path)
#define access _access
#define F_OK 0
#define X_OK 0
#define popen _popen
#define pclose _pclose
#elif defined(__APPLE__)
#include <unistd.h>
#include <mach-o/dyld.h>
#else
#include <unistd.h>
#endif

// Dictionary download URL
#define DICTIONARY_URL "https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz"
#define DICTIONARY_FILENAME "open_jtalk_dic_utf_8-1.11.tar.gz"
#define DICTIONARY_DIR "open_jtalk_dic_utf_8-1.11"
#define DICTIONARY_SHA256 "fe6ba0e43542cef98339abdffd903e062008ea170b04e7e2a35da805902f382a"

// Helper function to verify SHA256 checksum
static int verify_checksum(const char* file_path, const char* expected_sha256) {
    char result[256] = {0};
    size_t bytes_read = 0;
    int spawn_rc = -1;

    fprintf(stderr, "Verifying checksum...\n");

#ifdef _WIN32
    // PowerShell -Command does NOT bind trailing positional arguments to
    // $args (only -File does), so the previous "-Path $args[0]" form left the
    // path empty. Pass it via an environment variable instead: it is inherited
    // by the child process and never re-parsed as code (injection-safe).
    _putenv_s("PIPER_HASH_PATH", file_path);
    const char* const argv[] = {
        "powershell", "-NoProfile", "-Command",
        "(Get-FileHash -Path $env:PIPER_HASH_PATH -Algorithm SHA256).Hash",
        NULL,
    };
    spawn_rc = piper_capture_argv(argv, result, sizeof(result), &bytes_read);
    _putenv_s("PIPER_HASH_PATH", "");
#else
    // Probe for sha256sum / shasum at fixed paths (skip `which`, which
    // would re-introduce a shell sink that CodeQL flags).
    static const char* const SHA256SUM_PATHS[] = {
        "/usr/bin/sha256sum", "/usr/local/bin/sha256sum", "/bin/sha256sum",
        "/opt/homebrew/bin/sha256sum", NULL,
    };
    static const char* const SHASUM_PATHS[] = {
        "/usr/bin/shasum", "/usr/local/bin/shasum", "/bin/shasum",
        "/opt/homebrew/bin/shasum", NULL,
    };
    const char* sha256sum_bin = NULL;
    for (size_t i = 0; SHA256SUM_PATHS[i]; i++) {
        if (access(SHA256SUM_PATHS[i], X_OK) == 0) {
            sha256sum_bin = SHA256SUM_PATHS[i];
            break;
        }
    }
    if (sha256sum_bin) {
        const char* const argv[] = {sha256sum_bin, file_path, NULL};
        spawn_rc = piper_capture_argv(argv, result, sizeof(result), &bytes_read);
    } else {
        const char* shasum_bin = NULL;
        for (size_t i = 0; SHASUM_PATHS[i]; i++) {
            if (access(SHASUM_PATHS[i], X_OK) == 0) {
                shasum_bin = SHASUM_PATHS[i];
                break;
            }
        }
        if (shasum_bin) {
            const char* const argv[] = {shasum_bin, "-a", "256", file_path, NULL};
            spawn_rc = piper_capture_argv(argv, result, sizeof(result), &bytes_read);
        } else {
            fprintf(stderr, "Warning: No checksum tool available, skipping verification\n");
            return 0;
        }
    }
#endif

    if (spawn_rc != 0 || bytes_read == 0) {
        fprintf(stderr, "Warning: Failed to compute checksum, skipping verification\n");
        return 0;
    }

    // Strip trailing newline if present.
    {
        size_t len = strlen(result);
        if (len > 0 && result[len - 1] == '\n') {
            result[len - 1] = '\0';
        }
    }

    // sha256sum / shasum emit "<hash>  <filename>"; truncate at the first
    // whitespace so we are left with the bare hash token. PowerShell's
    // Get-FileHash emits just the hash, but the same trim is harmless.
    for (int i = 0; result[i]; i++) {
        if (result[i] == ' ' || result[i] == '\t') {
            result[i] = '\0';
            break;
        }
    }

    // Convert to lowercase for case-insensitive comparison.
    for (int i = 0; result[i]; i++) {
        result[i] = (char)tolower((unsigned char)result[i]);
    }

    char expected_lower[256];
    strncpy(expected_lower, expected_sha256, sizeof(expected_lower) - 1);
    expected_lower[sizeof(expected_lower) - 1] = '\0';
    for (int i = 0; expected_lower[i]; i++) {
        expected_lower[i] = (char)tolower((unsigned char)expected_lower[i]);
    }

    if (strcmp(result, expected_lower) == 0) {
        fprintf(stderr, "Checksum verified successfully\n");
        return 0;
    }
    fprintf(stderr, "Error: Checksum mismatch! Expected %s, got %s\n",
            expected_sha256, result);
    return -1;
}

// Helper function to create directory with parents
static int mkdir_p(const char* path) {
    char tmp[1024];
    char* p = NULL;
    size_t len;

    snprintf(tmp, sizeof(tmp), "%s", path);
    len = strlen(tmp);
    if (tmp[len - 1] == '/')
        tmp[len - 1] = 0;

    for (p = tmp + 1; *p; p++) {
        if (*p == '/' || *p == '\\') {
            *p = 0;
            mkdir(tmp, 0755);
            *p = '/';
        }
    }
    mkdir(tmp, 0755);
    return 0;
}

// Get the base directory for data files
static const char* get_data_dir() {
    static char data_dir[1024] = {0};

    if (data_dir[0] != '\0') {
        return data_dir;
    }

    // Check environment variable first
    const char* env_dir = getenv("OPENJTALK_DATA_DIR");
    if (env_dir && access(env_dir, F_OK) == 0) {
        strncpy(data_dir, env_dir, sizeof(data_dir) - 1);
        return data_dir;
    }

#ifdef _WIN32
    // On Windows, try AppData
    const char* appdata = getenv("APPDATA");
    if (appdata) {
        snprintf(data_dir, sizeof(data_dir), "%s\\piper", appdata);
    } else {
        // Fallback to current directory
        GetCurrentDirectoryA(sizeof(data_dir) - 10, data_dir);
        strcat(data_dir, "\\data");
    }
#elif defined(__ANDROID__)
    // Android: use app-specific external files dir if set, otherwise /data/local/tmp
    const char* xdg_data = getenv("XDG_DATA_HOME");
    if (xdg_data) {
        snprintf(data_dir, sizeof(data_dir), "%s/piper", xdg_data);
    } else {
        const char* ext_files = getenv("PIPER_DATA_DIR");
        if (ext_files) {
            snprintf(data_dir, sizeof(data_dir), "%s/piper", ext_files);
        } else {
            // Fallback: /data/local/tmp is writable on most devices
            strcpy(data_dir, "/data/local/tmp/piper");
        }
    }
#else
    // On Unix-like systems, use XDG_DATA_HOME or ~/.local/share
    const char* xdg_data = getenv("XDG_DATA_HOME");
    if (xdg_data) {
        snprintf(data_dir, sizeof(data_dir), "%s/piper", xdg_data);
    } else {
        const char* home = getenv("HOME");
        if (home) {
            snprintf(data_dir, sizeof(data_dir), "%s/.local/share/piper", home);
        } else {
            // Fallback to /tmp
            strcpy(data_dir, "/tmp/piper");
        }
    }
#endif

    // Create directory if it doesn't exist
    struct stat st = {0};
    if (stat(data_dir, &st) == -1) {
        mkdir_p(data_dir);
    }

    return data_dir;
}

// Get dictionary path relative to the running executable
// Looks for <exe_dir>/../share/open_jtalk/dic
static const char* get_exe_relative_dict_path() {
    static char exe_dict_path[1024] = {0};
    char exe_path[1024] = {0};

#ifdef _WIN32
    DWORD len = GetModuleFileNameA(NULL, exe_path, sizeof(exe_path));
    if (len == 0 || len >= sizeof(exe_path)) {
        return NULL;
    }
    // Find last backslash to get directory
    char* last_sep = strrchr(exe_path, '\\');
    if (!last_sep) {
        last_sep = strrchr(exe_path, '/');
    }
    if (!last_sep) {
        return NULL;
    }
    *last_sep = '\0';
    snprintf(exe_dict_path, sizeof(exe_dict_path),
             "%s\\..\\share\\open_jtalk\\dic", exe_path);
#elif defined(__APPLE__)
    uint32_t buf_size = sizeof(exe_path);
    if (_NSGetExecutablePath(exe_path, &buf_size) != 0) {
        return NULL;
    }
    // Find last slash to get directory
    char* last_sep = strrchr(exe_path, '/');
    if (!last_sep) {
        return NULL;
    }
    *last_sep = '\0';
    snprintf(exe_dict_path, sizeof(exe_dict_path),
             "%s/../share/open_jtalk/dic", exe_path);
#else
    ssize_t len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
    if (len <= 0) {
        return NULL;
    }
    exe_path[len] = '\0';
    // Find last slash to get directory
    char* last_sep = strrchr(exe_path, '/');
    if (!last_sep) {
        return NULL;
    }
    *last_sep = '\0';
    snprintf(exe_dict_path, sizeof(exe_dict_path),
             "%s/../share/open_jtalk/dic", exe_path);
#endif

    if (access(exe_dict_path, F_OK) == 0) {
        return exe_dict_path;
    }
    return NULL;
}

// Get the path to the OpenJTalk dictionary
const char* get_openjtalk_dictionary_path() {
    static char dict_path[1024] = {0};

    if (dict_path[0] != '\0') {
        return dict_path;
    }

    // Check environment variable first
    const char* env_dict = getenv("OPENJTALK_DICTIONARY_PATH");
    if (env_dict && access(env_dict, F_OK) == 0) {
        strncpy(dict_path, env_dict, sizeof(dict_path) - 1);
        return dict_path;
    }

    // Check relative to executable binary
    const char* exe_rel = get_exe_relative_dict_path();
    if (exe_rel) {
        strncpy(dict_path, exe_rel, sizeof(dict_path) - 1);
        return dict_path;
    }

    // Check common system locations
    const char* system_paths[] = {
#ifdef _WIN32
        "C:\\Program Files\\open_jtalk\\dic",
        "C:\\Program Files (x86)\\open_jtalk\\dic",
#elif defined(__ANDROID__)
        // Android: app assets or data directory (set by host app via env or dict_dir)
        "/data/local/tmp/open_jtalk/dic",
#else
        "/usr/share/open_jtalk/dic",
        "/usr/local/share/open_jtalk/dic",
        "/opt/open_jtalk/dic",
#endif
        NULL
    };

    for (int i = 0; system_paths[i] != NULL; i++) {
        if (access(system_paths[i], F_OK) == 0) {
            strncpy(dict_path, system_paths[i], sizeof(dict_path) - 1);
            return dict_path;
        }
    }

    // Use local data directory
    const char* data_dir = get_data_dir();
    snprintf(dict_path, sizeof(dict_path), "%s/%s", data_dir, DICTIONARY_DIR);

    return dict_path;
}

// Reset the cached dictionary path (for testing only).
// If override_path is non-NULL, force the cache to that path
// (useful for pointing at a non-existent path in tests).
void reset_openjtalk_dictionary_cache(void) {
    char* path = (char*)get_openjtalk_dictionary_path();
    if (path) {
        path[0] = '\0';
    }
}

// Force the cached dictionary path to a specific value (for testing).
void force_openjtalk_dictionary_path(const char* path) {
    char* cached = (char*)get_openjtalk_dictionary_path();
    if (cached && path) {
        strncpy(cached, path, 1023);
        cached[1023] = '\0';
    }
}

// Download and extract the dictionary
static int download_and_extract_dictionary() {
    const char* data_dir = get_data_dir();
    char archive_path[1024];

    snprintf(archive_path, sizeof(archive_path), "%s/%s", data_dir, DICTIONARY_FILENAME);

    // Download the dictionary archive
    fprintf(stderr, "Downloading OpenJTalk dictionary from %s...\n", DICTIONARY_URL);

    int download_rc = -1;

#ifdef _WIN32
    {
        // PowerShell -Command does not bind positional args to $args; pass the
        // URL / OutFile via environment variables (inherited by the child, not
        // re-parsed as code) instead. See model_manager.cpp downloadFile() for
        // the full rationale.
        _putenv_s("PIPER_DL_URI", DICTIONARY_URL);
        _putenv_s("PIPER_DL_OUT", archive_path);
        const char* const argv[] = {
            "powershell", "-NoProfile", "-Command",
            "Invoke-WebRequest -Uri $env:PIPER_DL_URI -OutFile $env:PIPER_DL_OUT",
            NULL,
        };
        download_rc = piper_run_argv(argv);
        _putenv_s("PIPER_DL_URI", "");
        _putenv_s("PIPER_DL_OUT", "");
    }
#else
    // Probe for curl / wget at fixed paths (avoids shell-based `which`).
    static const char* const CURL_PATHS[] = {
        "/usr/bin/curl", "/usr/local/bin/curl", "/opt/homebrew/bin/curl",
        "/bin/curl", NULL,
    };
    static const char* const WGET_PATHS[] = {
        "/usr/bin/wget", "/usr/local/bin/wget", "/opt/homebrew/bin/wget",
        "/bin/wget", NULL,
    };
    const char* curl_bin = NULL;
    for (size_t i = 0; CURL_PATHS[i]; i++) {
        if (access(CURL_PATHS[i], X_OK) == 0) { curl_bin = CURL_PATHS[i]; break; }
    }
    if (curl_bin) {
        const char* const argv[] = {
            curl_bin, "-L", "-o", archive_path, DICTIONARY_URL, NULL,
        };
        download_rc = piper_run_argv(argv);
    } else {
        const char* wget_bin = NULL;
        for (size_t i = 0; WGET_PATHS[i]; i++) {
            if (access(WGET_PATHS[i], X_OK) == 0) { wget_bin = WGET_PATHS[i]; break; }
        }
        if (wget_bin) {
            const char* const argv[] = {
                wget_bin, "-O", archive_path, DICTIONARY_URL, NULL,
            };
            download_rc = piper_run_argv(argv);
        } else {
            fprintf(stderr, "Error: Neither curl nor wget is available for downloading\n");
            return -1;
        }
    }
#endif

    if (download_rc != 0) {
        fprintf(stderr, "Error: Failed to download dictionary\n");
        return -1;
    }

    // Verify checksum
    if (verify_checksum(archive_path, DICTIONARY_SHA256) != 0) {
        fprintf(stderr, "Error: Dictionary download corrupted\n");
        unlink(archive_path);
        return -1;
    }

    // Extract the archive
    fprintf(stderr, "Extracting dictionary...\n");

    // tar -xzf <archive> -C <data_dir>: use BSD tar's -C flag so we don't
    // need a shell `cd && tar` chain. Each argument is passed verbatim
    // through posix_spawnp, eliminating shell metacharacter parsing.
    {
        const char* const argv[] = {
            "tar", "-xzf", archive_path, "-C", data_dir, NULL,
        };
        if (piper_run_argv(argv) != 0) {
            fprintf(stderr, "Error: Failed to extract dictionary\n");
            unlink(archive_path);
            return -1;
        }
    }

    // Clean up archive
    unlink(archive_path);

    fprintf(stderr, "OpenJTalk dictionary installed successfully\n");
    return 0;
}

// Ensure the OpenJTalk dictionary is available
int ensure_openjtalk_dictionary() {
    const char* dict_path = get_openjtalk_dictionary_path();

    // Check if dictionary already exists
    if (access(dict_path, F_OK) == 0) {
        return 0;
    }

    // Check if we're in offline mode
    const char* offline_mode = getenv("PIPER_OFFLINE_MODE");
    if (offline_mode && strcmp(offline_mode, "1") == 0) {
        fprintf(stderr, "Failed to ensure OpenJTalk dictionary: Offline mode is enabled. Please download and install the dictionary manually.\n");
        return -1;
    }

#ifdef __ANDROID__
    // Android: system()/popen() for curl/wget is not available.
    // The host app must provide the dictionary via dict_dir or OPENJTALK_DICTIONARY_PATH.
    fprintf(stderr, "Failed to ensure OpenJTalk dictionary: Auto-download is not supported on Android. "
                    "Please provide the dictionary via OPENJTALK_DICTIONARY_PATH or the dict_dir API parameter.\n");
    return -1;
#endif

    // Check if auto-download is disabled
    const char* auto_download = getenv("PIPER_AUTO_DOWNLOAD_DICT");
    if (auto_download && strcmp(auto_download, "0") == 0) {
        fprintf(stderr, "Failed to ensure OpenJTalk dictionary: Auto-download is disabled. Please download and install the dictionary manually.\n");
        return -1;
    }

    // Download and extract dictionary
    return download_and_extract_dictionary();
}
