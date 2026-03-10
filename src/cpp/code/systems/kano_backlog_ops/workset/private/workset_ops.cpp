#include "kano/backlog_ops/workset/workset_ops.hpp"
#include <fstream>
#include <algorithm>

namespace kano::backlog_ops {

Workset WorksetOps::init_workset(const std::string& agent, const std::filesystem::path& backlog_root) {
    // Basic implementation: load from .cache/worksets/<agent>.json or return empty
    Workset ws;
    ws.agent = agent;
    ws.id = "ws-" + agent; // Simplified
    ws.created_at = "2026-03-09";
    return ws;
}

void WorksetOps::add_item(Workset& workset, const std::string& item_uid) {
    if (std::find(workset.item_uids.begin(), workset.item_uids.end(), item_uid) == workset.item_uids.end()) {
        workset.item_uids.push_back(item_uid);
    }
}

bool WorksetOps::remove_item(Workset& workset, const std::string& item_uid) {
    auto it = std::find(workset.item_uids.begin(), workset.item_uids.end(), item_uid);
    if (it != workset.item_uids.end()) {
        workset.item_uids.erase(it);
        return true;
    }
    return false;
}

void WorksetOps::save_workset(const Workset& workset, const std::filesystem::path& backlog_root) {
    // For now, no-op or simple log
}

} // namespace kano::backlog_ops
