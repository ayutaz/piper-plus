# cmake/Testing.cmake
# Google Test fetch + BUILD_TESTS option + add_subdirectory(src/cpp/tests)

option(BUILD_TESTS "Build unit tests" OFF)
if(BUILD_TESTS)
  enable_testing()

  # Use FetchContent for Google Test
  include(FetchContent)
  FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip
  )
  # For Windows: Prevent overriding the parent project's compiler/linker settings
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  # Note: add_subdirectory(src/cpp/tests) is deferred to after all ExternalProject
  # targets are defined, so that if(TARGET openjtalk_external) etc. work correctly.
endif()
