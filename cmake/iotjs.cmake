# Copyright 2015-present Samsung Electronics Co., Ltd. and other contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

cmake_minimum_required(VERSION 2.8)

include(${CMAKE_CURRENT_LIST_DIR}/JSONParser.cmake)

set(IOTJS_SOURCE_DIR ${CMAKE_SOURCE_DIR}/src)

# Platform configuration
# Look for files under src/platform/<system>/
string(TOLOWER ${CMAKE_SYSTEM_NAME} IOTJS_SYSTEM_OS)
set(PLATFORM_OS_DIR
    "${IOTJS_SOURCE_DIR}/platform/${IOTJS_SYSTEM_OS}")
file(GLOB IOTJS_PLATFORM_SRC "${PLATFORM_OS_DIR}/iotjs_*.c")

# Board configuration
# Look for files under src/platform/<system>/<board>/
if(NOT "${TARGET_BOARD}" STREQUAL "None")
  set(PLATFORM_BOARD_DIR
    "${PLATFORM_OS_DIR}/${TARGET_BOARD}")
  file(GLOB IOTJS_BOARD_SRC "${PLATFORM_BOARD_DIR}/iotjs_*.c")
  list(APPEND IOTJS_PLATFORM_SRC "${IOTJS_BOARD_SRC}")
endif()

set(IOTJS_CFLAGS ${CFLAGS_COMMON})

if(ENABLE_SNAPSHOT)
  set(JS2C_SNAPSHOT_ARG --snapshot-tool=${JERRY_HOST_SNAPSHOT})
  set(IOTJS_CFLAGS ${IOTJS_CFLAGS} -DENABLE_SNAPSHOT)
endif()

# Module configuration - listup all possible native C modules
function(getListOfVarsStartWith prefix varResult)
    set(moduleNames)
    get_cmake_property(vars VARIABLES)
    string(REPLACE "." "\\." prefix ${prefix})
    foreach(var ${vars})
      string(REGEX MATCH
             "(^|;)${prefix}([A-Za-z0-9_]+[A-Za-z]+)[A-Za-z0-9_.]*"
             matchedVar "${var}")
      if(matchedVar)
        list(APPEND moduleNames ${CMAKE_MATCH_2})
      endif()
    endforeach()
    list(REMOVE_DUPLICATES moduleNames)
    set(${varResult} ${moduleNames} PARENT_SCOPE)
endfunction()

function(addModuleDependencies module varResult)
  string(TOUPPER ${module} MODULE)
  set(moduleDefines)

  if(NOT "${${IOTJS_MODULE_${MODULE}_JSON}.modules.${module}.require}"
     STREQUAL "")
    foreach(idx
            ${${IOTJS_MODULE_${MODULE}_JSON}.modules.${module}.require})
      set(dependency
          ${${IOTJS_MODULE_${MODULE}_JSON}.modules.${module}.require_${idx}})
      string(TOUPPER ${dependency} DEPENDENCY)
      if(NOT ${ENABLE_MODULE_${DEPENDENCY}})
        list(APPEND moduleDefines ENABLE_MODULE_${DEPENDENCY})
        addModuleDependencies(${dependency} deps)
        list(APPEND varResult ${deps})
        list(REMOVE_DUPLICATES moduleDefines)
      endif()
    endforeach()
  endif()

  set(${varResult} ${moduleDefines} PARENT_SCOPE)
endfunction()

# Set the default profile if not specified
set(IOTJS_PROFILE "${CMAKE_SOURCE_DIR}/profiles/default.profile"
    CACHE STRING "Path to profile.")

if(NOT IS_ABSOLUTE ${IOTJS_PROFILE})
  set(IOTJS_PROFILE "${CMAKE_SOURCE_DIR}/${IOTJS_PROFILE}")
endif()

# Enable the modules defined by the profile
if(EXISTS ${IOTJS_PROFILE})
  file(READ "${IOTJS_PROFILE}" PROFILE_SETTINGS)
  string(REGEX REPLACE "^#.*$" "" PROFILE_SETTINGS "${PROFILE_SETTINGS}")
  string(REGEX REPLACE "[\r|\n]" ";" PROFILE_SETTINGS "${PROFILE_SETTINGS}")

  foreach(module_define ${PROFILE_SETTINGS})
    set(${module_define} ON CACHE BOOL "ON/OFF")
  endforeach()
