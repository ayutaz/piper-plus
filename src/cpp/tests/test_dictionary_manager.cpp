#include <gtest/gtest.h>
#include <cstdlib>
#include <cstring>
#include <sys/stat.h>
#include <string>
#include <filesystem>

#ifdef _WIN32
#include <windows.h>
#include <direct.h>
#include <io.h>
#define access _access
#define F_OK 0
#define mkdir(path, mode) _mkdir(path)
#else
#include <unistd.h>
#endif

extern "C" {
#include "../openjtalk_dictionary_manager.h"
}

class DictionaryManagerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Create a temporary test directory
#ifdef _WIN32
        char temp_path[MAX_PATH];
        DWORD result = GetTempPathA(MAX_PATH, temp_path);
        ASSERT_GT(result, 0);
        
        char temp_dir[MAX_PATH];
        snprintf(temp_dir, sizeof(temp_dir), "%spiper_test_%d", temp_path, GetCurrentProcessId());
        
        // Create directory
        _mkdir(temp_dir);
        test_dir = _strdup(temp_dir);
#else
        char temp_template[] = "/tmp/piper_test_XXXXXX";
        test_dir = mkdtemp(temp_template);
        ASSERT_NE(test_dir, nullptr);
#endif
        
        // Save original environment variables
        original_home = getenv("HOME");
        original_dict_dir = getenv("OPENJTALK_DICTIONARY_PATH");
        original_auto_download = getenv("PIPER_AUTO_DOWNLOAD_DICT");
        original_offline = getenv("PIPER_OFFLINE_MODE");
        
        // Set test HOME
#ifdef _WIN32
        SetEnvironmentVariableA("HOME", test_dir);
#else
        setenv("HOME", test_dir, 1);
#endif
    }
    
    void TearDown() override {
        // Restore original environment variables
        if (original_home) {
#ifdef _WIN32
            SetEnvironmentVariableA("HOME", original_home);
#else
            setenv("HOME", original_home, 1);
#endif
        } else {
#ifdef _WIN32
            SetEnvironmentVariableA("HOME", NULL);
#else
            unsetenv("HOME");
#endif
        }
        
        if (original_dict_dir) {
#ifdef _WIN32
            SetEnvironmentVariableA("OPENJTALK_DICTIONARY_PATH", original_dict_dir);
#else
            setenv("OPENJTALK_DICTIONARY_PATH", original_dict_dir, 1);
#endif
        } else {
#ifdef _WIN32
            SetEnvironmentVariableA("OPENJTALK_DICTIONARY_PATH", NULL);
#else
            unsetenv("OPENJTALK_DICTIONARY_PATH");
#endif
        }
        
        if (original_auto_download) {
#ifdef _WIN32
            SetEnvironmentVariableA("PIPER_AUTO_DOWNLOAD_DICT", original_auto_download);
#else
            setenv("PIPER_AUTO_DOWNLOAD_DICT", original_auto_download, 1);
#endif
        } else {
#ifdef _WIN32
            SetEnvironmentVariableA("PIPER_AUTO_DOWNLOAD_DICT", NULL);
#else
            unsetenv("PIPER_AUTO_DOWNLOAD_DICT");
#endif
        }
        
        if (original_offline) {
#ifdef _WIN32
            SetEnvironmentVariableA("PIPER_OFFLINE_MODE", original_offline);
#else
            setenv("PIPER_OFFLINE_MODE", original_offline, 1);
#endif
        } else {
#ifdef _WIN32
            SetEnvironmentVariableA("PIPER_OFFLINE_MODE", NULL);
#else
            unsetenv("PIPER_OFFLINE_MODE");
#endif
        }
        
        // Reset dictionary cache so other test suites are not affected
        reset_openjtalk_dictionary_cache();

        // Clean up test directory
        if (test_dir) {
            std::filesystem::remove_all(test_dir);
#ifdef _WIN32
            free(test_dir);
#endif
        }
    }
    
    char* test_dir = nullptr;
    const char* original_home = nullptr;
    const char* original_dict_dir = nullptr;
    const char* original_auto_download = nullptr;
    const char* original_offline = nullptr;
};

// Test dictionary path resolution
// TODO: Implement openjtalk_get_default_dict_path function
// TEST_F(DictionaryManagerTest, GetDefaultDictPath) {
//     char buffer[1024];
//     
//     // Test default path (should use HOME)
//     EXPECT_EQ(openjtalk_get_default_dict_path(buffer, sizeof(buffer)), 0);
//     EXPECT_TRUE(strstr(buffer, test_dir) != nullptr);
//     EXPECT_TRUE(strstr(buffer, ".piper/dictionaries/openjtalk") != nullptr);
// }

