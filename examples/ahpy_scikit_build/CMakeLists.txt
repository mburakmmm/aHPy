cmake_minimum_required(VERSION 3.26)
project(ahpy_scikit_build_example LANGUAGES C)
find_package(Python REQUIRED COMPONENTS Interpreter)

set(AHPY_MODULE_NAME ahpy_scikit_build_example)
set(AHPY_GENERATED_C "${CMAKE_CURRENT_SOURCE_DIR}/${AHPY_MODULE_NAME}.c")
set(AHPY_CONFIG "${CMAKE_CURRENT_BINARY_DIR}/ahpy-config.cmake")

execute_process(
  COMMAND "${Python_EXECUTABLE}" -m cython
    --runtime-backend=hpy-universal -3
    -o "${AHPY_GENERATED_C}"
    "${CMAKE_CURRENT_SOURCE_DIR}/${AHPY_MODULE_NAME}.pyx"
  COMMAND_ERROR_IS_FATAL ANY
)
execute_process(
  COMMAND "${Python_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/configure_ahpy.py"
    "${AHPY_CONFIG}" "${AHPY_MODULE_NAME}"
  COMMAND_ERROR_IS_FATAL ANY
)
include("${AHPY_CONFIG}")
if(NOT AHPY_ABI STREQUAL "universal")
  message(FATAL_ERROR "scikit-build-core example requires Universal HPy")
endif()

add_library(${AHPY_MODULE_NAME} MODULE
  "${AHPY_GENERATED_C}"
  ${AHPY_RUNTIME_SOURCES}
)
set_target_properties(${AHPY_MODULE_NAME} PROPERTIES
  C_STANDARD 99
  C_STANDARD_REQUIRED YES
  POSITION_INDEPENDENT_CODE YES
  PREFIX ""
  SUFFIX "${AHPY_EXTENSION_SUFFIX}"
)
target_compile_definitions(${AHPY_MODULE_NAME} PRIVATE ${AHPY_DEFINITIONS})
target_include_directories(${AHPY_MODULE_NAME} PRIVATE ${AHPY_INCLUDE_DIRS})
if(AHPY_RUNTIME_LIBRARY)
  target_link_libraries(${AHPY_MODULE_NAME} PRIVATE "${AHPY_RUNTIME_LIBRARY}")
endif()
if(MSVC)
  target_link_options(${AHPY_MODULE_NAME} PRIVATE "/EXPORT:${AHPY_INITIALIZER}")
endif()

install(TARGETS ${AHPY_MODULE_NAME}
  LIBRARY DESTINATION .
  RUNTIME DESTINATION .
)
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/${AHPY_MODULE_NAME}.py"
  DESTINATION .
)
