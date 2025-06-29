# Download pre-built piper-phonemize for Windows
# This avoids complex Windows build issues

include(FetchContent)

set(PIPER_PHONEMIZE_VERSION "2023.11.14-3")
set(PIPER_PHONEMIZE_URL "https://github.com/rhasspy/piper-phonemize/releases/download/${PIPER_PHONEMIZE_VERSION}/piper-phonemize-windows-amd64.tar.gz")

message(STATUS "Downloading pre-built piper-phonemize for Windows...")

FetchContent_Declare(
  piper_phonemize_windows
  URL ${PIPER_PHONEMIZE_URL}
  URL_HASH SHA256=<hash_here>  # Add actual hash for security
)

FetchContent_GetProperties(piper_phonemize_windows)
if(NOT piper_phonemize_windows_POPULATED)
  FetchContent_Populate(piper_phonemize_windows)
  
  # Extract to the expected directory
  set(PIPER_PHONEMIZE_DIR ${CMAKE_CURRENT_BINARY_DIR}/pi)
  file(MAKE_DIRECTORY ${PIPER_PHONEMIZE_DIR})
  
  # Copy all files from download to install directory
  file(GLOB_RECURSE PHONEMIZE_FILES "${piper_phonemize_windows_SOURCE_DIR}/*")
  foreach(file ${PHONEMIZE_FILES})
    file(RELATIVE_PATH rel_path ${piper_phonemize_windows_SOURCE_DIR} ${file})
    get_filename_component(dir ${rel_path} DIRECTORY)
    file(MAKE_DIRECTORY ${PIPER_PHONEMIZE_DIR}/${dir})
    configure_file(${file} ${PIPER_PHONEMIZE_DIR}/${rel_path} COPYONLY)
  endforeach()
endif()

# Set up library and include paths
set(PIPER_PHONEMIZE_LIBRARIES
  ${PIPER_PHONEMIZE_DIR}/lib/piper_phonemize.lib
  ${PIPER_PHONEMIZE_DIR}/lib/espeak-ng.lib
  ${PIPER_PHONEMIZE_DIR}/lib/onnxruntime.lib
)

set(PIPER_PHONEMIZE_INCLUDE_DIRS
  ${PIPER_PHONEMIZE_DIR}/include
)

# Copy DLLs to build directory
file(GLOB PIPER_PHONEMIZE_DLLS "${PIPER_PHONEMIZE_DIR}/lib/*.dll")
foreach(dll ${PIPER_PHONEMIZE_DLLS})
  configure_file(${dll} ${CMAKE_CURRENT_BINARY_DIR} COPYONLY)
endforeach()