# download_with_retry.cmake
# Usage: cmake -P download_with_retry.cmake <URL> <DEST_FILE> <RETRY_COUNT> <RETRY_DELAY>

# Handle variable substitution in URL (e.g., ${FMT_VERSION})
if(CMAKE_ARGC GREATER 7)
    # Variable substitution provided as additional arguments
    set(VAR_NAME "${CMAKE_ARGV7}")
    set(VAR_VALUE "${CMAKE_ARGV8}")
    set(URL "${CMAKE_ARGV3}")
    string(REPLACE "\${${VAR_NAME}}" "${VAR_VALUE}" URL "${URL}")
else()
    set(URL "${CMAKE_ARGV3}")
endif()

set(DEST_FILE "${CMAKE_ARGV4}")
set(RETRY_COUNT "${CMAKE_ARGV5}")
set(RETRY_DELAY "${CMAKE_ARGV6}")

if(NOT URL OR NOT DEST_FILE)
    message(FATAL_ERROR "Usage: cmake -P download_with_retry.cmake <URL> <DEST_FILE> <RETRY_COUNT> <RETRY_DELAY>")
endif()

if(NOT RETRY_COUNT)
    set(RETRY_COUNT 3)
endif()

if(NOT RETRY_DELAY)
    set(RETRY_DELAY 30)
endif()

# Create destination directory
get_filename_component(DEST_DIR "${DEST_FILE}" DIRECTORY)
file(MAKE_DIRECTORY "${DEST_DIR}")

# Try downloading with retries
foreach(attempt RANGE 1 ${RETRY_COUNT})
    message(STATUS "Download attempt ${attempt}/${RETRY_COUNT} for ${URL}")
    
    file(DOWNLOAD 
        "${URL}" 
        "${DEST_FILE}"
        SHOW_PROGRESS
        STATUS download_status
        TIMEOUT 300  # 5 minute timeout per attempt
    )
    
    list(GET download_status 0 status_code)
    list(GET download_status 1 status_string)
    
    if(status_code EQUAL 0)
        message(STATUS "Successfully downloaded ${URL}")
        return()
    else()
        message(WARNING "Download failed (attempt ${attempt}/${RETRY_COUNT}): ${status_string}")
        
        # Check for rate limiting
        if(status_string MATCHES "429" OR status_string MATCHES "rate limit")
            message(STATUS "Rate limited. Waiting ${RETRY_DELAY} seconds before retry...")
        elseif(attempt LESS ${RETRY_COUNT})
            message(STATUS "Waiting ${RETRY_DELAY} seconds before retry...")
        endif()
        
        # Remove partial download
        if(EXISTS "${DEST_FILE}")
            file(REMOVE "${DEST_FILE}")
        endif()
        
        # Wait before retry (except on last attempt)
        if(attempt LESS ${RETRY_COUNT})
            execute_process(COMMAND ${CMAKE_COMMAND} -E sleep ${RETRY_DELAY})
        endif()
    endif()
endforeach()

message(FATAL_ERROR "Failed to download ${URL} after ${RETRY_COUNT} attempts")