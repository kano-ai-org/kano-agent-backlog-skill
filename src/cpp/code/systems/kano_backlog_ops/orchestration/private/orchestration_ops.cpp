#include "kano/backlog_ops/orchestration/orchestration_ops.hpp"
#include "kano/backlog_core/frontmatter/canonical_store.hpp"
#include <filesystem>

namespace kano::backlog_ops {

using namespace kano::backlog_core;

void OrchestrationOps::initialize_backlog(const std::filesystem::path& root, const std::string& agent) {
    std::filesystem::create_directories(root / "items");
    std::filesystem::create_directories(root / ".cache" / "index");
}

void OrchestrationOps::refresh_index(BacklogIndex& index, const std::filesystem::path& root) {
    // Clear and rebuild index from files
    CanonicalStore store(root);
    auto item_paths = store.list_items();
    
    // In a real implementation, we'd clear the index first.
    for (const auto& path : item_paths) {
        try {
            auto item = store.read(path);
            index.index_item(item);
        } catch (...) {
            // Log and continue
        }
    }
}

} // namespace kano::backlog_ops
