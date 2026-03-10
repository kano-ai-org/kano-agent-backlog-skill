#pragma once

#include "kano/backlog_core/models/models.hpp"
#include <string>
#include <vector>
#include <optional>
#include <filesystem>

namespace kano::backlog_ops {

struct Workset {
    std::string id;
    std::string agent;
    std::vector<std::string> item_uids;
    std::string created_at;
};

/**
 * WorksetOps manages active work item sets.
 * Ported from workset.py
 */
class WorksetOps {
public:
    /**
     * Initialize a new workset or load existing.
     */
    static Workset init_workset(const std::string& agent, const std::filesystem::path& backlog_root);

    /**
     * Add an item to the active workset.
     */
    static void add_item(Workset& workset, const std::string& item_uid);

    /**
     * Remove an item from the active workset.
     */
    bool remove_item(Workset& workset, const std::string& item_uid);

    /**
     * Save workset state to disk.
     */
    static void save_workset(const Workset& workset, const std::filesystem::path& backlog_root);
};

} // namespace kano::backlog_ops
