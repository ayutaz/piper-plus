# cmake/ExternalDeps.cmake
# ExternalProject definitions: fmt, spdlog, hts_engine, OpenJTalk

# NOTE: external project prefix are shortened because of path length restrictions on Windows

# ---- fmt ---

if(NOT DEFINED FMT_DIR)
  set(FMT_VERSION "10.0.0")
  set(FMT_DIR "${CMAKE_CURRENT_BINARY_DIR}/fi")

  include(ExternalProject)
  # Pass architecture settings to external projects
  if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    # iOS: EXTERNAL_CMAKE_ARGS already set by CompilerSettings.cmake
    # (no-op here, avoid overriding with macOS settings)
  elseif(APPLE)
    # macOS: Apple Silicon (arm64) only
    set(EXTERNAL_CMAKE_ARGS -DCMAKE_OSX_ARCHITECTURES=arm64)
  else()
    set(EXTERNAL_CMAKE_ARGS "")
  endif()

  # Propagate Android NDK toolchain to all external projects
  if(ANDROID)
    list(APPEND EXTERNAL_CMAKE_ARGS ${ANDROID_CMAKE_ARGS})
  endif()

  # Ensure MSVC runtime library is propagated to all external projects
  if(MSVC)
    list(APPEND EXTERNAL_CMAKE_ARGS
      -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
      -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
      -DCMAKE_CXX_FLAGS_RELEASE=/MD
      -DCMAKE_CXX_FLAGS_DEBUG=/MDd
      -DCMAKE_C_FLAGS_RELEASE=/MD
      -DCMAKE_C_FLAGS_DEBUG=/MDd
    )
  endif()

  ExternalProject_Add(
    fmt_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/f"
    URL "https://github.com/fmtlib/fmt/archive/refs/tags/${FMT_VERSION}.zip"
    DOWNLOAD_NO_PROGRESS TRUE
    TIMEOUT 600  # 10 minutes timeout
    TLS_VERIFY ON
    DOWNLOAD_TRIES 3  # Retry download 3 times
    CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${FMT_DIR}
               -DFMT_TEST:BOOL=OFF  # Don't build all the tests
               -DFMT_HEADER_ONLY:BOOL=ON  # Build as header-only library
               -DBUILD_SHARED_LIBS:BOOL=OFF  # Build static libraries
               -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
               ${EXTERNAL_CMAKE_ARGS}
  )
  add_dependencies(piper_common fmt_external)
  if(TARGET piper)
    add_dependencies(piper fmt_external)
    add_dependencies(test_piper fmt_external)
  endif()
endif()

# ---- spdlog ---

if(NOT DEFINED SPDLOG_DIR)
  set(SPDLOG_DIR "${CMAKE_CURRENT_BINARY_DIR}/si")
  set(SPDLOG_VERSION "1.12.0")
  ExternalProject_Add(
    spdlog_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/s"
    URL "https://github.com/gabime/spdlog/archive/refs/tags/v${SPDLOG_VERSION}.zip"
    DOWNLOAD_NO_PROGRESS TRUE
    TIMEOUT 600  # 10 minutes timeout
    TLS_VERIFY ON
    DOWNLOAD_TRIES 3  # Retry download 3 times
    CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${SPDLOG_DIR}
               -DSPDLOG_BUILD_SHARED:BOOL=OFF  # Build static libraries
               -DSPDLOG_FMT_EXTERNAL:BOOL=ON  # Use external fmt
               -Dfmt_DIR:PATH=${FMT_DIR}/lib/cmake/fmt
               -DFMT_HEADER_ONLY:BOOL=ON  # Use fmt as header-only
               -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
               ${EXTERNAL_CMAKE_ARGS}
  )
  add_dependencies(spdlog_external fmt_external)
  add_dependencies(piper_common spdlog_external)
  if(TARGET piper)
    add_dependencies(piper spdlog_external)
    add_dependencies(test_piper spdlog_external)
  endif()
endif()

# ---- HTSEngine ---

# HTS Engine stub for OpenJTalk header compatibility.
# piper-plus uses ONNX neural synthesis, not HTS Engine.

# Use stub instead of real HTS Engine
set(HTS_STUB_DIR "${CMAKE_CURRENT_BINARY_DIR}/hts_stub")
file(MAKE_DIRECTORY ${HTS_STUB_DIR}/include)
file(MAKE_DIRECTORY ${HTS_STUB_DIR}/lib)

# Copy stub files
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/cmake/hts_engine_stub.h
               ${HTS_STUB_DIR}/include/HTS_engine.h COPYONLY)

