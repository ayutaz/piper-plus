cmake_minimum_required(VERSION 3.15)
project(piper_plus_examples C)

find_package(PiperPlus REQUIRED)

add_executable(basic basic.c)
target_link_libraries(basic PRIVATE PiperPlus::piper_plus)

add_executable(streaming streaming.c)
target_link_libraries(streaming PRIVATE PiperPlus::piper_plus)

add_executable(multi_language multi_language.c)
target_link_libraries(multi_language PRIVATE PiperPlus::piper_plus)
