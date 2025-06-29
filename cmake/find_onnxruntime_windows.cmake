# Find ONNX Runtime DLL for Windows
# First check if it's already available from piper-phonemize

if(MSVC)
  # Wait for piper_phonemize_external to complete if it's being built
  if(TARGET piper_phonemize_external)
    execute_process(
      COMMAND ${CMAKE_COMMAND} -E echo "Waiting for piper-phonemize build to complete before searching for ONNX Runtime..."
    )
  endif()
  
  # List of possible locations for onnxruntime.dll
  set(ONNXRUNTIME_SEARCH_PATHS
    "${PIPER_PHONEMIZE_DIR}/lib"
    "${PIPER_PHONEMIZE_DIR}/bin"
    "${CMAKE_CURRENT_BINARY_DIR}/pi/lib"
    "${CMAKE_CURRENT_BINARY_DIR}/pi/bin"
    "${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/onnxruntime-src/lib"
    "${CMAKE_CURRENT_BINARY_DIR}/p/src/piper_phonemize_external-build/_deps/onnxruntime-build/lib"
    "${CMAKE_CURRENT_BINARY_DIR}/_deps/onnxruntime-src/lib"
    "${CMAKE_CURRENT_BINARY_DIR}/_deps/onnxruntime-build/lib"
  )
  
  # Search for onnxruntime.dll
  set(ONNXRUNTIME_DLL "")
  foreach(search_path ${ONNXRUNTIME_SEARCH_PATHS})
    if(EXISTS "${search_path}/onnxruntime.dll")
      set(ONNXRUNTIME_DLL "${search_path}/onnxruntime.dll")
      message(STATUS "Found ONNX Runtime DLL: ${ONNXRUNTIME_DLL}")
      break()
    endif()
  endforeach()
  
  # If not found, download it
  if(NOT ONNXRUNTIME_DLL OR NOT EXISTS "${ONNXRUNTIME_DLL}")
    message(STATUS "ONNX Runtime DLL not found in piper-phonemize, downloading...")
    
    set(ONNXRUNTIME_VERSION "1.15.1")
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
    
    # Download
    if(NOT EXISTS "${ONNXRUNTIME_ZIP}")
      message(STATUS "Downloading ONNX Runtime from: ${ONNXRUNTIME_URL}")
      file(DOWNLOAD
        ${ONNXRUNTIME_URL}
        ${ONNXRUNTIME_ZIP}
        SHOW_PROGRESS
        STATUS download_status
      )
      
      list(GET download_status 0 status_code)
      if(NOT status_code EQUAL 0)
        message(WARNING "Failed to download ONNX Runtime, Windows build may fail")
        set(ONNXRUNTIME_DLL "")
      endif()
    endif()
    
    # Extract using PowerShell (more reliable on Windows)
    if(EXISTS "${ONNXRUNTIME_ZIP}")
      set(ONNXRUNTIME_EXTRACT_DIR "${ONNXRUNTIME_DOWNLOAD_DIR}/extracted")
      if(NOT EXISTS "${ONNXRUNTIME_EXTRACT_DIR}/onnxruntime-win-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}")
        message(STATUS "Extracting ONNX Runtime...")
        file(MAKE_DIRECTORY ${ONNXRUNTIME_EXTRACT_DIR})
        
        # Try PowerShell first
        execute_process(
          COMMAND powershell -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory('${ONNXRUNTIME_ZIP}', '${ONNXRUNTIME_EXTRACT_DIR}')"
          RESULT_VARIABLE ps_result
          OUTPUT_QUIET
          ERROR_QUIET
        )
        
        # If PowerShell fails, try CMake tar
        if(NOT ps_result EQUAL 0)
          file(MAKE_DIRECTORY ${ONNXRUNTIME_EXTRACT_DIR})
          execute_process(
            COMMAND ${CMAKE_COMMAND} -E tar xf "${ONNXRUNTIME_ZIP}"
            WORKING_DIRECTORY "${ONNXRUNTIME_EXTRACT_DIR}"
            RESULT_VARIABLE tar_result
          )
          
          if(NOT tar_result EQUAL 0)
            message(WARNING "Failed to extract ONNX Runtime")
            set(ONNXRUNTIME_DLL "")
          endif()
        endif()
      endif()
      
      # Find the DLL
      if(EXISTS "${ONNXRUNTIME_EXTRACT_DIR}/onnxruntime-win-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}/lib/onnxruntime.dll")
        set(ONNXRUNTIME_DLL "${ONNXRUNTIME_EXTRACT_DIR}/onnxruntime-win-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}/lib/onnxruntime.dll")
        set(ONNXRUNTIME_LIB_DIR "${ONNXRUNTIME_EXTRACT_DIR}/onnxruntime-win-${ONNX_ARCH}-${ONNXRUNTIME_VERSION}/lib")
        message(STATUS "Found downloaded ONNX Runtime DLL: ${ONNXRUNTIME_DLL}")
      endif()
    endif()
  endif()
  
  # Set the parent scope variables
  if(ONNXRUNTIME_DLL AND EXISTS "${ONNXRUNTIME_DLL}")
    set(ONNXRUNTIME_DLL "${ONNXRUNTIME_DLL}" PARENT_SCOPE)
    get_filename_component(ONNXRUNTIME_LIB_DIR "${ONNXRUNTIME_DLL}" DIRECTORY)
    set(ONNXRUNTIME_LIB_DIR "${ONNXRUNTIME_LIB_DIR}" PARENT_SCOPE)
  else()
    message(WARNING "ONNX Runtime DLL not found - Windows builds may fail to run")
    set(ONNXRUNTIME_DLL "" PARENT_SCOPE)
    set(ONNXRUNTIME_LIB_DIR "" PARENT_SCOPE)
  endif()
endif()