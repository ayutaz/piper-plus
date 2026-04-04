# cmake/Install.cmake
# Install rules for piper executable + dictionaries + Windows DLL handling

# ---- piper executable install ----
if(TARGET piper)
  install(
    TARGETS piper
    DESTINATION bin)
endif()

# Install OpenJTalk for Japanese TTS support
# r9y9 fork: static library linked directly, no separate binaries needed.
# OpenJTalk binaries (open_jtalk, open_jtalk_phonemizer) are no longer installed
# since C++ now uses the API directly instead of system() calls.
# Install OpenJTalk dictionary
install(
  DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/share/open_jtalk
  DESTINATION share
  OPTIONAL  # Don't fail if not present
)

# Install phonemizer dictionaries (English CMU, Chinese Pinyin)
install(
  FILES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/cmudict_data.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_single.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_phrases.json
  DESTINATION share/piper/dicts
)

# Install voices.json catalog for model listing/downloading
install(
  FILES ${CMAKE_CURRENT_SOURCE_DIR}/src/python_run/piper/voices.json
  DESTINATION share
  OPTIONAL
)


# ---- Windows-specific DLL handling ----
if(WIN32)
  # Helper function to copy DLLs
  function(copy_dlls_to_target target_name)
    # Create bin and lib subdirectories for better organization
    add_custom_command(TARGET ${target_name} POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:${target_name}>/lib"
      COMMENT "Creating lib directory for ${target_name}..."
    )

    # Copy ONNX Runtime DLLs
    if(ONNXRUNTIME_DLL)
      add_custom_command(TARGET ${target_name} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "${ONNXRUNTIME_DLL}"
          "$<TARGET_FILE_DIR:${target_name}>/onnxruntime.dll"
        COMMENT "Copying ONNX Runtime DLL..."
      )

      # Also copy ONNX Runtime providers DLL if it exists
      get_filename_component(ONNX_DIR "${ONNXRUNTIME_DLL}" DIRECTORY)
      file(GLOB ONNX_PROVIDER_DLLS "${ONNX_DIR}/onnxruntime_providers*.dll")
      foreach(dll ${ONNX_PROVIDER_DLLS})
        add_custom_command(TARGET ${target_name} POST_BUILD
          COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${dll}"
            "$<TARGET_FILE_DIR:${target_name}>/"
          COMMENT "Copying ONNX Runtime provider DLL: ${dll}..."
        )
      endforeach()
    endif()
  endfunction()

  # Apply DLL copying to targets
  copy_dlls_to_target(piper)
  copy_dlls_to_target(test_piper)
  if(PIPER_PLUS_BUILD_SHARED)
    copy_dlls_to_target(piper_plus)
  endif()

  # Install ONNX Runtime DLL
  if(ONNXRUNTIME_DLL)
    install(FILES ${ONNXRUNTIME_DLL} DESTINATION bin)
    get_filename_component(ONNX_DIR "${ONNXRUNTIME_DLL}" DIRECTORY)
    file(GLOB ONNX_PROVIDER_DLLS "${ONNX_DIR}/onnxruntime_providers*.dll")
    if(ONNX_PROVIDER_DLLS)
      install(FILES ${ONNX_PROVIDER_DLLS} DESTINATION bin)
    endif()
  endif()

  # Copy Microsoft C++ runtime redistributables if needed
  # Required for dynamic runtime linking (/MD)
  set(CMAKE_INSTALL_UCRT_LIBRARIES TRUE)
  set(CMAKE_INSTALL_SYSTEM_RUNTIME_DESTINATION bin)
  set(CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS_SKIP FALSE)
  include(InstallRequiredSystemLibraries)

  # Copy runtime DLLs only for piper target to avoid conflicts
  # test_piper will use the same directory structure in CI
  if(CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS)
    foreach(lib ${CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS})
      add_custom_command(TARGET piper POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
          "${lib}"
          "$<TARGET_FILE_DIR:piper>/"
        COMMENT "Copying runtime library ${lib}..."
      )
    endforeach()
  endif()
endif()
