// kano_backlog_core version module — implementation unit
// This file ensures the static library has at least one translation unit.

#include "version.hpp"

namespace kano::backlog {

// Force at least one symbol into the library for linker language detection.
const char* GetVersionCStr() {
    static const std::string versionStr{GetBuildVersion()};
    return versionStr.c_str();
}

} // namespace kano::backlog
