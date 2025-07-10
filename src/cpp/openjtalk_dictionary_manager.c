#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <sys/stat.h>
#include <ctype.h>

#ifdef _WIN32
#include <windows.h>
#include <direct.h>
#include <io.h>
#define mkdir(path, mode) _mkdir(path)
#define access _access
#define F_OK 0
#define popen _popen
#define pclose _pclose
#else
#include <unistd.h>
#endif

// Dictionary download URL
#define DICTIONARY_URL "https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz"
#define DICTIONARY_FILENAME "open_jtalk_dic_utf_8-1.11.tar.gz"
#define DICTIONARY_DIR "open_jtalk_dic_utf_8-1.11"
#define DICTIONARY_SHA256 "fe6ba0e43542cef98339abdffd903e062008ea170b04e7e2a35da805902f382a"

// HTS voice download URL (Using direct link from SourceForge)
#define HTS_VOICE_URL "https://sourceforge.net/projects/open-jtalk/files/HTS%20voice/hts_voice_nitech_jp_atr503_m001-1.05/hts_voice_nitech_jp_atr503_m001-1.05.tar.gz/download"
#define HTS_VOICE_FILENAME "hts_voice_nitech_jp_atr503_m001-1.05.tar.gz"
#define HTS_VOICE_DIR "hts_voice_nitech_jp_atr503_m001-1.05"
#define HTS_VOICE_FILE "nitech_jp_atr503_m001.htsvoice"
#define HTS_VOICE_SHA256 "2e555c88482267b2931c7dbc7ecc0e3df140d6f68fc913aa4822f336c9e0adfc"

