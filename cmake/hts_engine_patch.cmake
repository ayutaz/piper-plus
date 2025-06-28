# Patch for HTSEngine on Windows
# This file patches HTS_audio.c to fix Windows compilation issues

if(MSVC)
    # Create a patched version of HTS_audio.c
    file(READ "${CMAKE_CURRENT_SOURCE_DIR}/lib/HTS_audio.c" HTS_AUDIO_CONTENT)
    
    # Add necessary defines at the beginning of the file
    set(PATCH_HEADER "
#ifdef _WIN32
// Fix for ARM64 structure definitions in Windows SDK
#ifndef _ARM64_
#define _ARM64_
#endif
// Additional Windows compatibility
#define WIN32_LEAN_AND_MEAN
#endif
")
    
    # Prepend the patch header
    set(HTS_AUDIO_CONTENT "${PATCH_HEADER}${HTS_AUDIO_CONTENT}")
    
    # Write the patched file
    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/lib/HTS_audio_patched.c" "${HTS_AUDIO_CONTENT}")
endif()