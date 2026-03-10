#pragma once
#include <string>
#include <string_view>

namespace kano::backlog {

constexpr std::string_view GetBuildVersion() {
#ifdef KB_BUILD_VERSION
    return KB_BUILD_VERSION;
#elif defined(KB_VERSION)
    return KB_VERSION;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildVCS() {
#ifdef KB_BUILD_VCS
    return KB_BUILD_VCS;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildBranch() {
#ifdef KB_BUILD_BRANCH
    return KB_BUILD_BRANCH;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildRevision() {
#ifdef KB_BUILD_REVISION
    return KB_BUILD_REVISION;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildRevisionHashShort() {
#ifdef KB_BUILD_REVISION_HASH_SHORT
    return KB_BUILD_REVISION_HASH_SHORT;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildRevisionHash() {
#ifdef KB_BUILD_REVISION_HASH
    return KB_BUILD_REVISION_HASH;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildDirty() {
#ifdef KB_BUILD_DIRTY
    return KB_BUILD_DIRTY;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildHostName() {
#ifdef KB_BUILD_HOST_NAME
    return KB_BUILD_HOST_NAME;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildPlatform() {
#ifdef KB_BUILD_PLATFORM
    return KB_BUILD_PLATFORM;
#else
    return "unknown";
#endif
}

constexpr std::string_view GetBuildToolchain() {
#ifdef KB_BUILD_TOOLCHAIN
    return KB_BUILD_TOOLCHAIN;
#else
    return "unknown";
#endif
}

inline std::string GetBuildInfo() {
    std::string out;
    out.reserve(256);
    out += "version=";
    out += GetBuildVersion();
    out += " vcs=";
    out += GetBuildVCS();
    out += " branch=";
    out += GetBuildBranch();
    out += " rev=";
    out += GetBuildRevision();
    out += " hash_short=";
    out += GetBuildRevisionHashShort();
    out += " hash=";
    out += GetBuildRevisionHash();
    out += " dirty=";
    out += GetBuildDirty();
    out += " host=";
    out += GetBuildHostName();
    out += " platform=";
    out += GetBuildPlatform();
    out += " toolchain=";
    out += GetBuildToolchain();
    return out;
}

constexpr std::string_view GetVersion() {
    return GetBuildVersion();
}

} // namespace kano::backlog
