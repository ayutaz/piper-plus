# Download ONNX Runtime for Windows
# This is necessary because piper-phonemize may not include the Windows DLLs

if(MSVC)
  set(ONNXRUNTIME_VERSION "1.15.1")
  
  # Determine architecture
  if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    set(ONNX_ARCH "x64")
  else()
    set(ONNX_ARCH "x86")
  endif()
  
  set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-win-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}.zip")
  set(ONNXRUNTIME_DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/onnxruntime-download")
  set(ONNXRUNTIME_ZIP "${ONNXRUNTIME_DOWNLOAD_DIR}/onnxruntime.zip")
  
  # Create download directory
  file(MAKE_DIRECTORY ${ONNXRUNTIME_DOWNLOAD_DIR})
  
  # Download ONNX Runtime if not already present
  if(NOT EXISTS "${ONNXRUNTIME_ZIP}")
    message(STATUS "Downloading ONNX Runtime ${ONNXRUNTIME_VERSION} for Windows ${ONNX_ARCH}...")
    file(DOWNLOAD
      ${ONNXRUNTIME_URL}
      ${ONNXRUNTIME_ZIP}
      SHOW_PROGRESS
      STATUS download_status
    )
    
    list(GET download_status 0 status_code)
    if(NOT status_code EQUAL 0)
      message(FATAL_ERROR "Failed to download ONNX Runtime")
    endif()
  endif()
  
  # Extract ONNX Runtime
  set(ONNXRUNTIME_EXTRACT_DIR "${ONNXRUNTIME_DOWNLOAD_DIR}/extracted")
  if(NOT EXISTS "${ONNXRUNTIME_EXTRACT_DIR}")
    message(STATUS "Extracting ONNX Runtime...")
    file(MAKE_DIRECTORY ${ONNXRUNTIME_EXTRACT_DIR})
    # Use execute_process for compatibility with older CMake versions
    execute_process(
      COMMAND ${CMAKE_COMMAND} -E tar xf ${ONNXRUNTIME_ZIP}
      WORKING_DIRECTORY ${ONNXRUNTIME_EXTRACT_DIR}
      RESULT_VARIABLE extract_result
    )
    if(NOT extract_result EQUAL 0)
      message(FATAL_ERROR "Failed to extract ONNX Runtime")
    endif()
  endif()
  
  # Find the extracted directory (it has version in the name)
  file(GLOB ONNXRUNTIME_DIR "${ONNXRUNTIME_EXTRACT_DIR}/onnxruntime-*")
  if(NOT ONNXRUNTIME_DIR)
    message(FATAL_ERROR "Failed to find extracted ONNX Runtime directory")
  endif()
  
  # Get the first directory (there should only be one)
  list(GET ONNXRUNTIME_DIR 0 ONNXRUNTIME_DIR)
  
  # Set paths
  set(ONNXRUNTIME_LIB_DIR "${ONNXRUNTIME_DIR}/lib")
  set(ONNXRUNTIME_DLL "${ONNXRUNTIME_LIB_DIR}/onnxruntime.dll")
  
  if(NOT EXISTS "${ONNXRUNTIME_DLL}")
    message(FATAL_ERROR "ONNX Runtime DLL not found at: ${ONNXRUNTIME_DLL}")
  endif()
  
  message(STATUS "Found ONNX Runtime DLL: ${ONNXRUNTIME_DLL}")
  
  # Export variables for use in main CMakeLists.txt
  set(ONNXRUNTIME_DLL "${ONNXRUNTIME_DLL}" PARENT_SCOPE)
  set(ONNXRUNTIME_LIB_DIR "${ONNXRUNTIME_LIB_DIR}" PARENT_SCOPE)
endif()