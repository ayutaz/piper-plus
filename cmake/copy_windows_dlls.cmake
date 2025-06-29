# CMake script to copy Windows DLLs
# This script is called as a post-build step to avoid batch command syntax issues

message("Starting Windows DLL copy process...")

# Copy ONNX Runtime DLL if it exists
if(EXISTS "${ONNXRUNTIME_DLL}")
    message("Copying ONNX Runtime DLL...")
    file(COPY "${ONNXRUNTIME_DLL}" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/Release/")
    file(COPY "${ONNXRUNTIME_DLL}" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/Debug/")
else()
    message("ONNX Runtime DLL not found at: ${ONNXRUNTIME_DLL}")
endif()

# Copy ONNX Runtime providers shared library if it exists
if(EXISTS "${ONNXRUNTIME_LIB_DIR}/onnxruntime_providers_shared.dll")
    message("Copying ONNX Runtime providers shared DLL...")
    file(COPY "${ONNXRUNTIME_LIB_DIR}/onnxruntime_providers_shared.dll" 
         DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/Release/")
    file(COPY "${ONNXRUNTIME_LIB_DIR}/onnxruntime_providers_shared.dll" 
         DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/Debug/")
endif()

# Copy all DLLs from piper-phonemize lib directory
file(GLOB PIPER_LIB_DLLS "${PIPER_PHONEMIZE_DIR}/lib/*.dll")
if(PIPER_LIB_DLLS)
    message("Copying DLLs from ${PIPER_PHONEMIZE_DIR}/lib/...")
    foreach(dll ${PIPER_LIB_DLLS})
        message("  - ${dll}")
        file(COPY "${dll}" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/Release/")
        file(COPY "${dll}" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/Debug/")
    endforeach()
else()
    message("No DLLs found in ${PIPER_PHONEMIZE_DIR}/lib/")
endif()

# Copy all DLLs from piper-phonemize bin directory
file(GLOB PIPER_BIN_DLLS "${PIPER_PHONEMIZE_DIR}/bin/*.dll")
if(PIPER_BIN_DLLS)
    message("Copying DLLs from ${PIPER_PHONEMIZE_DIR}/bin/...")
    foreach(dll ${PIPER_BIN_DLLS})
        message("  - ${dll}")
        file(COPY "${dll}" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/Release/")
        file(COPY "${dll}" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}/Debug/")
    endforeach()
else()
    message("No DLLs found in ${PIPER_PHONEMIZE_DIR}/bin/")
endif()

# List all DLLs in the Release directory
file(GLOB RELEASE_DLLS "${CMAKE_CURRENT_BINARY_DIR}/Release/*.dll")
if(RELEASE_DLLS)
    message("DLLs in Release directory:")
    foreach(dll ${RELEASE_DLLS})
        get_filename_component(dll_name "${dll}" NAME)
        message("  - ${dll_name}")
    endforeach()
else()
    message("No DLLs found in Release directory")
endif()

message("Windows DLL copy process completed.")