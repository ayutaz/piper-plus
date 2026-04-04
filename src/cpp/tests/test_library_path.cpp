/**
 * Test: library_path.c
 *
 * Unit tests for piper_plus_get_library_dir() and piper_plus_get_exe_dir().
 * Validates success paths, NULL/zero/negative buffer arguments, and tiny
 * buffer edge cases.
 */

#include <gtest/gtest.h>
#include <cstring>
#include <filesystem>

extern "C" {
#include "library_path.h"
}

// ============================================
// piper_plus_get_library_dir tests
// ============================================

TEST(LibraryPath, GetLibraryDirSucceeds) {
    char buf[4096];
    int rc = piper_plus_get_library_dir(buf, sizeof(buf));
    EXPECT_EQ(rc, 0) << "piper_plus_get_library_dir should return 0 on success";
    EXPECT_GT(std::strlen(buf), 0u) << "Returned path should not be empty";
    EXPECT_TRUE(std::filesystem::is_directory(buf))
        << "Returned path should be an existing directory: " << buf;
}

TEST(LibraryPath, GetLibraryDirNullBufReturnsError) {
    int rc = piper_plus_get_library_dir(NULL, 100);
    EXPECT_EQ(rc, -1);
}

TEST(LibraryPath, GetLibraryDirZeroSizeReturnsError) {
    char buf[64];
    int rc = piper_plus_get_library_dir(buf, 0);
    EXPECT_EQ(rc, -1);
}

TEST(LibraryPath, GetLibraryDirNegativeSizeReturnsError) {
    char buf[64];
    int rc = piper_plus_get_library_dir(buf, -1);
    EXPECT_EQ(rc, -1);
}

TEST(LibraryPath, GetLibraryDirTinyBufferReturnsError) {
    char buf[2];
    int rc = piper_plus_get_library_dir(buf, 2);
    EXPECT_EQ(rc, -1) << "A 2-byte buffer is too small for any real directory path";
}

// ============================================
// piper_plus_get_exe_dir tests
// ============================================

TEST(LibraryPath, GetExeDirSucceeds) {
    char buf[4096];
    int rc = piper_plus_get_exe_dir(buf, sizeof(buf));
    EXPECT_EQ(rc, 0) << "piper_plus_get_exe_dir should return 0 on success";
    EXPECT_GT(std::strlen(buf), 0u) << "Returned path should not be empty";
    EXPECT_TRUE(std::filesystem::is_directory(buf))
        << "Returned path should be an existing directory: " << buf;
}

TEST(LibraryPath, GetExeDirNullBufReturnsError) {
    int rc = piper_plus_get_exe_dir(NULL, 100);
    EXPECT_EQ(rc, -1);
}

TEST(LibraryPath, GetExeDirZeroSizeReturnsError) {
    char buf[64];
    int rc = piper_plus_get_exe_dir(buf, 0);
    EXPECT_EQ(rc, -1);
}

TEST(LibraryPath, GetExeDirTinyBufferReturnsError) {
    char buf[2];
    int rc = piper_plus_get_exe_dir(buf, 2);
    EXPECT_EQ(rc, -1) << "A 2-byte buffer is too small for any real directory path";
}
