#pragma once

#include "kano/backlog_core/models/models.hpp"
#include "kano/backlog_ops/index/backlog_index.hpp"
#include <string>
#include <vector>
#include <optional>

namespace kano::backlog_ops {

struct ViewFilter {
    std::optional<kano::backlog_core::ItemType> type;
    std::optional<kano::backlog_core::ItemState> state;
    std::optional<std::string> parent_id;
    std::optional<std::string> owner;
    std::vector<std::string> tags;
};

class ViewOps {
public:
    /**
     * List items based on filter criteria.
     * Uses the index for fast lookup.
     */
    static std::vector<IndexItem> list_items(
        BacklogIndex& index,
        const ViewFilter& filter = {}
    );

    /**
     * Render a simple ASCII table of items for CLI output.
     */
    static std::string render_table(const std::vector<IndexItem>& items);
};

} // namespace kano::backlog_ops
