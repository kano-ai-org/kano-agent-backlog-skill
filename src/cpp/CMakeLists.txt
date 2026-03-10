cmake_minimum_required(VERSION 3.24)
project(KanoBacklog DESCRIPTION "Kano Backlog CLI" VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

if(MSVC)
    add_compile_options(
        "$<$<COMPILE_LANGUAGE:CXX>:/EHsc>"
        "$<$<COMPILE_LANGUAGE:CXX>:/GR>"
    )
endif()

# Get version from parent VERSION file (if it exists)
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../../VERSION")
    file(READ "${CMAKE_CURRENT_SOURCE_DIR}/../../VERSION" KB_VERSION_FILE_CONTENT)
    string(STRIP "${KB_VERSION_FILE_CONTENT}" KB_VERSION_STR)
else()
    set(KB_VERSION_STR "0.1.0-dev")
endif()
add_compile_definitions(KB_VERSION="${KB_VERSION_STR}")

# Build metadata from environment (CI integration)
set(KB_BUILD_VERSION_STR "${KB_VERSION_STR}")
set(KB_BUILD_VCS_STR "$ENV{KB_BUILD_VCS}")
set(KB_BUILD_BRANCH_STR "$ENV{KB_BUILD_BRANCH}")
set(KB_BUILD_REVISION_STR "$ENV{KB_BUILD_REVISION}")
set(KB_BUILD_REVISION_HASH_SHORT_STR "$ENV{KB_BUILD_REVISION_HASH_SHORT}")
set(KB_BUILD_REVISION_HASH_STR "$ENV{KB_BUILD_REVISION_HASH}")
set(KB_BUILD_DIRTY_STR "$ENV{KB_BUILD_DIRTY}")
set(KB_BUILD_HOST_NAME_STR "$ENV{KB_BUILD_HOST_NAME}")
set(KB_BUILD_PLATFORM_STR "$ENV{KB_BUILD_PLATFORM}")
set(KB_BUILD_TOOLCHAIN_STR "${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")

if(KB_BUILD_VCS_STR STREQUAL "")
    set(KB_BUILD_VCS_STR "unknown")
endif()
if(KB_BUILD_BRANCH_STR STREQUAL "")
    set(KB_BUILD_BRANCH_STR "unknown")
endif()
if(KB_BUILD_REVISION_STR STREQUAL "")
    set(KB_BUILD_REVISION_STR "unknown")
endif()
if(KB_BUILD_REVISION_HASH_SHORT_STR STREQUAL "")
    set(KB_BUILD_REVISION_HASH_SHORT_STR "unknown")
endif()
if(KB_BUILD_REVISION_HASH_STR STREQUAL "")
    set(KB_BUILD_REVISION_HASH_STR "unknown")
endif()
if(KB_BUILD_DIRTY_STR STREQUAL "")
    set(KB_BUILD_DIRTY_STR "unknown")
endif()
if(KB_BUILD_HOST_NAME_STR STREQUAL "")
    set(KB_BUILD_HOST_NAME_STR "unknown")
endif()
if(KB_BUILD_PLATFORM_STR STREQUAL "")
    set(KB_BUILD_PLATFORM_STR "${CMAKE_SYSTEM_NAME}-${CMAKE_SYSTEM_PROCESSOR}")
endif()

add_compile_definitions(KB_BUILD_VERSION="${KB_BUILD_VERSION_STR}")
add_compile_definitions(KB_BUILD_VCS="${KB_BUILD_VCS_STR}")
add_compile_definitions(KB_BUILD_BRANCH="${KB_BUILD_BRANCH_STR}")
add_compile_definitions(KB_BUILD_REVISION="${KB_BUILD_REVISION_STR}")
add_compile_definitions(KB_BUILD_REVISION_HASH_SHORT="${KB_BUILD_REVISION_HASH_SHORT_STR}")
add_compile_definitions(KB_BUILD_REVISION_HASH="${KB_BUILD_REVISION_HASH_STR}")
add_compile_definitions(KB_BUILD_DIRTY="${KB_BUILD_DIRTY_STR}")
add_compile_definitions(KB_BUILD_HOST_NAME="${KB_BUILD_HOST_NAME_STR}")
add_compile_definitions(KB_BUILD_PLATFORM="${KB_BUILD_PLATFORM_STR}")
add_compile_definitions(KB_BUILD_TOOLCHAIN="${KB_BUILD_TOOLCHAIN_STR}")

# CLI11 v2.4 uses <codecvt> which is removed in MSVC 19.50 (VS 2026)
add_compile_definitions(CLI11_HAS_CODECVT=0)

# ── Third-party dependencies ──────────────────────────────────────────────────

include(FetchContent)

set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build all dependencies static" FORCE)

# CLI11 — argument parsing (submodule, same as kano-git)
set(KB_CLI11_SOURCE_MODE "submodule" CACHE STRING "CLI11 source mode: submodule|fetch|system")
set_property(CACHE KB_CLI11_SOURCE_MODE PROPERTY STRINGS submodule fetch system)

if(KB_CLI11_SOURCE_MODE STREQUAL "submodule")
    set(KB_CLI11_SUBMODULE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/code/thirdparty/cli11")
    if(EXISTS "${KB_CLI11_SUBMODULE_DIR}/CMakeLists.txt")
        add_subdirectory("${KB_CLI11_SUBMODULE_DIR}" "${CMAKE_BINARY_DIR}/thirdparty/cli11-build" EXCLUDE_FROM_ALL)
    else()
        message(FATAL_ERROR "CLI11 submodule missing: ${KB_CLI11_SUBMODULE_DIR}. Run: git submodule update --init --recursive")
    endif()
elseif(KB_CLI11_SOURCE_MODE STREQUAL "fetch")
    FetchContent_Declare(
        CLI11
        GIT_REPOSITORY https://github.com/CLIUtils/CLI11.git
        GIT_TAG v2.4.2
    )
    FetchContent_MakeAvailable(CLI11)
    # Workaround: MSVC + Ninja Multi-Config can lose standard headers when FetchContent
    # dependencies are treated as SYSTEM includes. Fix by adding explicit include path.
    if(MSVC AND DEFINED cli11_SOURCE_DIR AND EXISTS "${cli11_SOURCE_DIR}/include")
        include_directories("${cli11_SOURCE_DIR}/include")
    endif()
elseif(KB_CLI11_SOURCE_MODE STREQUAL "system")
    find_package(CLI11 CONFIG REQUIRED)
else()
    message(FATAL_ERROR "Unsupported KB_CLI11_SOURCE_MODE: ${KB_CLI11_SOURCE_MODE}")
endif()

# toml++ — TOML config parsing
set(KB_TOMLPP_SOURCE_MODE "fetch" CACHE STRING "toml++ source mode: fetch|system")
set_property(CACHE KB_TOMLPP_SOURCE_MODE PROPERTY STRINGS fetch system)

if(KB_TOMLPP_SOURCE_MODE STREQUAL "fetch")
    # Workaround: Disable SYSTEM modifier for tomlplusplus includes to prevent MSVC bug
    # where standard headers like <string> disappear.
    set(tomlplusplus_INCLUDES_WITH_SYSTEM OFF CACHE BOOL "" FORCE)
    
    FetchContent_Declare(
        tomlplusplus
        GIT_REPOSITORY https://github.com/marzer/tomlplusplus.git
        GIT_TAG v3.4.0
    )
    set(TOMLPLUSPLUS_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(TOMLPLUSPLUS_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(TOMLPLUSPLUS_BUILD_DOCS OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(tomlplusplus)
elseif(KB_TOMLPP_SOURCE_MODE STREQUAL "system")
    find_package(tomlplusplus CONFIG REQUIRED)
else()
    message(FATAL_ERROR "Unsupported KB_TOMLPP_SOURCE_MODE: ${KB_TOMLPP_SOURCE_MODE}")
endif()

# Workaround for CMake 4.2+ which deprecates compatibility with CMake < 3.5
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

# ── yaml-cpp ───────────────────────────────────────────────────────────────────
include(FetchContent)
FetchContent_Declare(
    yaml-cpp
    GIT_REPOSITORY https://github.com/jbeder/yaml-cpp.git
    GIT_TAG 0.8.0
)
set(YAML_CPP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(yaml-cpp)


# ── Common Utilities ──────────────────────────────────────────────────────────

FetchContent_Declare(
    jsoncpp
    GIT_REPOSITORY https://github.com/open-source-parsers/jsoncpp.git
    GIT_TAG 1.9.6
)
set(JSONCPP_WITH_TESTS OFF CACHE BOOL "" FORCE)
set(JSONCPP_WITH_POST_BUILD_UNITTEST OFF CACHE BOOL "" FORCE)
set(JSONCPP_WITH_PKGCONFIG_SUPPORT OFF CACHE BOOL "" FORCE)
set(BUILD_OBJECT_LIBS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(jsoncpp)

if(TARGET jsoncpp_lib)
    set(_jsoncpp_target jsoncpp_lib)
elseif(TARGET jsoncpp_static)
    set(_jsoncpp_target jsoncpp_static)
elseif(TARGET JsonCpp::JsonCpp)
    set(_jsoncpp_target JsonCpp::JsonCpp)
endif()

# ── Platform detection ─────────────────────────────────────────────────────────

if(WIN32)
    add_compile_definitions(KB_PLATFORM_WINDOWS=1)
    add_compile_definitions(NOMINMAX WIN32_LEAN_AND_MEAN)
else()
    add_compile_definitions(KB_PLATFORM_UNIX=1)
endif()

# ── Output directories (mirrored from kano-git) ───────────────────────────────

set(KB_BUILD_ROOT "${CMAKE_SOURCE_DIR}/build")
set(KB_PRESET_NAME "unknown-preset" CACHE STRING "CMake preset name for artifact layout")

set(KB_BIN_ROOT "${KB_BUILD_ROOT}/bin/${KB_PRESET_NAME}")
set(KB_LIB_ROOT "${KB_BUILD_ROOT}/lib/${KB_PRESET_NAME}")
set(KB_SYMBOL_ROOT "${KB_BUILD_ROOT}/_intermediate/${KB_PRESET_NAME}/symbols")

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${KB_BIN_ROOT}")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${KB_LIB_ROOT}")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${KB_LIB_ROOT}")

set(CMAKE_PDB_OUTPUT_DIRECTORY "${KB_SYMBOL_ROOT}")
set(CMAKE_COMPILE_PDB_OUTPUT_DIRECTORY "${KB_SYMBOL_ROOT}")

foreach(cfg IN ITEMS Debug Release RelWithDebInfo MinSizeRel)
    string(TOUPPER "${cfg}" cfg_upper)
    string(TOLOWER "${cfg}" cfg_lower)

    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${cfg_upper} "${KB_BIN_ROOT}/${cfg_lower}")
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY_${cfg_upper} "${KB_LIB_ROOT}/${cfg_lower}")
    set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY_${cfg_upper} "${KB_LIB_ROOT}/${cfg_lower}")
    set(CMAKE_PDB_OUTPUT_DIRECTORY_${cfg_upper} "${KB_SYMBOL_ROOT}/${cfg_lower}")
    set(CMAKE_COMPILE_PDB_OUTPUT_DIRECTORY_${cfg_upper} "${KB_SYMBOL_ROOT}/${cfg_lower}")
endforeach()

# ── Subdirectories ─────────────────────────────────────────────────────────────

# CLI targets (new)
# FetchContent for sqlite3 (amalgamation style)
FetchContent_Declare(
  sqlite3
  GIT_REPOSITORY https://github.com/azadkuh/sqlite-amalgamation.git
  GIT_TAG        master
)
FetchContent_MakeAvailable(sqlite3)
# Manually add include directory since the dependency's CMakeLists.txt is incomplete for BUILD_INTERFACE
target_include_directories(SQLite3 INTERFACE $<BUILD_INTERFACE:${sqlite3_SOURCE_DIR}>)

add_subdirectory(code/systems/kano_backlog_core)
add_subdirectory(code/systems/kano_backlog_ops)
add_subdirectory(code/apps/kano_backlog_cli)

# Webview targets (existing — conditional)
option(KB_BUILD_WEBVIEW "Build kano-backlog webview targets" OFF)
if(KB_BUILD_WEBVIEW)
    # Webview-specific dependencies
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

    add_subdirectory(code/systems/kano_backlog_webview_core)
    add_subdirectory(code/apps/kano_backlog_webview)
endif()

option(KB_BUILD_TESTS "Build kano-backlog C++ test targets" ON)
if(KB_BUILD_TESTS)
    # Tests will be added here as they are created
    # add_subdirectory(code/tests)
endif()
