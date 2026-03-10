#pragma once

#include "kano/backlog_ops/index/backlog_index.hpp"
#include <filesystem>
#include <string>

namespace kano::backlog_ops {

/**
 * OrchestrationOps manages high-level backlog workflows.
 * Ported from init.py and other coordination logic.
 */
class OrchestrationOps {
public:
    /**
     * Initialize a new backlog at the given root.
     */
    static void initialize_backlog(const std::filesystem::path& root, const std::string& agent);

    /**
     * Refresh the index by scanning all item files.
     */
    static void refresh_index(BacklogIndex& index, const std::filesystem::path& root);
};

} // namespace kano::backlog_ops
