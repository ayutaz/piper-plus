# cmake/PiperLink.cmake
# Linking, include directories, and compile definitions for piper / test_piper
# executables. Must be included AFTER ExternalDeps.cmake and OnnxRuntime.cmake
# so that FMT_DIR, SPDLOG_DIR, OPENJTALK_DIR, HTS_STUB_DIR, ONNXRUNTIME_DIR
# etc. are already set.

# ---- Platform-specific extra libraries and static linking ----

if(APPLE)
  # macOS-specific settings
  set(PIPER_EXTRA_LIBRARIES "pthread")
elseif(ANDROID)
  # Android: no static linking, pthread not needed (bionic provides it)
  set(PIPER_EXTRA_LIBRARIES "")
elseif(NOT MSVC)
  # Linux flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
  if(TARGET piper)
    target_link_libraries(piper PRIVATE -static-libgcc -static-libstdc++)
  endif()

  set(PIPER_EXTRA_LIBRARIES "pthread")
endif()

# ---- Platform-specific library linking (piper executable only) ----
if(TARGET piper)
  if(WIN32)
    # Windows: Link libraries directly with generator expressions for debug/release
    target_link_libraries(piper PRIVATE
      optimized ${FMT_DIR}/lib/fmt.lib
      debug ${FMT_DIR}/lib/fmtd.lib
      optimized ${SPDLOG_DIR}/lib/spdlog.lib
      debug ${SPDLOG_DIR}/lib/spdlogd.lib
      ${ONNXRUNTIME_LIB}
      ${PIPER_EXTRA_LIBRARIES}
    )
  else()
    # Unix: Use standard library names
    target_link_libraries(piper PRIVATE
      fmt
      spdlog
      onnxruntime
      ${PIPER_EXTRA_LIBRARIES}
    )
  endif()
endif()

# ---- Link OpenJTalk libraries ----
# Ensure OpenJTalk is built before linking
add_dependencies(piper_common openjtalk_external)
if(TARGET piper)
  add_dependencies(piper openjtalk_external)
  add_dependencies(test_piper openjtalk_external)
endif()

# hts_engine_stub: OpenJTalk ヘッダーが HTS_engine.h を transitively include するため、
# 型定義互換シムとしてリンクが必要。HTS 合成機能は一切使用しない。
if(TARGET piper)
  target_link_libraries(piper PRIVATE hts_engine_stub)
  target_link_libraries(test_piper PRIVATE hts_engine_stub)
endif()

# ---- piper / test_piper link directories and include directories ----
if(TARGET piper)
  target_link_directories(piper PUBLIC
    ${FMT_DIR}/lib
    ${SPDLOG_DIR}/lib
  )

  target_include_directories(piper PUBLIC
    ${FMT_DIR}/include
    ${SPDLOG_DIR}/include
  )

  # Add ONNX Runtime include directory for Windows
  if(WIN32 AND ONNXRUNTIME_INCLUDE_DIR)
    target_include_directories(piper PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
    target_include_directories(test_piper PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
  endif()
endif()

# Add ONNX Runtime install path for Linux/macOS
if(NOT WIN32 AND DEFINED ONNXRUNTIME_DIR)
  # Also install ONNX Runtime shared libs
  install(
    DIRECTORY ${ONNXRUNTIME_DIR}/lib/
    DESTINATION lib
    FILES_MATCHING PATTERN "libonnxruntime*"
  )
endif()

if(TARGET piper)
  # Include OpenJTalk headers (r9y9 fork installs to include/openjtalk/)
  target_include_directories(piper PUBLIC
    ${OPENJTALK_DIR}/include
    ${OPENJTALK_DIR}/include/openjtalk
  )
  target_include_directories(test_piper PUBLIC
    ${OPENJTALK_DIR}/include
    ${OPENJTALK_DIR}/include/openjtalk
  )

  # Include HTSEngine headers (required for OpenJTalk)
  target_include_directories(piper PUBLIC
    ${HTS_STUB_DIR}/include
  )
  target_include_directories(test_piper PUBLIC
    ${HTS_STUB_DIR}/include
  )

  # Link OpenJTalk static library (r9y9 fork: single "openjtalk" lib with MeCab included)
  if(WIN32)
    target_link_libraries(piper PRIVATE ${OPENJTALK_DIR}/lib/openjtalk.lib)
    target_link_libraries(test_piper PRIVATE ${OPENJTALK_DIR}/lib/openjtalk.lib)
  else()
    target_link_libraries(piper PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)
    target_link_libraries(test_piper PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)
  endif()

  target_compile_definitions(piper PUBLIC _PIPER_VERSION=${piper_version})
  target_compile_definitions(piper PUBLIC SPDLOG_FMT_EXTERNAL=1)
  target_compile_definitions(piper PUBLIC FMT_HEADER_ONLY=1)

  # Add OpenJTalk dictionary path definition
  if(WIN32)
    target_compile_definitions(piper PUBLIC OPENJTALK_DIC_PATH="..\\\\share\\\\open_jtalk\\\\dic")
    target_compile_definitions(test_piper PUBLIC OPENJTALK_DIC_PATH="${CMAKE_CURRENT_BINARY_DIR}\\\\naist-jdic")
    target_compile_definitions(test_piper PUBLIC SPDLOG_FMT_EXTERNAL=1)
    target_compile_definitions(test_piper PUBLIC FMT_HEADER_ONLY=1)
  else()
    target_compile_definitions(piper PUBLIC OPENJTALK_DIC_PATH="../share/open_jtalk/dic")
    target_compile_definitions(test_piper PUBLIC OPENJTALK_DIC_PATH="${CMAKE_CURRENT_BINARY_DIR}/naist-jdic")
    target_compile_definitions(test_piper PUBLIC SPDLOG_FMT_EXTERNAL=1)
    target_compile_definitions(test_piper PUBLIC FMT_HEADER_ONLY=1)
  endif()
endif() # TARGET piper

# ---- Declare test ----
if(TARGET test_piper)
  include(CTest)
  enable_testing()
  add_test(
    NAME test_piper
    COMMAND test_piper "${CMAKE_SOURCE_DIR}/test/models/multilingual-test-medium.onnx" "${CMAKE_CURRENT_BINARY_DIR}/test.wav"
  )
  set_tests_properties(test_piper PROPERTIES SKIP_RETURN_CODE 77)
endif()

if(TARGET test_piper)
  target_compile_features(test_piper PUBLIC cxx_std_17)

  target_include_directories(
    test_piper PUBLIC
    ${FMT_DIR}/include
    ${SPDLOG_DIR}/include
  )

  target_link_directories(
    test_piper PUBLIC
    ${FMT_DIR}/lib
    ${SPDLOG_DIR}/lib
  )

  # Platform-specific library linking for test_piper
  if(WIN32)
    # Windows: Link libraries directly with generator expressions for debug/release
    target_link_libraries(test_piper PRIVATE
      optimized ${FMT_DIR}/lib/fmt.lib
      debug ${FMT_DIR}/lib/fmtd.lib
      optimized ${SPDLOG_DIR}/lib/spdlog.lib
      debug ${SPDLOG_DIR}/lib/spdlogd.lib
      ${ONNXRUNTIME_LIB}
      ${PIPER_EXTRA_LIBRARIES}
    )
  else()
    target_link_libraries(test_piper PRIVATE
      fmt
      spdlog
      onnxruntime
      ${PIPER_EXTRA_LIBRARIES}
    )
  endif()
endif()

# OpenJTalk is linked as a static library (r9y9 fork) for direct API access
