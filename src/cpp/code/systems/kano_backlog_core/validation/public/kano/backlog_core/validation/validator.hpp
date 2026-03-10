#pragma once

#include "kano/backlog_core/models/models.hpp"
#include <string>
#include <vector>
#include <utility>

namespace kano::backlog_core {

class Validator {
public:
    /**
     * Check if item meets Ready gate criteria based on its type.
     * Returns {is_valid, list_of_missing_field_names}.
     */
    static std::pair<bool, std::vector<std::string>> is_ready(const BacklogItem& item);

    /**
     * Validate basic schema requirements (ID format, UUIDv7, ISO dates, required fields).
     * Returns list of error messages (empty if valid).
     */
    static std::vector<std::string> validate_schema(const BacklogItem& item);
};

} // namespace kano::backlog_core