else()
  message(FATAL_ERROR "Profile file: '${IOTJS_PROFILE}' doesn't exist!")
endif()

set(IOTJS_MODULES)
set(MODULES_INCLUDE_DIR)

# Add the basic descriptor file (src/modules.json)
list(APPEND EXTERNAL_MODULES ${IOTJS_SOURCE_DIR})

set(iotjs_module_idx 0)
foreach(module_descriptor ${EXTERNAL_MODULES})
  get_filename_component(MODULE_DIR ${module_descriptor} ABSOLUTE)

  if(NOT EXISTS "${MODULE_DIR}/modules.json")
    message(FATAL_ERROR "The modules.json file doesn't exist in ${MODULE_DIR}")
  endif()

  list(APPEND MODULES_INCLUDE_DIR ${MODULE_DIR})
  list(APPEND IOTJS_MODULES_JSONS "${iotjs_module_idx}")
  set(CURR_JSON "IOTJS_MODULES_JSON_${iotjs_module_idx}")
  set(${CURR_JSON}_PATH ${MODULE_DIR})

  file(READ "${MODULE_DIR}/modules.json" IOTJS_MODULES_JSON_FILE)
  sbeParseJson(${CURR_JSON} IOTJS_MODULES_JSON_FILE)

  getListOfVarsStartWith("${CURR_JSON}.modules." _IOTJS_MODULES)
  list(APPEND IOTJS_MODULES ${_IOTJS_MODULES})

  foreach(module ${_IOTJS_MODULES})
    string(TOUPPER ${module} MODULE)
    set(IOTJS_MODULE_${MODULE}_JSON ${CURR_JSON})
  endforeach()

  math(EXPR iotjs_module_idx "${iotjs_module_idx} + 1")
endforeach(module_descriptor)

list(REMOVE_DUPLICATES IOTJS_MODULES)

# Turn off the other modules
foreach(module ${IOTJS_MODULES})
  string(TOUPPER ${module} MODULE)
  set(ENABLE_MODULE_${MODULE} OFF CACHE BOOL "ON/OFF")
endforeach()

# Resolve the dependencies and set the ENABLE_MODULE_[NAME] variables
foreach(module ${IOTJS_MODULES})
  string(TOUPPER ${module} MODULE)
  if(${ENABLE_MODULE_${MODULE}})
    addModuleDependencies(${module} deps)
    foreach(module_define ${deps})
      set(${module_define} ON)
    endforeach()
    unset(deps)
  endif()
endforeach()

set(IOTJS_JS_MODULES)
set(IOTJS_NATIVE_MODULES)
set(IOTJS_MODULE_SRC)
set(IOTJS_MODULE_DEFINES)

message("IoT.js module configuration:")
getListOfVarsStartWith("ENABLE_MODULE_" IOTJS_ENABLED_MODULES)
foreach(MODULE ${IOTJS_ENABLED_MODULES})
  set(MODULE_DEFINE_VAR "ENABLE_MODULE_${MODULE}")
  message(STATUS "${MODULE_DEFINE_VAR} = ${${MODULE_DEFINE_VAR}}")
  # Set the defines for build
  if(${MODULE_DEFINE_VAR})
    list(APPEND IOTJS_MODULE_DEFINES "-D${MODULE_DEFINE_VAR}=1")
  else()
    list(APPEND IOTJS_MODULE_DEFINES "-D${MODULE_DEFINE_VAR}=0")
  endif()
endforeach()

