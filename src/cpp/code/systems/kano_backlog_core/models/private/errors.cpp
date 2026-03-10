#include "kano/backlog_core/models/errors.hpp"

namespace kano::backlog_core {

std::string ValidationError::format_errors(const std::vector<std::string>& errs) {
    std::string result = "Validation failed:\n";
    for (const auto& e : errs) {
        result += "  - " + e + "\n";
    }
    return result;
}

std::string ReadyGateError::format_errors(const std::vector<std::string>& errs) {
    std::string result = "Ready gate failed:\n";
    for (const auto& e : errs) {
        result += "  - " + e + "\n";
    }
    return result;
}

std::string AmbiguousRefError::format_matches(const std::string& r, const std::vector<std::string>& m) {
    std::string result = "Ambiguous reference '" + r + "' matches: ";
    for (size_t i = 0; i < m.size(); ++i) {
        result += m[i];
        if (i < m.size() - 1) {
            result += ", ";
        }
    }
    return result;
}

} // namespace kano::backlog_core
