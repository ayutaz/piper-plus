cmake_minimum_required(VERSION 3.22.1)
project(piper_plus_g2p_jni LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 16 KB page size compatibility (Android 15+, NFR-COMPAT-4 / R-4)
add_link_options("-Wl,-z,max-page-size=16384")

# -- piper_plus shared library (pre-built, IMPORTED) -------------------------
# The pre-built libpiper_plus.so is placed under jniLibs/<abi>/ by the
# release-shared-lib CI job (or the local build-android-jnilibs.sh script).
add_library(piper_plus SHARED IMPORTED)
set_target_properties(piper_plus PROPERTIES
    IMPORTED_LOCATION
        "${CMAKE_SOURCE_DIR}/../jniLibs/${ANDROID_ABI}/libpiper_plus.so"
)

# Make piper_plus.h visible. Path traversal from CMAKE_SOURCE_DIR
# (= android/piper-plus-g2p/src/main/cpp):
#   ..      → src/main/
#   ../..   → src/
#   ../../../  → piper-plus-g2p/
#   ../../../../  → android/
#   ../../../../../  → repository root
target_include_directories(piper_plus INTERFACE
    "${CMAKE_SOURCE_DIR}/../../../../../src/cpp"
)

# -- JNI wrapper -------------------------------------------------------------
add_library(piper_plus_g2p_jni SHARED piper_plus_g2p_jni.cpp)

# android + log are NDK-specific. Link them only when configuring under the
# AGP toolchain (ANDROID is set automatically by android.toolchain.cmake).
if(ANDROID)
    target_link_libraries(piper_plus_g2p_jni
        PRIVATE piper_plus android log)
else()
    target_link_libraries(piper_plus_g2p_jni
        PRIVATE piper_plus)
endif()