# Collect the files of enabled modules
foreach(MODULE ${IOTJS_ENABLED_MODULES})
  if(${ENABLE_MODULE_${MODULE}})
    string(TOLOWER ${MODULE} module)
    set(IOTJS_MODULES_JSON ${IOTJS_MODULE_${MODULE}_JSON})
    set(MODULE_BASE_DIR ${${IOTJS_MODULES_JSON}_PATH})
    set(MODULE_PREFIX ${IOTJS_MODULES_JSON}.modules.${module}.)

    # Add js source
    set(MODULE_JS_FILE ${${MODULE_PREFIX}js_file})
    if(NOT "${MODULE_JS_FILE}" STREQUAL "")
      set(JS_PATH "${MODULE_BASE_DIR}/${MODULE_JS_FILE}")
      if(EXISTS "${JS_PATH}")
        list(APPEND IOTJS_JS_MODULES "${module}=${JS_PATH}")
      else()
        message(FATAL_ERROR "JS file doesn't exist: ${JS_PATH}")
      endif()
    endif()

    # Add platform-related native source
    if(NOT "${${MODULE_PREFIX}native_files}" STREQUAL ""
       AND NOT "${${MODULE_PREFIX}init}" STREQUAL "")
      list(APPEND IOTJS_NATIVE_MODULES "${MODULE}")
    endif()

    # Add common native source
    foreach(idx ${${MODULE_PREFIX}native_files})
      set(MODULE_C_FILE
          ${${MODULE_PREFIX}native_files_${idx}})
      set(MODULE_C_FILE "${MODULE_BASE_DIR}/${MODULE_C_FILE}")
      if(EXISTS "${MODULE_C_FILE}")
        list(APPEND IOTJS_MODULE_SRC ${MODULE_C_FILE})
      else()
        message(FATAL_ERROR "C file doesn't exist: ${MODULE_C_FILE}")
      endif()
    endforeach()

    getListOfVarsStartWith("${MODULE_PREFIX}" MODULE_KEYS)
    list(FIND MODULE_KEYS "platforms" PLATFORMS_KEY)

    set(PLATFORMS_PREFIX ${MODULE_PREFIX}platforms.)
    if(${PLATFORMS_KEY} GREATER -1)
      getListOfVarsStartWith("${PLATFORMS_PREFIX}" MODULE_PLATFORMS)
      list(FIND MODULE_PLATFORMS ${IOTJS_SYSTEM_OS} PLATFORM_NATIVES)

      # Add plaform-dependant native source if exists...
      if(${PLATFORM_NATIVES} GREATER -1)
        foreach(idx ${${PLATFORMS_PREFIX}${IOTJS_SYSTEM_OS}.native_files})
          set(MODULE_PLATFORM_FILE
              ${${PLATFORMS_PREFIX}${IOTJS_SYSTEM_OS}.native_files_${idx}})
          set(MODULE_PLATFORM_FILE "${MODULE_BASE_DIR}/${MODULE_PLATFORM_FILE}")
          if(EXISTS "${MODULE_PLATFORM_FILE}")
            list(APPEND IOTJS_MODULE_SRC ${MODULE_PLATFORM_FILE})
          else()
            message(FATAL_ERROR "C file doesn't exist: ${MODULE_PLATFORM_FILE}")
          endif()
        endforeach()
      # ...otherwise add native files from 'undefined' section.
      else()
        foreach(idx ${${PLATFORMS_PREFIX}undefined.native_files})
          set(MODULE_UNDEFINED_FILE
              "${${MODULE_PREFIX}undefined.native_files_${idx}}")
          set(MODULE_UNDEFINED_FILE
              "${MODULE_BASE_DIR}/${MODULE_UNDEFINED_FILE}")
          if(EXISTS "${MODULE_UNDEFINED_FILE}")
            list(APPEND IOTJS_MODULE_SRC ${MODULE_UNDEFINED_FILE})
          else()
            message(FATAL_ERROR "${MODULE_UNDEFINED_FILE} does not exists.")
          endif()
        endforeach()
      endif()
    endif()
  endif()
endforeach(MODULE)

list(APPEND IOTJS_JS_MODULES "iotjs=${IOTJS_SOURCE_DIR}/js/iotjs.js")

