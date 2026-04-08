# cmake/ios.toolchain.cmake
# iOS cross-compilation toolchain for arm64 (iPhone/iPad)
#
# Usage:
#   cmake -B build-ios \
#     -DCMAKE_TOOLCHAIN_FILE=cmake/ios.toolchain.cmake \
#     -DCMAKE_OSX_ARCHITECTURES=arm64 \
#     ...

set(CMAKE_SYSTEM_NAME iOS)
set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING "iOS architecture")
set(CMAKE_OSX_DEPLOYMENT_TARGET "15.0" CACHE STRING "Minimum iOS deployment target")

# Static library only (dylib not allowed on iOS App Store)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Force static library on iOS")

# Bitcode disabled (deprecated since Xcode 14)
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fembed-bitcode=off" CACHE STRING "" FORCE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fembed-bitcode=off" CACHE STRING "" FORCE)

# Disable code signing for CI builds
set(CMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO" CACHE STRING "")

# Force HTS Engine stub (autotools not feasible for iOS cross-compilation)
set(USE_HTS_ENGINE_STUB ON CACHE BOOL "Force HTS Engine stub on iOS" FORCE)

# Skip standalone executables on iOS (only static library is built)
set(IOS TRUE CACHE BOOL "Building for iOS" FORCE)
