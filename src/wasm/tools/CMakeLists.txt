cmake_minimum_required(VERSION 3.15)

# Dictionary compression tool (native build, not WebAssembly)
add_executable(dict_compressor dict_compressor.cpp)

# Link zlib
find_package(ZLIB REQUIRED)
target_link_libraries(dict_compressor ZLIB::ZLIB)

# Set C++ standard
set_target_properties(dict_compressor PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
)

# Test dictionary generator
add_executable(generate_test_dict generate_test_dict.cpp)
set_target_properties(generate_test_dict PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
)