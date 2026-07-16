cmake_minimum_required(VERSION 3.26)
project(ahpy_cmake_example LANGUAGES C)

if(NOT DEFINED AHPY_CONFIG)
  message(FATAL_ERROR "Pass -DAHPY_CONFIG=/absolute/path/to/ahpy-config.cmake")
endif()
include("${AHPY_CONFIG}")
if(NOT AHPY_ABI STREQUAL "universal")
  message(FATAL_ERROR "aHPy CMake example requires the Universal ABI")
endif()
if(NOT AHPY_MODULE_NAME STREQUAL "ahpy_cmake_example")
  message(FATAL_ERROR "aHPy contract module name does not match this target")
endif()

add_library(ahpy_cmake_example MODULE
  ahpy_cmake_example.c
  ${AHPY_RUNTIME_SOURCES}
)
set_target_properties(ahpy_cmake_example PROPERTIES
  C_STANDARD 99
  C_STANDARD_REQUIRED YES
  PREFIX ""
  SUFFIX "${AHPY_EXTENSION_SUFFIX}"
)
set_target_properties(ahpy_cmake_example PROPERTIES POSITION_INDEPENDENT_CODE YES)
target_compile_definitions(ahpy_cmake_example PRIVATE ${AHPY_DEFINITIONS})
target_include_directories(ahpy_cmake_example PRIVATE ${AHPY_INCLUDE_DIRS})
if(AHPY_RUNTIME_LIBRARY)
  target_link_libraries(ahpy_cmake_example PRIVATE "${AHPY_RUNTIME_LIBRARY}")
endif()
if(MSVC)
  target_link_options(ahpy_cmake_example PRIVATE "/EXPORT:${AHPY_INITIALIZER}")
endif()