# Build stub library
add_library(hts_engine_stub STATIC ${CMAKE_CURRENT_SOURCE_DIR}/cmake/hts_engine_stub.c)
target_include_directories(hts_engine_stub PUBLIC ${HTS_STUB_DIR}/include)
set_target_properties(hts_engine_stub PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(WIN32)
  set_target_properties(hts_engine_stub PROPERTIES
    ARCHIVE_OUTPUT_DIRECTORY ${HTS_STUB_DIR}/lib
    OUTPUT_NAME HTSEngine
    PREFIX "")
else()
  set_target_properties(hts_engine_stub PROPERTIES
    ARCHIVE_OUTPUT_DIRECTORY ${HTS_STUB_DIR}/lib
    OUTPUT_NAME HTSEngine
    PREFIX "lib")
endif()

# Ensure the stub library is built and create a symlink/copy for compatibility
if(WIN32)
  add_custom_command(TARGET hts_engine_stub POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory ${HTS_STUB_DIR}/lib
    COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:hts_engine_stub> ${HTS_STUB_DIR}/lib/HTSEngine.lib
    COMMENT "Ensuring HTS Engine stub library is in expected location (Windows)"
  )
else()
  add_custom_command(TARGET hts_engine_stub POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory ${HTS_STUB_DIR}/lib
    COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:hts_engine_stub> ${HTS_STUB_DIR}/lib/libHTSEngine.a
    COMMENT "Ensuring HTS Engine stub library is in expected location (Unix)"
  )
endif()

# ---- OpenJTalk ---
# Using pyopenjtalk-plus's open_jtalk fork for Python/C++ consistency.
# This fork has improved NJD accent phrase rules (Rules 19-22) and accent type fixes
# that produce identical fullcontext labels to the Python training pipeline.
# Both the library and dictionary come from the same pyopenjtalk-plus source.
set(PYOPENJTALK_PLUS_URL "https://files.pythonhosted.org/packages/82/4e/1e2c165b04dd250dbcb1c270df8517681eed5c20b755c72bec2b42853851/pyopenjtalk_plus-0.4.1.post7.tar.gz")

if(NOT DEFINED OPENJTALK_DIR)
    set(OPENJTALK_DIR "${CMAKE_CURRENT_BINARY_DIR}/oj")

    # pyopenjtalk-plus fork: single "openjtalk" library (MeCab + NJD + JPCommon)
    # No HTS_Engine dependency (NJD/MeCab pipeline only)
    set(OPENJTALK_CMAKE_ARGS
      -DCMAKE_INSTALL_PREFIX:PATH=${OPENJTALK_DIR}
      -DCMAKE_BUILD_TYPE:STRING=${CMAKE_BUILD_TYPE}
      -DBUILD_SHARED_LIBS:BOOL=OFF
      -DCHARSET:STRING=utf8
      -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
      ${EXTERNAL_CMAKE_ARGS}
    )

    if(WIN32)
      list(APPEND OPENJTALK_CMAKE_ARGS
        -DCMAKE_MSVC_RUNTIME_LIBRARY:STRING=${CMAKE_MSVC_RUNTIME_LIBRARY}
      )
    else()
      # Linux ARM64 cross-compilation settings (skip for Android -- NDK toolchain is in EXTERNAL_CMAKE_ARGS)
      if(NOT ANDROID AND CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
        list(APPEND OPENJTALK_CMAKE_ARGS
          -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
          -DCMAKE_C_COMPILER:FILEPATH=aarch64-linux-gnu-gcc
          -DCMAKE_CXX_COMPILER:FILEPATH=aarch64-linux-gnu-g++
          -DCMAKE_AR:FILEPATH=aarch64-linux-gnu-ar
          -DCMAKE_RANLIB:FILEPATH=aarch64-linux-gnu-ranlib
        )
      endif()
    endif()

    ExternalProject_Add(
      openjtalk_external
      PREFIX "${CMAKE_CURRENT_BINARY_DIR}/o"
      URL ${PYOPENJTALK_PLUS_URL}
      URL_HASH SHA256=555fdf86310d6d72f4a37e92beb251cdc2114aafc133d4c77b136a07a4b17119
      DOWNLOAD_NO_PROGRESS TRUE
      TIMEOUT 600
      TLS_VERIFY ON
      DOWNLOAD_TRIES 3
      SOURCE_SUBDIR lib/open_jtalk/src
      CMAKE_ARGS ${OPENJTALK_CMAKE_ARGS}
      PATCH_COMMAND
        ${CMAKE_COMMAND} -D SOURCE_DIR=<SOURCE_DIR> -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/patch_r9y9_openjtalk.cmake
      BUILD_BYPRODUCTS
        ${OPENJTALK_DIR}/lib/libopenjtalk.a      # Unix
        ${OPENJTALK_DIR}/lib/openjtalk.lib        # Windows
    )

    # Note: pyopenjtalk-plus fork doesn't require HTS_Engine for NJD pipeline

    # Dictionary from pyopenjtalk-plus (same source, same archive)
    # Custom dictionary with improved accent predictions from jpreprocess project.
    # DEPENDS openjtalk_external to avoid parallel download race condition.
    set(OPENJTALK_DIC_DIR "${CMAKE_CURRENT_BINARY_DIR}/share/open_jtalk/dic")
    ExternalProject_Add(
      openjtalk_dic_download
      PREFIX "${CMAKE_CURRENT_BINARY_DIR}/od"
      DEPENDS openjtalk_external
      URL ${PYOPENJTALK_PLUS_URL}
      URL_HASH SHA256=555fdf86310d6d72f4a37e92beb251cdc2114aafc133d4c77b136a07a4b17119
      DOWNLOAD_NO_PROGRESS TRUE
      TIMEOUT 600
      TLS_VERIFY ON
      DOWNLOAD_TRIES 3
      CONFIGURE_COMMAND ""
      BUILD_COMMAND ""
      INSTALL_COMMAND
        ${CMAKE_COMMAND} -E make_directory ${OPENJTALK_DIC_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/pyopenjtalk/dictionary ${OPENJTALK_DIC_DIR}
    )
endif()
