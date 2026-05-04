# cmake/ios.toolchain.cmake
# iOS cross-compilation toolchain for arm64 (iPhone/iPad)
#
# Usage (device slice):
#   cmake -B build-ios \
#     -DCMAKE_TOOLCHAIN_FILE=cmake/ios.toolchain.cmake \
#     -DCMAKE_OSX_SYSROOT=iphoneos \
#     -DCMAKE_OSX_ARCHITECTURES=arm64 \
#     ...
#
# Usage (simulator slice, M2 — issue #377):
#   cmake -B build-ios-sim \
#     -DCMAKE_TOOLCHAIN_FILE=cmake/ios.toolchain.cmake \
#     -DCMAKE_OSX_SYSROOT=iphonesimulator \
#     -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" \
#     ...
#
# Both CMAKE_OSX_SYSROOT and CMAKE_OSX_ARCHITECTURES are CACHE variables
# without FORCE, so CLI -D overrides take precedence (no toolchain change
# required for simulator slice support).

set(CMAKE_SYSTEM_NAME iOS)
set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING
  "iOS architecture (override via -DCMAKE_OSX_ARCHITECTURES, e.g. \"arm64;x86_64\" for simulator)")
set(CMAKE_OSX_DEPLOYMENT_TARGET "15.0" CACHE STRING "Minimum iOS deployment target")

# Static library only (dylib not allowed on iOS App Store)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Force static library on iOS")

# Bitcode disabled (deprecated since Xcode 14)
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fembed-bitcode=off" CACHE STRING "" FORCE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fembed-bitcode=off" CACHE STRING "" FORCE)

# Disable code signing for CI builds
set(CMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO" CACHE STRING "")

# Skip standalone executables on iOS (only static library is built)
set(IOS TRUE CACHE BOOL "Building for iOS" FORCE)