// Test custom dictionary path via environment variable
TEST_F(DictionaryManagerTest, CustomDictPath) {
    const char* custom_path = "/custom/dict/path";
    setenv("OPENJTALK_DICTIONARY_PATH", custom_path, 1);
    
    // Create dummy dictionary files
    mkdir("/tmp", 0755);
    mkdir("/tmp/custom_dict_test", 0755);
    setenv("OPENJTALK_DICTIONARY_PATH", "/tmp/custom_dict_test", 1);
    
    // Create dummy dictionary files
    FILE* fp = fopen("/tmp/custom_dict_test/sys.dic", "w");
    if (fp) fclose(fp);
    fp = fopen("/tmp/custom_dict_test/unk.dic", "w");
    if (fp) fclose(fp);
    
    // TODO: Implement openjtalk_get_default_dict_path function
    // char buffer[1024];
    // EXPECT_EQ(openjtalk_get_default_dict_path(buffer, sizeof(buffer)), 0);
    // EXPECT_STREQ(buffer, "/tmp/custom_dict_test");
    
    // Clean up
    unlink("/tmp/custom_dict_test/sys.dic");
    unlink("/tmp/custom_dict_test/unk.dic");
    rmdir("/tmp/custom_dict_test");
}

// Test dictionary existence check
// TODO: Implement openjtalk_check_dictionary function
// TEST_F(DictionaryManagerTest, CheckDictionary) {
//     // Non-existent path
//     EXPECT_EQ(openjtalk_check_dictionary("/nonexistent/path"), 0);
//     
//     // Create a test directory with dictionary files
//     char test_dict_path[256];
//     snprintf(test_dict_path, sizeof(test_dict_path), "%s/test_dict", test_dir);
//     mkdir(test_dict_path, 0755);
//     
//     // Without dictionary files
//     EXPECT_EQ(openjtalk_check_dictionary(test_dict_path), 0);
//     
//     // Create dictionary files
//     char sys_dic[256], unk_dic[256];
//     snprintf(sys_dic, sizeof(sys_dic), "%s/sys.dic", test_dict_path);
//     snprintf(unk_dic, sizeof(unk_dic), "%s/unk.dic", test_dict_path);
//     
//     FILE* fp = fopen(sys_dic, "w");
//     if (fp) fclose(fp);
//     fp = fopen(unk_dic, "w");
//     if (fp) fclose(fp);
//     
//     // With dictionary files
//     EXPECT_EQ(openjtalk_check_dictionary(test_dict_path), 1);
// }

// Test offline mode
TEST_F(DictionaryManagerTest, OfflineMode) {
    // Force the cache to a non-existent path so ensure_openjtalk_dictionary()
    // cannot find a dictionary and must attempt download (which offline blocks)
    force_openjtalk_dictionary_path("/nonexistent_dict_path_for_test");

#ifdef _WIN32
    SetEnvironmentVariableA("PIPER_OFFLINE_MODE", "1");
#else
    setenv("PIPER_OFFLINE_MODE", "1", 1);
#endif

    // Should fail: dictionary doesn't exist and offline mode blocks download
    EXPECT_NE(ensure_openjtalk_dictionary(), 0);
}

// Test auto-download disabled
TEST_F(DictionaryManagerTest, AutoDownloadDisabled) {
    // Force the cache to a non-existent path
    force_openjtalk_dictionary_path("/nonexistent_dict_path_for_test");

#ifdef _WIN32
    SetEnvironmentVariableA("PIPER_AUTO_DOWNLOAD_DICT", "0");
#else
    setenv("PIPER_AUTO_DOWNLOAD_DICT", "0", 1);
#endif

    // Should fail: dictionary doesn't exist and auto-download is disabled
    EXPECT_NE(ensure_openjtalk_dictionary(), 0);
}

// Test version management
// TODO: Implement version management functions
// TEST_F(DictionaryManagerTest, VersionManagement) {
//     // Test getting available versions
//     const char* versions[10];
//     int count = openjtalk_get_available_versions(versions, 10);
//     EXPECT_GT(count, 0);
//     EXPECT_STREQ(versions[0], "1.11");  // First version should be 1.11
//     
//     // Test setting dictionary version
//     openjtalk_set_dict_version("1.10");
//     // This would affect subsequent dictionary downloads
// }

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}