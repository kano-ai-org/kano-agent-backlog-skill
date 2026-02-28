add_library(kano_backlog_webview_core STATIC)

target_sources(kano_backlog_webview_core
  PRIVATE
    private/BacklogWebviewService.cpp
  PUBLIC
    FILE_SET CXX_MODULES FILES
      private/KanoBacklogWebview.Strings.ixx
)

target_include_directories(kano_backlog_webview_core
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/public
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/internal
)

target_link_libraries(kano_backlog_webview_core
  PUBLIC
    drogon
)

add_library(kano::kano_backlog_webview_core ALIAS kano_backlog_webview_core)
