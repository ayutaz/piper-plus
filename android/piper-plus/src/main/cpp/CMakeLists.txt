cmake_minimum_required(VERSION 3.22.1)
project(piper_plus_jni LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# -- piper_plus shared library (pre-built) -----------------------------------
# The pre-built libpiper_plus.so is placed under jniLibs/<abi>/ by the NDK
# build that runs before this CMakeLists (M4-4). We declare it as IMPORTED
# so the JNI wrapper can link against it.
add_library(piper_plus SHARED IMPORTED)
set_target_properties(piper_plus PROPERTIES
    IMPORTED_LOCATION
        "${CMAKE_SOURCE_DIR}/../jniLibs/${ANDROID_ABI}/libpiper_plus.so"
)
# Make the C header visible to the JNI wrapper.
target_include_directories(piper_plus INTERFACE
    "${CMAKE_SOURCE_DIR}/../../../../../../src/cpp"
)

# -- JNI wrapper -------------------------------------------------------------
add_library(piper_plus_jni SHARED piper_plus_jni.cpp)

target_link_libraries(piper_plus_jni
    PRIVATE
        piper_plus
        android
        log
)
