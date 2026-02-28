cmake_minimum_required(VERSION 3.24)

project(kano_backlog_webview LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_SCAN_FOR_MODULES ON)

if(WIN32)
  add_compile_definitions(NOMINMAX WIN32_LEAN_AND_MEAN)
endif()

set(CMAKE_INCLUDE_SYSTEM_FLAG_CXX "/I ")
set(CMAKE_NO_SYSTEM_FROM_IMPORTED ON)

include(FetchContent)

set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build all dependencies static" FORCE)

FetchContent_Declare(
  jsoncpp
  GIT_REPOSITORY https://github.com/open-source-parsers/jsoncpp.git
  GIT_TAG 1.9.6
)

FetchContent_Declare(
  zlib
  GIT_REPOSITORY https://github.com/madler/zlib.git
  GIT_TAG v1.3.1
)

set(JSONCPP_WITH_TESTS OFF CACHE BOOL "" FORCE)
set(JSONCPP_WITH_POST_BUILD_UNITTEST OFF CACHE BOOL "" FORCE)
set(JSONCPP_WITH_PKGCONFIG_SUPPORT OFF CACHE BOOL "" FORCE)
set(BUILD_OBJECT_LIBS OFF CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(jsoncpp)
FetchContent_MakeAvailable(zlib)

if(TARGET jsoncpp_lib)
  set(_jsoncpp_target jsoncpp_lib)
elseif(TARGET jsoncpp_static)
  set(_jsoncpp_target jsoncpp_static)
elseif(TARGET JsonCpp::JsonCpp)
  set(_jsoncpp_target JsonCpp::JsonCpp)
else()
  message(FATAL_ERROR "jsoncpp target not found after FetchContent")
endif()

set(JSONCPP_INCLUDE_DIRS "${jsoncpp_SOURCE_DIR}/include" CACHE PATH "jsoncpp include dir" FORCE)
set(JSONCPP_LIBRARIES "${_jsoncpp_target}" CACHE STRING "jsoncpp library target" FORCE)

set(ZLIB_INCLUDE_DIR "${zlib_BINARY_DIR};${zlib_SOURCE_DIR}" CACHE STRING "zlib include dirs" FORCE)
set(ZLIB_LIBRARY "${zlib_BINARY_DIR}/zlibstaticd.lib" CACHE FILEPATH "zlib library" FORCE)

FetchContent_Declare(
  drogon
  GIT_REPOSITORY https://github.com/drogonframework/drogon.git
  GIT_TAG v1.9.8
)

set(BUILD_CTL OFF CACHE BOOL "" FORCE)
set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_ORM OFF CACHE BOOL "" FORCE)
set(BUILD_YAML_CONFIG OFF CACHE BOOL "" FORCE)
set(BUILD_BROTLI OFF CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(drogon)

add_subdirectory(systems/kano_backlog_webview_core)
add_subdirectory(apps/kano_backlog_webview)
