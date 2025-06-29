# Download pre-built piper-phonemize for CI builds
if(MSVC AND DEFINED ENV{GITHUB_ACTIONS})
  message(STATUS "GitHub Actions Windows build detected - downloading pre-built piper-phonemize")
  
  set(PIPER_PHONEMIZE_VERSION "2023.11.14-3")
  set(PIPER_PHONEMIZE_URL "https://github.com/rhasspy/piper-phonemize/releases/download/${PIPER_PHONEMIZE_VERSION}/piper-phonemize-windows-amd64.zip")
  set(PIPER_PHONEMIZE_ZIP "${CMAKE_CURRENT_BINARY_DIR}/piper-phonemize.zip")
  
  # Download pre-built binaries
  if(NOT EXISTS "${PIPER_PHONEMIZE_ZIP}")
    message(STATUS "Downloading piper-phonemize from: ${PIPER_PHONEMIZE_URL}")
    file(DOWNLOAD
      ${PIPER_PHONEMIZE_URL}
      ${PIPER_PHONEMIZE_ZIP}
      SHOW_PROGRESS
      STATUS download_status
    )
    
    list(GET download_status 0 status_code)
    if(NOT status_code EQUAL 0)
      message(FATAL_ERROR "Failed to download piper-phonemize")
    endif()
  endif()
  
  # Extract
  message(STATUS "Extracting piper-phonemize...")
  execute_process(
    COMMAND ${CMAKE_COMMAND} -E tar xf "${PIPER_PHONEMIZE_ZIP}"
    WORKING_DIRECTORY "${PIPER_PHONEMIZE_DIR}"
    RESULT_VARIABLE extract_result
  )
  
  if(NOT extract_result EQUAL 0)
    message(FATAL_ERROR "Failed to extract piper-phonemize")
  endif()
  
  # Create dummy target
  add_custom_target(piper_phonemize_external
    COMMAND ${CMAKE_COMMAND} -E echo "Using pre-built piper-phonemize"
  )
endif()