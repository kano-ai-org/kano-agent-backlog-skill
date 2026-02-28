module;

#include <algorithm>
#include <cctype>
#include <string>

export module KanoBacklogWebview.Strings;

export namespace kano::backlog::webview::text {

std::string ToLower(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(),
                 [](const unsigned char c) {
                   return static_cast<char>(std::tolower(c));
                 });
  return value;
}

bool ContainsCaseInsensitive(const std::string& source,
                             const std::string& needle) {
  if (needle.empty()) {
    return true;
  }
  return ToLower(source).find(ToLower(needle)) != std::string::npos;
}

}  // namespace kano::backlog::webview::text
