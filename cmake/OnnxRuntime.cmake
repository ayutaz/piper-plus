# cmake/OnnxRuntime.cmake
# ONNX Runtime download + platform-specific configuration

# ---- ONNX Runtime ---
if(WIN32)
  include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/find_onnxruntime_windows.cmake)
elseif(NOT DEFINED ONNXRUNTIME_DIR)
  # Linux/macOS: Download pre-built ONNX Runtime if not already available
  #
  # Source of truth for the C++ pipeline ORT version. The CI gate
  # `scripts/check_ort_versions.py` (workflow: ort-version-sync.yml) cross-
  # checks every cmake / GitHub Actions reference against this value.
  #
  # Issue #383 follow-up: bumped 1.17.0 → 1.20.0 alongside the parallelism
  # work. The proximate trigger was a Windows model-load SEH (`The given
  # version [14] is not supported, only version 1 to 10`); investigation in
  # `tools/benchmark/issue-383/cpp_ort_upgrade.md` showed the real root
  # cause was the loader picking up an older `onnxruntime.dll` from
  # System32, not 1.17.0 itself. Fixed by staging the bundled DLL next to
  # test executables (commit 734aa5c6) and by upgrading the pipeline ORT
  # to 1.20.0 across cmake + the iOS/Android release workflows
  # (`release-shared-lib.yml`, `android-build.yml`, `release-kotlin-g2p.yml`,
  # `build-piper.yml`, `_build-test-cpp.yml`) so all artefacts ship the
  # same runtime version. Updating this constant is the canonical change;
  # the CI gate fails if any of the above drift away from it.
  set(ONNXRUNTIME_VERSION "1.20.0")
  if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
    if(APPLE)
      set(ONNXRUNTIME_ARCH "arm64")
    else()
      set(ONNXRUNTIME_ARCH "aarch64")
    endif()
  else()
    set(ONNXRUNTIME_ARCH "x64")
  endif()
  if(APPLE)
    set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-osx-${ONNXRUNTIME_ARCH}-${ONNXRUNTIME_VERSION}.tgz")
  else()
    set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-linux-${ONNXRUNTIME_ARCH}-${ONNXRUNTIME_VERSION}.tgz")
  endif()
  set(ONNXRUNTIME_DIR "${CMAKE_CURRENT_BINARY_DIR}/ort")

  include(ExternalProject)
  ExternalProject_Add(
    onnxruntime_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/ort_dl"
    URL "${ONNXRUNTIME_URL}"
    CONFIGURE_COMMAND ""
    BUILD_COMMAND ""
    INSTALL_COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/lib ${ONNXRUNTIME_DIR}/lib
    COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/include ${ONNXRUNTIME_DIR}/include
  )
  add_dependencies(piper_common onnxruntime_external)
  if(TARGET piper)
    add_dependencies(piper onnxruntime_external)
    add_dependencies(test_piper onnxruntime_external)
  endif()

  target_include_directories(piper_common PUBLIC ${ONNXRUNTIME_DIR}/include)
  if(TARGET piper)
    target_include_directories(piper PUBLIC ${ONNXRUNTIME_DIR}/include)
    target_include_directories(test_piper PUBLIC ${ONNXRUNTIME_DIR}/include)
    target_link_directories(piper PUBLIC ${ONNXRUNTIME_DIR}/lib)
    target_link_directories(test_piper PUBLIC ${ONNXRUNTIME_DIR}/lib)
  endif()
else()
  # ONNXRUNTIME_DIR was pre-defined externally (e.g. Android cross-compilation)
  if(DEFINED ONNXRUNTIME_DIR)
    if(DEFINED ONNXRUNTIME_INCLUDE_DIR)
      target_include_directories(piper_common PUBLIC ${ONNXRUNTIME_INCLUDE_DIR})
    else()
      target_include_directories(piper_common PUBLIC ${ONNXRUNTIME_DIR}/include)
    endif()
    target_link_directories(piper_common PUBLIC ${ONNXRUNTIME_DIR}/lib)
  endif()
endif()
