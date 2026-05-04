# cmake/CompilerSettings.cmake
# C/C++ standard, warning flags, -fPIC, -static-libstdc++, Android/ARM64 settings

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Set C standard for better compatibility
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(MSVC)
  # Force compiler to use UTF-8 for IPA constants
  add_compile_options("$<$<C_COMPILER_ID:MSVC>:/utf-8>")
  add_compile_options("$<$<CXX_COMPILER_ID:MSVC>:/utf-8>")

  # Additional Windows-specific flags
  add_compile_options(/EHsc)  # Enable C++ exceptions
  add_compile_options(/W3)    # Warning level 3

  # Define Windows version macros
  add_compile_definitions(WIN32_LEAN_AND_MEAN)
  add_compile_definitions(_WIN32_WINNT=0x0601)  # Windows 7 and later
elseif(APPLE)
  # macOS flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
else()
  # Linux flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
  # Set RPATH for installed binaries
  set(CMAKE_INSTALL_RPATH "$ORIGIN" "$ORIGIN/../lib")
  set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)
  set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)
endif()

# ---- Android cross-compilation support ----
if(ANDROID)
  message(STATUS "Android cross-compilation: ABI=${ANDROID_ABI}, Platform=${ANDROID_PLATFORM}")
  # Propagate NDK toolchain to ExternalProject_Add calls
  set(ANDROID_CMAKE_ARGS
    -DCMAKE_TOOLCHAIN_FILE=${CMAKE_TOOLCHAIN_FILE}
    -DANDROID_ABI=${ANDROID_ABI}
    -DANDROID_PLATFORM=${ANDROID_PLATFORM}
    -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}
    -DCMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER}
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
  )
endif()

# ---- iOS cross-compilation support ----
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
  message(STATUS "iOS cross-compilation: sysroot=${CMAKE_OSX_SYSROOT}, arch=${CMAKE_OSX_ARCHITECTURES}, target=${CMAKE_OSX_DEPLOYMENT_TARGET}")
  # Propagate iOS settings to ExternalProject_Add calls.
  #
  # CMAKE_OSX_SYSROOT is critical (issue #377): without it, ExternalProjects
  # default to the iphoneos (device) SDK regardless of the parent's slice
  # selection. When the simulator slice's main project (built with
  # iphonesimulator) merges in the ExternalProject's static archive (built
  # with iphoneos), `xcodebuild -create-xcframework` rejects the result with
  # "binaries with multiple platforms are not supported".
  #
  # CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY prevents try_compile from
  # attempting to link an executable (which fails on iOS cross-compile because
  # device-arch crt1.o cannot link against host crt1.o), and avoids silent
  # feature-detection regressions inside the ExternalProject's CMake config.
  set(EXTERNAL_CMAKE_ARGS
    -DCMAKE_SYSTEM_NAME=iOS
    -DCMAKE_OSX_SYSROOT=${CMAKE_OSX_SYSROOT}
    -DCMAKE_OSX_ARCHITECTURES=${CMAKE_OSX_ARCHITECTURES}
    -DCMAKE_OSX_DEPLOYMENT_TARGET=${CMAKE_OSX_DEPLOYMENT_TARGET}
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY
  )
endif()

# ARM64-specific optimizations (skip on Android/Apple-embedded -- their
# toolchains set their own flags). PIPER_APPLE_EMBEDDED is defined in the
# root CMakeLists.txt before this file is included.
if(NOT ANDROID AND NOT PIPER_APPLE_EMBEDDED AND CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
  message(STATUS "Detected ARM64 architecture, enabling optimizations")

  # Enable NEON SIMD instructions
  if(NOT MSVC)
    # Use compatible ARM64 flags for QEMU
    # Avoid advanced instructions that might not be properly emulated
    set(ARM64_FLAGS "-march=armv8-a -mtune=generic")
    string(APPEND CMAKE_CXX_FLAGS " ${ARM64_FLAGS}")
    string(APPEND CMAKE_C_FLAGS " ${ARM64_FLAGS}")

    # Conservative optimization for QEMU compatibility
    set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG")
    set(CMAKE_C_FLAGS_RELEASE "-O2 -DNDEBUG")

    # Enable Link Time Optimization for release builds
    if(CMAKE_BUILD_TYPE STREQUAL "Release")
      include(CheckIPOSupported)
      check_ipo_supported(RESULT ipo_supported OUTPUT error)
      if(ipo_supported)
        set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
        message(STATUS "Link Time Optimization enabled for ARM64")
      endif()
    endif()

    # Strip symbols for smaller binaries
    set(CMAKE_EXE_LINKER_FLAGS_RELEASE "-s")
  endif()

  # Temporarily disable NEON for debugging
  # add_compile_definitions(USE_ARM64_NEON)
endif()