// Helper function to verify SHA256 checksum
static int verify_checksum(const char* file_path, const char* expected_sha256) {
    char cmd[2048];
    char result[256] = {0};
    FILE* fp;
    
    fprintf(stderr, "Verifying checksum...\n");
    
#ifdef _WIN32
    // Use PowerShell on Windows
    snprintf(cmd, sizeof(cmd),
             "powershell -Command \"(Get-FileHash -Path '%s' -Algorithm SHA256).Hash\"",
             file_path);
#else
    // Try sha256sum first, then shasum -a 256
    if (system("which sha256sum > /dev/null 2>&1") == 0) {
        snprintf(cmd, sizeof(cmd), "sha256sum \"%s\" | cut -d' ' -f1", file_path);
    } else if (system("which shasum > /dev/null 2>&1") == 0) {
        snprintf(cmd, sizeof(cmd), "shasum -a 256 \"%s\" | cut -d' ' -f1", file_path);
    } else {
        fprintf(stderr, "Warning: No checksum tool available, skipping verification\n");
        return 0; // Skip verification if no tool available
    }
#endif
    
#ifdef _WIN32
    fp = _popen(cmd, "r");
#else
    fp = popen(cmd, "r");
#endif
    if (fp == NULL) {
        fprintf(stderr, "Warning: Failed to compute checksum, skipping verification\n");
        return 0;
    }
    
    if (fgets(result, sizeof(result), fp) != NULL) {
        // Remove newline
        size_t len = strlen(result);
        if (len > 0 && result[len-1] == '\n') {
            result[len-1] = '\0';
        }
        
        // Convert to lowercase for comparison
        for (int i = 0; result[i]; i++) {
            result[i] = tolower(result[i]);
        }
        
        // Compare with expected checksum (also in lowercase)
        char expected_lower[256];
        strncpy(expected_lower, expected_sha256, sizeof(expected_lower) - 1);
        for (int i = 0; expected_lower[i]; i++) {
            expected_lower[i] = tolower(expected_lower[i]);
        }
        
        if (strcmp(result, expected_lower) == 0) {
            fprintf(stderr, "Checksum verified successfully\n");
#ifdef _WIN32
            _pclose(fp);
#else
            pclose(fp);
#endif
            return 0;
        } else {
            fprintf(stderr, "Error: Checksum mismatch! Expected %s, got %s\n", expected_sha256, result);
#ifdef _WIN32
            _pclose(fp);
#else
            pclose(fp);
#endif
            return -1;
        }
    }
    
#ifdef _WIN32
    _pclose(fp);
#else
    pclose(fp);
#endif
    fprintf(stderr, "Warning: Failed to read checksum output, skipping verification\n");
    return 0;
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
    
    // Check common system locations
    const char* system_paths[] = {
#ifdef _WIN32
        "C:\\Program Files\\open_jtalk\\dic",
        "C:\\Program Files (x86)\\open_jtalk\\dic",
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

// Download and extract the dictionary
static int download_and_extract_dictionary() {
    const char* data_dir = get_data_dir();
    char archive_path[1024];
    char extract_cmd[2048];
    char download_cmd[2048];
    
    snprintf(archive_path, sizeof(archive_path), "%s/%s", data_dir, DICTIONARY_FILENAME);
    
    // Download the dictionary archive
    fprintf(stderr, "Downloading OpenJTalk dictionary from %s...\n", DICTIONARY_URL);
    
#ifdef _WIN32
    // Use PowerShell on Windows
    snprintf(download_cmd, sizeof(download_cmd),
             "powershell -Command \"Invoke-WebRequest -Uri '%s' -OutFile '%s'\"",
             DICTIONARY_URL, archive_path);
#else
    // Use curl or wget on Unix-like systems
    if (system("which curl > /dev/null 2>&1") == 0) {
        snprintf(download_cmd, sizeof(download_cmd),
                 "curl -L -o \"%s\" \"%s\"",
                 archive_path, DICTIONARY_URL);
    } else if (system("which wget > /dev/null 2>&1") == 0) {
        snprintf(download_cmd, sizeof(download_cmd),
                 "wget -O \"%s\" \"%s\"",
                 archive_path, DICTIONARY_URL);
    } else {
        fprintf(stderr, "Error: Neither curl nor wget is available for downloading\n");
        return -1;
    }
#endif
    
    if (system(download_cmd) != 0) {
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
    
#ifdef _WIN32
    // Use PowerShell to extract on Windows
    snprintf(extract_cmd, sizeof(extract_cmd),
             "powershell -Command \"cd '%s'; tar -xzf '%s'\"",
             data_dir, DICTIONARY_FILENAME);
#else
    // Use tar on Unix-like systems
    snprintf(extract_cmd, sizeof(extract_cmd),
             "cd \"%s\" && tar -xzf \"%s\"",
             data_dir, DICTIONARY_FILENAME);
#endif
    
    if (system(extract_cmd) != 0) {
        fprintf(stderr, "Error: Failed to extract dictionary\n");
        unlink(archive_path);
        return -1;
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
    
    // Check if auto-download is disabled
    const char* auto_download = getenv("PIPER_AUTO_DOWNLOAD_DICT");
    if (auto_download && strcmp(auto_download, "0") == 0) {
        fprintf(stderr, "Failed to ensure OpenJTalk dictionary: Auto-download is disabled. Please download and install the dictionary manually.\n");
        return -1;
    }
    
    // Download and extract dictionary
    return download_and_extract_dictionary();
}

// Get the path to the HTS voice file
const char* get_openjtalk_voice_path() {
    // HTS voice not needed for phonemizer-only mode
    // This function is kept for backward compatibility but returns NULL
    return NULL;
}

#if 0
// Original HTS voice download code - kept for reference but disabled
static const char* get_openjtalk_voice_path_old() {
    static char voice_path[1024] = {0};
    
    if (voice_path[0] != '\0') {
        return voice_path;
    }
    
    // Check environment variable first
    const char* env_voice = getenv("OPENJTALK_VOICE");
    if (env_voice && access(env_voice, F_OK) == 0) {
        strncpy(voice_path, env_voice, sizeof(voice_path) - 1);
        return voice_path;
    }
    
    // Get default location in the same directory as dictionary
    const char* data_dir = get_data_dir();
    char voice_dir[1024];
    snprintf(voice_dir, sizeof(voice_dir), "%s/%s", data_dir, HTS_VOICE_DIR);
    snprintf(voice_path, sizeof(voice_path), "%s/%s", voice_dir, HTS_VOICE_FILE);
    
    // Download if not exists
    if (access(voice_path, F_OK) != 0) {
        // Check if we're in offline mode
        const char* offline_mode = getenv("PIPER_OFFLINE_MODE");
        if (offline_mode && strcmp(offline_mode, "1") == 0) {
            voice_path[0] = '\0'; // Reset path
            return NULL;
        }
        
        // Check if auto-download is disabled
        const char* auto_download = getenv("PIPER_AUTO_DOWNLOAD_DICT");
        if (auto_download && strcmp(auto_download, "0") == 0) {
            voice_path[0] = '\0'; // Reset path
            return NULL;
        }
        
        // Create directory
        mkdir_p(voice_dir);
        
        // Download HTS voice tar.gz file
        char archive_path[1024];
        snprintf(archive_path, sizeof(archive_path), "%s/%s", data_dir, HTS_VOICE_FILENAME);
        
        fprintf(stderr, "Downloading HTS voice from %s...\n", HTS_VOICE_URL);
        
        char download_cmd[1024];
#ifdef _WIN32
        // Use curl if available on Windows (Git Bash), otherwise use PowerShell
        if (system("where curl >NUL 2>&1") == 0) {
            snprintf(download_cmd, sizeof(download_cmd),
                     "curl -L -o \"%s\" \"%s\"",
                     archive_path, HTS_VOICE_URL);
        } else {
            snprintf(download_cmd, sizeof(download_cmd),
                     "powershell -Command \"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
                     "$ProgressPreference = 'SilentlyContinue'; "
                     "Invoke-WebRequest -Uri '%s' -OutFile '%s' -MaximumRedirection 5\"",
                     HTS_VOICE_URL, archive_path);
        }
#else
        if (system("which curl > /dev/null 2>&1") == 0) {
            snprintf(download_cmd, sizeof(download_cmd),
                     "curl -L -o \"%s\" \"%s\"",
                     archive_path, HTS_VOICE_URL);
        } else if (system("which wget > /dev/null 2>&1") == 0) {
            snprintf(download_cmd, sizeof(download_cmd),
                     "wget -O \"%s\" \"%s\"",
                     archive_path, HTS_VOICE_URL);
        } else {
            fprintf(stderr, "Error: Neither curl nor wget is available for downloading\n");
            voice_path[0] = '\0'; // Reset path
            return NULL;
        }
#endif
        
        if (system(download_cmd) != 0) {
            fprintf(stderr, "Error: Failed to download HTS voice file\n");
            voice_path[0] = '\0'; // Reset path
            return NULL;
        }
        
        // Verify checksum
        if (verify_checksum(archive_path, HTS_VOICE_SHA256) != 0) {
            fprintf(stderr, "Error: HTS voice download corrupted\n");
            unlink(archive_path);
            voice_path[0] = '\0'; // Reset path
            return NULL;
        }
        
        // Extract the archive
        fprintf(stderr, "Extracting HTS voice...\n");
        char extract_cmd[1024];
        
#ifdef _WIN32
        // Try native tar if available (Windows 10+), otherwise use PowerShell
        if (system("where tar >NUL 2>&1") == 0) {
            snprintf(extract_cmd, sizeof(extract_cmd),
                     "cd /d \"%s\" && tar -xzf \"%s\"",
                     data_dir, HTS_VOICE_FILENAME);
        } else {
            // Fallback to PowerShell for older Windows
            snprintf(extract_cmd, sizeof(extract_cmd),
                     "powershell -Command \"cd '%s'; "
                     "Add-Type -AssemblyName System.IO.Compression.FileSystem; "
                     "$archive = '%s'; "
                     "$tarFile = $archive -replace '\\.gz$', ''; "
                     "$gzStream = [System.IO.File]::OpenRead($archive); "
                     "$decompress = New-Object System.IO.Compression.GzipStream($gzStream, [System.IO.Compression.CompressionMode]::Decompress); "
                     "$output = [System.IO.File]::Create($tarFile); "
                     "$decompress.CopyTo($output); "
                     "$output.Close(); $decompress.Close(); $gzStream.Close(); "
                     "tar -xf $tarFile; "
                     "Remove-Item $tarFile -Force\"",
                     data_dir, archive_path);
        }
#else
        snprintf(extract_cmd, sizeof(extract_cmd),
                 "cd \"%s\" && tar -xzf \"%s\"",
                 data_dir, HTS_VOICE_FILENAME);
#endif
        
        if (system(extract_cmd) != 0) {
            fprintf(stderr, "Error: Failed to extract HTS voice archive\n");
            unlink(archive_path);
            voice_path[0] = '\0'; // Reset path
            return NULL;
        }
        
        // Clean up archive
        unlink(archive_path);
        
        fprintf(stderr, "HTS voice file installed successfully\n");
    }
    
    return voice_path;
}
#endif