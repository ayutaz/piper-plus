# Download ONNX Runtime DLLs for Windows
# This script ensures that onnxruntime.dll is available for Windows builds

if(NOT DEFINED ONNXRUNTIME_VERSION)
  set(ONNXRUNTIME_VERSION "1.14.1")
endif()

if(NOT DEFINED ONNXRUNTIME_DIR)
  set(ONNXRUNTIME_DIR "${CMAKE_CURRENT_BINARY_DIR}/onnxruntime")
endif()

# Determine architecture
if(CMAKE_SIZEOF_VOID_P EQUAL 8)
  set(ONNXRUNTIME_ARCH "x64")
else()
  set(ONNXRUNTIME_ARCH "x86")
endif()

# Download URL for Windows ONNX Runtime
set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-win-${ONNXRUNTIME_ARCH}-${ONNXRUNTIME_VERSION}.zip")

# Download and extract ONNX Runtime
if(NOT EXISTS "${ONNXRUNTIME_DIR}/lib/onnxruntime.dll")
  message(STATUS "Downloading ONNX Runtime ${ONNXRUNTIME_VERSION} for Windows ${ONNXRUNTIME_ARCH}...")
  
  # Create directory
  file(MAKE_DIRECTORY "${ONNXRUNTIME_DIR}")
  
  # Download
  set(ONNXRUNTIME_ARCHIVE "${CMAKE_CURRENT_BINARY_DIR}/onnxruntime.zip")
  file(DOWNLOAD
    "${ONNXRUNTIME_URL}"
    "${ONNXRUNTIME_ARCHIVE}"
    SHOW_PROGRESS
    STATUS download_status
    TIMEOUT 300
  )
  
  list(GET download_status 0 status_code)
  list(GET download_status 1 error_message)
  
  if(NOT status_code EQUAL 0)
    message(FATAL_ERROR "Failed to download ONNX Runtime: ${error_message}")
  endif()
  
  # Extract
  message(STATUS "Extracting ONNX Runtime...")
  execute_process(
    COMMAND ${CMAKE_COMMAND} -E tar xf "${ONNXRUNTIME_ARCHIVE}"
    WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
    RESULT_VARIABLE extract_result
  )
  
  if(NOT extract_result EQUAL 0)
    message(FATAL_ERROR "Failed to extract ONNX Runtime")
  endif()
  
  # Move to final location
  file(RENAME
    "${CMAKE_CURRENT_BINARY_DIR}/onnxruntime-win-${ONNXRUNTIME_ARCH}-${ONNXRUNTIME_VERSION}"
    "${ONNXRUNTIME_DIR}"
  )
  
  # Verify DLL exists
  if(NOT EXISTS "${ONNXRUNTIME_DIR}/lib/onnxruntime.dll")
    message(FATAL_ERROR "ONNX Runtime DLL not found after extraction")
  endif()
  
  message(STATUS "ONNX Runtime ${ONNXRUNTIME_VERSION} downloaded successfully")
else()
  message(STATUS "Using existing ONNX Runtime at ${ONNXRUNTIME_DIR}")
endif()

# Export paths
set(ONNXRUNTIME_ROOT_DIR "${ONNXRUNTIME_DIR}" CACHE PATH "ONNX Runtime root directory")
set(ONNXRUNTIME_INCLUDE_DIR "${ONNXRUNTIME_DIR}/include" CACHE PATH "ONNX Runtime include directory")
set(ONNXRUNTIME_LIB_DIR "${ONNXRUNTIME_DIR}/lib" CACHE PATH "ONNX Runtime library directory")
set(ONNXRUNTIME_DLL "${ONNXRUNTIME_DIR}/lib/onnxruntime.dll" CACHE FILEPATH "ONNX Runtime DLL")