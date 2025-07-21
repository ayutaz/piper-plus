# CPP source directory CMake configuration

# Add test executable
add_executable(hello_wasm hello_wasm.cpp)

# Set properties for WebAssembly build
set_target_properties(hello_wasm PROPERTIES
    SUFFIX ".js"
    LINK_FLAGS "--bind"
)

# Install targets
install(TARGETS hello_wasm
    RUNTIME DESTINATION ${CMAKE_BINARY_DIR}/dist
)

# Copy generated files
install(FILES 
    ${CMAKE_CURRENT_BINARY_DIR}/hello_wasm.js
    ${CMAKE_CURRENT_BINARY_DIR}/hello_wasm.wasm
    DESTINATION ${CMAKE_BINARY_DIR}/dist
)