# Generate src/iotjs_module_inl.h
# Build up init function prototypes
set(IOTJS_MODULE_INITIALIZERS "")
foreach(MODULE ${IOTJS_NATIVE_MODULES})
  set(IOTJS_MODULES_JSON ${IOTJS_MODULE_${MODULE}_JSON})
  string(TOLOWER ${MODULE} module)

  set(IOTJS_MODULE_INITIALIZERS "${IOTJS_MODULE_INITIALIZERS}
extern iotjs_jval_t ${${IOTJS_MODULES_JSON}.modules.${module}.init}();")
endforeach()

# Build up module entries
set(IOTJS_MODULE_ENTRIES "")
set(IOTJS_MODULE_OBJECTS "")
foreach(MODULE ${IOTJS_NATIVE_MODULES})
  set(IOTJS_MODULES_JSON ${IOTJS_MODULE_${MODULE}_JSON})
  string(TOLOWER ${MODULE} module)
  set(INIT_FUNC ${${IOTJS_MODULES_JSON}.modules.${module}.init})

  set(IOTJS_MODULE_ENTRIES  "${IOTJS_MODULE_ENTRIES}
  { \"${module}\", ${INIT_FUNC} },")
  set(IOTJS_MODULE_OBJECTS "${IOTJS_MODULE_OBJECTS}
    { 0 },")
endforeach()

# Build up the contents of src/iotjs_module_inl.h
list(LENGTH IOTJS_NATIVE_MODULES IOTJS_MODULE_COUNT)
set(IOTJS_MODULE_INL_H "/* File generated via iotjs.cmake */
${IOTJS_MODULE_INITIALIZERS}

const
iotjs_module_t iotjs_modules[${IOTJS_MODULE_COUNT}] = {${IOTJS_MODULE_ENTRIES}
};

iotjs_module_objects_t iotjs_module_objects[${IOTJS_MODULE_COUNT}] = {
${IOTJS_MODULE_OBJECTS}
};
")

file(WRITE ${IOTJS_SOURCE_DIR}/iotjs_module_inl.h "${IOTJS_MODULE_INL_H}")

# Cleanup
unset(IOTJS_MODULE_INL_H)
unset(IOTJS_MODULES_JSON_FILE)

foreach(idx ${IOTJS_MODULES_JSONS})
  sbeClearJson(IOTJS_MODULES_JSON_${idx})
  unset(IOTJS_MODULES_JSON_${idx}_PATH)
endforeach()

foreach(module ${IOTJS_MODULES})
  string(TOUPPER ${module} MODULE)
  unset(IOTJS_MODULE_${MODULE}_JSON)
endforeach()


# Run js2c
set(JS2C_RUN_MODE "release")
if("${CMAKE_BUILD_TYPE}" STREQUAL "Debug")
  set(JS2C_RUN_MODE "debug")
endif()

add_custom_command(
  OUTPUT ${IOTJS_SOURCE_DIR}/iotjs_js.c ${IOTJS_SOURCE_DIR}/iotjs_js.h
  COMMAND python ${ROOT_DIR}/tools/js2c.py
  ARGS --buildtype=${JS2C_RUN_MODE}
       --modules '${IOTJS_JS_MODULES}'
       ${JS2C_SNAPSHOT_ARG}
  DEPENDS ${ROOT_DIR}/tools/js2c.py
          jerry-snapshot
          ${IOTJS_SOURCE_DIR}/js/*.js
)

# Collect all sources into LIB_IOTJS_SRC
file(GLOB LIB_IOTJS_SRC ${IOTJS_SOURCE_DIR}/*.c)
list(APPEND LIB_IOTJS_SRC
  ${IOTJS_SOURCE_DIR}/iotjs_js.c
  ${IOTJS_SOURCE_DIR}/iotjs_js.h
  ${IOTJS_MODULE_SRC}
  ${IOTJS_PLATFORM_SRC}
)

separate_arguments(EXTERNAL_INCLUDE_DIR)
separate_arguments(EXTERNAL_STATIC_LIB)
separate_arguments(EXTERNAL_SHARED_LIB)

set(IOTJS_INCLUDE_DIRS
  ${EXTERNAL_INCLUDE_DIR}
  ${ROOT_DIR}/include
  ${IOTJS_SOURCE_DIR}
  ${MODULES_INCLUDE_DIR}
  ${PLATFORM_OS_DIR}
  ${JERRY_PORT_DIR}/include
  ${JERRY_INCLUDE_DIR}
  ${HTTPPARSER_INCLUDE_DIR}
  ${MBEDTLS_INCLUDE_DIR}
  ${TUV_INCLUDE_DIR}
)

if(NOT BUILD_LIB_ONLY)
  if("${CMAKE_SYSTEM_NAME}" STREQUAL "Darwin")
    set(IOTJS_LINK_FLAGS "-Xlinker -map -Xlinker iotjs.map")
  else()
    set(IOTJS_LINK_FLAGS "-Xlinker -Map -Xlinker iotjs.map")
  endif()
endif()

# Print out some configs
message("IoT.js configured with:")
message(STATUS "CMAKE_BUILD_TYPE         ${CMAKE_BUILD_TYPE}")
message(STATUS "CMAKE_C_FLAGS            ${CMAKE_C_FLAGS}")
message(STATUS "PLATFORM_DESCRIPTOR      ${PLATFORM_DESCRIPTOR}")
message(STATUS "TARGET_OS                ${TARGET_OS}")
message(STATUS "TARGET_SYSTEMROOT        ${TARGET_SYSTEMROOT}")
message(STATUS "TARGET_BOARD             ${TARGET_BOARD}")
message(STATUS "BUILD_LIB_ONLY           ${BUILD_LIB_ONLY}")
message(STATUS "ENABLE_LTO               ${ENABLE_LTO}")
message(STATUS "ENABLE_SNAPSHOT          ${ENABLE_SNAPSHOT}")
message(STATUS "EXTERNAL_MODULES         ${EXTERNAL_MODULES}")
message(STATUS "IOTJS_CFLAGS             ${IOTJS_CFLAGS}")
message(STATUS "IOTJS_LINK_FLAGS         ${IOTJS_LINK_FLAGS}")
message(STATUS "IOTJS_PROFILE            ${IOTJS_PROFILE}")

set(IOTJS_CFLAGS ${IOTJS_CFLAGS} ${IOTJS_MODULE_DEFINES})

# Configure the libiotjs.a
set(TARGET_LIB_IOTJS libiotjs)
add_library(${TARGET_LIB_IOTJS} STATIC ${LIB_IOTJS_SRC})
set_target_properties(${TARGET_LIB_IOTJS} PROPERTIES
  COMPILE_OPTIONS "${IOTJS_CFLAGS}"
  OUTPUT_NAME iotjs
  ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
)
target_include_directories(${TARGET_LIB_IOTJS} PRIVATE ${IOTJS_INCLUDE_DIRS})
target_link_libraries(${TARGET_LIB_IOTJS}
  ${JERRY_LIBS}
  ${TUV_LIBS}
  libhttp-parser
  ${MBEDTLS_LIBS}
  ${EXTERNAL_STATIC_LIB}
  ${EXTERNAL_SHARED_LIB}
)

if("${LIB_INSTALL_DIR}" STREQUAL "")
  set(LIB_INSTALL_DIR "lib")
endif()

if("${BIN_INSTALL_DIR}" STREQUAL "")
  set(BIN_INSTALL_DIR "bin")
endif()

install(TARGETS ${TARGET_LIB_IOTJS} DESTINATION ${LIB_INSTALL_DIR})

# Configure the iotjs executable
if(NOT BUILD_LIB_ONLY)
  set(TARGET_IOTJS iotjs)
  add_executable(${TARGET_IOTJS} ${ROOT_DIR}/iotjs_linux.c)
  set_target_properties(${TARGET_IOTJS} PROPERTIES
    COMPILE_OPTIONS "${IOTJS_CFLAGS}"
    LINK_FLAGS "${CMAKE_EXE_LINKER_FLAGS} ${IOTJS_LINK_FLAGS}"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  )
  target_include_directories(${TARGET_IOTJS} PRIVATE ${IOTJS_INCLUDE_DIRS})
  target_link_libraries(${TARGET_IOTJS} ${TARGET_LIB_IOTJS})
  install(TARGETS ${TARGET_IOTJS} DESTINATION ${BIN_INSTALL_DIR})
endif()
