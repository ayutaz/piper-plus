# cmake/PiperPlusShared.cmake
# piper_plus SHARED library (C API) + RPATH + install

option(PIPER_PLUS_BUILD_SHARED "Build piper-plus shared library (C API)" OFF)

if(PIPER_PLUS_BUILD_SHARED)

# iOS: build as static library (dylib not allowed on App Store)
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
  add_library(piper_plus STATIC
    src/cpp/piper_plus_c_api.cpp
    $<TARGET_OBJECTS:piper_common>
  )
else()
  add_library(piper_plus SHARED
    src/cpp/piper_plus_c_api.cpp
    $<TARGET_OBJECTS:piper_common>
  )
endif()

# Dependencies (same as piper/test_piper)
add_dependencies(piper_plus fmt_external spdlog_external openjtalk_external hts_engine_stub)
if(TARGET onnxruntime_external)
  add_dependencies(piper_plus onnxruntime_external)
endif()

# Include directories (same as piper_common)
# PRIVATE for build-tree paths; consumers use the installed header via INSTALL_INTERFACE.
target_include_directories(piper_plus
  PRIVATE
    ${FMT_DIR}/include
    ${SPDLOG_DIR}/include
    ${OPENJTALK_DIR}/include
    ${OPENJTALK_DIR}/include/openjtalk
    ${HTS_STUB_DIR}/include
  PUBLIC
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)
if(DEFINED ONNXRUNTIME_INCLUDE_DIR)
  target_include_directories(piper_plus PRIVATE ${ONNXRUNTIME_INCLUDE_DIR})
elseif(NOT WIN32 AND DEFINED ONNXRUNTIME_DIR)
  target_include_directories(piper_plus PRIVATE ${ONNXRUNTIME_DIR}/include)
endif()

# Compile definitions (same as piper_common, but NO OPENJTALK_DIC_PATH -- C API uses dict_dir)
target_compile_definitions(piper_plus PRIVATE
  PIPER_PLUS_BUILDING_DLL
  _PIPER_VERSION=${piper_version}
  SPDLOG_FMT_EXTERNAL=1
  FMT_HEADER_ONLY=1
)

# Link directories (PRIVATE -- all deps are linked into the shared lib)
target_link_directories(piper_plus PRIVATE
  ${FMT_DIR}/lib
  ${SPDLOG_DIR}/lib
)
if(NOT WIN32 AND DEFINED ONNXRUNTIME_DIR)
  target_link_directories(piper_plus PRIVATE ${ONNXRUNTIME_DIR}/lib)
endif()

# Link libraries -- NOTE: -static-libstdc++ is intentionally NOT applied (M1-2)
if(WIN32)
  target_link_libraries(piper_plus PRIVATE
    optimized ${FMT_DIR}/lib/fmt.lib
    debug ${FMT_DIR}/lib/fmtd.lib
    optimized ${SPDLOG_DIR}/lib/spdlog.lib
    debug ${SPDLOG_DIR}/lib/spdlogd.lib
    ${ONNXRUNTIME_LIB}
    ${OPENJTALK_DIR}/lib/openjtalk.lib
  )
elseif(CMAKE_SYSTEM_NAME STREQUAL "iOS" AND DEFINED ONNXRUNTIME_LIB)
  # iOS: link ONNX Runtime by explicit path (from xcframework extraction)
  target_link_libraries(piper_plus PRIVATE
    fmt
    spdlog
    ${ONNXRUNTIME_LIB}
  )
  # Link OpenJTalk static library
  target_link_libraries(piper_plus PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)

  # Generate module.modulemap for xcframework Swift import support
  # (M2 §11.7 繰り上げ採用 — issue #377)
  # The map file is placed in CMAKE_BINARY_DIR and the assemble-xcframework CI
  # job copies it into each slice's Headers/ directory inside the xcframework,
  # enabling `import PiperPlus` from Swift via SPM binaryTarget consumption.
  file(WRITE "${CMAKE_BINARY_DIR}/module.modulemap"
"module PiperPlus {
  umbrella header \"piper_plus.h\"
  export *
  module * { export * }
}
")
elseif(ANDROID AND DEFINED ONNXRUNTIME_LIB)
  # Android: link ONNX Runtime by explicit path (from AAR extraction)
  target_link_libraries(piper_plus PRIVATE
    fmt
    spdlog
    ${ONNXRUNTIME_LIB}
  )
  # Link OpenJTalk static library
  target_link_libraries(piper_plus PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)
else()
  target_link_libraries(piper_plus PRIVATE
    fmt
    spdlog
    onnxruntime
    ${PIPER_EXTRA_LIBRARIES}
  )
  # Link OpenJTalk static library
  target_link_libraries(piper_plus PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)
endif()

# Link HTS Engine stub (required for OpenJTalk header compatibility)
target_link_libraries(piper_plus PRIVATE hts_engine_stub)

