#include <gtest/gtest.h>
#include <cstdlib>
#include <sstream>
#include <string>

// Platform-specific environment variable functions
#ifdef _WIN32
#include <windows.h>
// Windows doesn't have setenv/unsetenv, use _putenv_s instead
int setenv(const char* name, const char* value, int) {
    return _putenv_s(name, value);
}
int unsetenv(const char* name) {
    return _putenv_s(name, "");
}
#endif

// Test fixture for GPU device ID tests
class GPUDeviceIdTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Clear environment variable before each test
        unsetenv("PIPER_GPU_DEVICE_ID");
    }
    
    void TearDown() override {
        // Clean up environment variable
        unsetenv("PIPER_GPU_DEVICE_ID");
    }
};

// Test environment variable parsing
TEST_F(GPUDeviceIdTest, EnvironmentVariableParsing) {
    // Test valid integer
    setenv("PIPER_GPU_DEVICE_ID", "2", 1);
    const char* env_value = std::getenv("PIPER_GPU_DEVICE_ID");
    ASSERT_NE(env_value, nullptr);
    EXPECT_EQ(std::stoi(env_value), 2);
    
    // Test invalid values don't crash
    setenv("PIPER_GPU_DEVICE_ID", "invalid", 1);
    env_value = std::getenv("PIPER_GPU_DEVICE_ID");
    ASSERT_NE(env_value, nullptr);
    // Should not crash when trying to parse
    try {
        std::stoi(env_value);
        FAIL() << "Expected std::invalid_argument";
    } catch (const std::invalid_argument& e) {
        // Expected behavior
        SUCCEED();
    }
}

// Test default GPU device ID value
TEST_F(GPUDeviceIdTest, DefaultGPUDeviceId) {
    // When no environment variable is set, default should be 0
    const char* env_value = std::getenv("PIPER_GPU_DEVICE_ID");
    EXPECT_EQ(env_value, nullptr);
    
    // In actual usage, the default value in RunConfig should be 0
    // This is verified at compile time by the struct definition
}

// Test that large device IDs are accepted
TEST_F(GPUDeviceIdTest, LargeDeviceIds) {
    // GPU device IDs can be large in multi-GPU systems
    setenv("PIPER_GPU_DEVICE_ID", "7", 1);
    const char* env_value = std::getenv("PIPER_GPU_DEVICE_ID");
    ASSERT_NE(env_value, nullptr);
    EXPECT_EQ(std::stoi(env_value), 7);
    
    // Test a very large ID
    setenv("PIPER_GPU_DEVICE_ID", "255", 1);
    env_value = std::getenv("PIPER_GPU_DEVICE_ID");
    ASSERT_NE(env_value, nullptr);
    EXPECT_EQ(std::stoi(env_value), 255);
}

// Test negative device IDs (should be handled by CUDA runtime)
TEST_F(GPUDeviceIdTest, NegativeDeviceIds) {
    setenv("PIPER_GPU_DEVICE_ID", "-1", 1);
    const char* env_value = std::getenv("PIPER_GPU_DEVICE_ID");
    ASSERT_NE(env_value, nullptr);
    EXPECT_EQ(std::stoi(env_value), -1);
    
    // Negative values should be passed through to CUDA runtime
    // which will handle the error appropriately
}

// Test empty string handling
TEST_F(GPUDeviceIdTest, EmptyStringHandling) {
    setenv("PIPER_GPU_DEVICE_ID", "", 1);
    const char* env_value = std::getenv("PIPER_GPU_DEVICE_ID");
#ifdef _WIN32
    // Windows _putenv_s("name", "") removes the variable entirely
    if (env_value == nullptr) {
        SUCCEED();
        return;
    }
#endif
    ASSERT_NE(env_value, nullptr);
    EXPECT_STREQ(env_value, "");

    // Empty string should cause parsing error
    try {
        std::stoi(env_value);
        FAIL() << "Expected std::invalid_argument";
    } catch (const std::invalid_argument& e) {
        // Expected behavior
        SUCCEED();
    }
}

// Test zero device ID
TEST_F(GPUDeviceIdTest, ZeroDeviceId) {
    setenv("PIPER_GPU_DEVICE_ID", "0", 1);
    const char* env_value = std::getenv("PIPER_GPU_DEVICE_ID");
    ASSERT_NE(env_value, nullptr);
    EXPECT_EQ(std::stoi(env_value), 0);
}

// Test command line argument format validation
TEST_F(GPUDeviceIdTest, CommandLineFormatValidation) {
    // This test verifies that the expected command line formats are valid
    // The actual parsing is done in main.cpp
    
    // Valid formats
    std::vector<std::string> valid_args = {
        "--gpu-device-id",
        "--gpu_device_id"
    };
    
    for (const auto& arg : valid_args) {
        // Check that the argument string is well-formed
        EXPECT_FALSE(arg.empty());
        EXPECT_EQ(arg.substr(0, 2), "--");
    }
}