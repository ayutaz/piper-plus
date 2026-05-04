# cmake/PiperExecutable.cmake
# piper executable + test_piper target creation + RPATH
#
# NOTE: Linking, include directories, and compile definitions are configured
# AFTER ExternalDeps.cmake and OnnxRuntime.cmake are included. See the
# piper/test_piper configuration block in the root CMakeLists.txt.

# Skip standalone executables on Android / Apple-embedded (only library is built)
if(NOT ANDROID AND NOT PIPER_APPLE_EMBEDDED)
  add_executable(piper src/cpp/main.cpp)
  add_executable(test_piper src/cpp/test.cpp)
  # Link the piper_common STATIC library (was OBJECT before issue #377 fix).
  target_link_libraries(piper PRIVATE piper_common)
  target_link_libraries(test_piper PRIVATE piper_common)
endif()

# Link pthread and libdl on Linux (libdl needed for dladdr in library_path.c)
if(UNIX AND NOT APPLE)
  find_package(Threads REQUIRED)
  if(TARGET piper)
    target_link_libraries(piper PRIVATE Threads::Threads dl)
  endif()
  if(TARGET test_piper)
    target_link_libraries(test_piper PRIVATE Threads::Threads dl)
  endif()
endif()

# Configure RPATH for macOS
if(APPLE AND TARGET piper)
  set_target_properties(piper PROPERTIES
    MACOSX_RPATH TRUE
    INSTALL_RPATH "@executable_path;@executable_path/../lib;@loader_path/../lib"
    BUILD_RPATH "${CMAKE_CURRENT_BINARY_DIR}/ort/lib"
    BUILD_WITH_INSTALL_RPATH FALSE
  )
  set_target_properties(test_piper PROPERTIES
    MACOSX_RPATH TRUE
    INSTALL_RPATH "@executable_path;@executable_path/../lib;@loader_path/../lib"
    BUILD_RPATH "${CMAKE_CURRENT_BINARY_DIR}/ort/lib"
    BUILD_WITH_INSTALL_RPATH FALSE
  )
endif()
