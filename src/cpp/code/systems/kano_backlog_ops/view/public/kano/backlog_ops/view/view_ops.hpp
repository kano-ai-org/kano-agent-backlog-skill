#pragma once

#include "kano/backlog_core/models/models.hpp"
#include "kano/backlog_ops/index/backlog_index.hpp"
#include <string>
#include <vector>
#include <optional>
#include <filesystem>
#include <cstddef>

namespace kano::backlog_ops {

struct RefreshDashboardsResult {
    std::vector<std::filesystem::path> views_refreshed;
};

struct ViewFilter {
    std::optional<kano::backlog_core::ItemType> type;
    std::optional<kano::backlog_core::ItemState> state;
    std::optional<std::filesystem::path> product_root;
    std::optional<std::string> parent_id;
    std::optional<std::string> owner;
    std::vector<std::string> tags;
};

struct ListItemProjection {
    std::string id;
    std::string uid;
    kano::backlog_core::ItemType type;
    std::string title;
    kano::backlog_core::ItemState state;
    std::optional<std::string> priority;
    std::optional<std::string> parent;
    std::optional<std::string> duplicate_of;
    std::vector<std::string> tags;
    std::string updated;
    kano::backlog_core::ItemLinks links;
    std::vector<std::string> topics;
    std::size_t canonical_position = 0;
};

struct CompactListOptions {
    std::optional<kano::backlog_core::ItemType> type;
    std::optional<kano::backlog_core::ItemState> state;
    std::optional<std::string> exact_item;
    std::optional<std::string> topic;
    std::optional<std::string> group;
    int recent_days = 30;
};

struct CompactListGroup {
    std::string id;
    kano::backlog_core::ItemState state;
    kano::backlog_core::ItemType type;
    std::optional<std::string> priority;
    std::vector<std::string> topics;
    std::string recency;
    std::size_t total_count = 0;
    std::size_t shown_count = 0;
    std::size_t omitted_count = 0;
};

struct CompactListResult {
    std::size_t canonical_total = 0;
    std::size_t selection_total = 0;
    std::size_t shown_count = 0;
    std::size_t omitted_count = 0;
    std::string latest_updated;
    std::string cutoff_date;
    std::string cutoff_source = "latest_updated_window";
    std::optional<int> recent_days = 30;
    bool expanded_retrieval = false;
    std::vector<ListItemProjection> items;
    std::vector<CompactListGroup> groups;
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
     * Read the complete list projection from canonical item files.
     *
     * The returned order is the canonical CLI list order: updated descending,
     * then display ID ascending. Topic memberships are a read-only projection
     * from topic manifests and do not modify canonical item metadata.
     */
    static std::vector<ListItemProjection> list_item_projections(
        const std::filesystem::path& product_root,
        const std::filesystem::path& backlog_root
    );

    /**
     * Build an opt-in compact projection without mutating or reordering input.
     *
     * By default only old Done items without blocker/dependency edges may be
     * omitted. Exact item, state, topic, and group selectors expand all matched
     * items so every omission is reversible through the CLI.
     */
    static CompactListResult compact_items(
        const std::vector<ListItemProjection>& canonical_items,
        const CompactListOptions& options = {}
    );

    /**
     * Render a simple ASCII table of items for CLI output.
     */
    static std::string render_table(const std::vector<IndexItem>& items);

    /**
     * Render the compact projection for the CLI's plain output mode.
     */
    static std::string render_compact_table(const CompactListResult& result);

    /**
     * Refresh plain markdown dashboards from canonical files.
     */
    static RefreshDashboardsResult refresh_dashboards(
        const std::filesystem::path& product_root,
        const std::string& agent
    );
};

} // namespace kano::backlog_ops