# Link pthread and libdl on Linux/Android
if(ANDROID)
  target_link_libraries(piper_plus PRIVATE log dl)
elseif(UNIX AND NOT APPLE)
  find_package(Threads REQUIRED)
  target_link_libraries(piper_plus PRIVATE Threads::Threads dl)
endif()

# Visibility and output settings
set_target_properties(piper_plus PROPERTIES
  C_VISIBILITY_PRESET hidden
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON
  OUTPUT_NAME "piper_plus"
)

# iOS static library: no VERSION/SOVERSION/RPATH needed
if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
  set_target_properties(piper_plus PROPERTIES
    VERSION ${piper_version}
    SOVERSION 1
  )

  # RPATH settings
  if(APPLE)
    set_target_properties(piper_plus PROPERTIES
      MACOSX_RPATH TRUE
      INSTALL_RPATH "@loader_path"
    )
  elseif(UNIX)
    set_target_properties(piper_plus PROPERTIES
      INSTALL_RPATH "$ORIGIN"
      BUILD_WITH_INSTALL_RPATH TRUE
    )
  endif()
endif()

# Install targets
include(GNUInstallDirs)
install(TARGETS piper_plus
  EXPORT PiperPlusTargets
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(FILES src/cpp/piper_plus.h
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)

# --- ONNX Runtime shared library install ---
# Skip for iOS/Android (ONNX Runtime is linked statically or bundled separately)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS" AND NOT ANDROID)
  if(WIN32)
    # Windows: copy DLLs to bin/
    file(GLOB _ort_dlls "${ONNXRUNTIME_DIR}/lib/*.dll")
    install(FILES ${_ort_dlls} DESTINATION ${CMAKE_INSTALL_BINDIR})
  else()
    # Unix: copy shared libs to lib/ (exclude .dSYM directories on macOS)
    file(GLOB _ort_libs "${ONNXRUNTIME_DIR}/lib/libonnxruntime*${CMAKE_SHARED_LIBRARY_SUFFIX}*")
    list(FILTER _ort_libs EXCLUDE REGEX "\\.dSYM$")
    install(FILES ${_ort_libs} DESTINATION ${CMAKE_INSTALL_LIBDIR})
  endif()
endif()

# --- ONNX Runtime license ---
set(_ort_license "${ONNXRUNTIME_DIR}/../ort_dl/src/onnxruntime_external/LICENSE")
if(NOT EXISTS "${_ort_license}")
  # Fallback: try common locations
  set(_ort_license "${ONNXRUNTIME_DIR}/LICENSE")
endif()
if(EXISTS "${_ort_license}")
  install(FILES "${_ort_license}"
          DESTINATION ${CMAKE_INSTALL_DATADIR}/licenses/onnxruntime
          RENAME LICENSE)
endif()

# --- Dictionary install (optional) ---
# OpenJTalk dictionary
if(EXISTS "${CMAKE_BINARY_DIR}/oj/dic")
  install(DIRECTORY "${CMAKE_BINARY_DIR}/oj/dic/"
          DESTINATION share/open_jtalk/dic)
endif()

# --- G2P dictionaries (English CMU, Chinese Pinyin) ---
set(_g2p_dict_files
  ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/cmudict_data.json
  ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_single.json
  ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_phrases.json
)
foreach(_dict ${_g2p_dict_files})
  if(EXISTS "${_dict}")
    install(FILES "${_dict}" DESTINATION ${CMAKE_INSTALL_DATADIR}/piper/dicts)
  endif()
endforeach()

# --- macOS: fix ONNX Runtime install_name ---
if(APPLE)
  install(CODE "
    file(GLOB _ort_dylibs \"\${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}/libonnxruntime*.dylib\")
    foreach(_dylib IN LISTS _ort_dylibs)
      get_filename_component(_name \${_dylib} NAME)
      execute_process(
        COMMAND install_name_tool -id \"@rpath/\${_name}\" \"\${_dylib}\"
      )
    endforeach()
  ")
endif()

# --- pkg-config ---
configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/cmake/piper_plus.pc.in
  ${CMAKE_CURRENT_BINARY_DIR}/piper_plus.pc
  @ONLY
)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/piper_plus.pc
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)

# --- CMake Config package ---
include(CMakePackageConfigHelpers)

install(EXPORT PiperPlusTargets
  FILE PiperPlusTargets.cmake
  NAMESPACE PiperPlus::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/PiperPlus
)

configure_package_config_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/cmake/PiperPlusConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/PiperPlusConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/PiperPlus
)

write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/PiperPlusConfigVersion.cmake
  VERSION ${piper_version}
  COMPATIBILITY SameMajorVersion
)

install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/PiperPlusConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/PiperPlusConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/PiperPlus
)

endif() # PIPER_PLUS_BUILD_SHARED
