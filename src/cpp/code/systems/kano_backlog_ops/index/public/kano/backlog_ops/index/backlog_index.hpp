#pragma once

#include "kano/backlog_core/models/models.hpp"
#include <string>
#include <vector>
#include <optional>
#include <filesystem>
#include <sqlite3.h>

namespace kano::backlog_ops {

struct IndexItem {
    std::string id;
    std::string uid;
    kano::backlog_core::ItemType type;
    std::string title;
    kano::backlog_core::ItemState state;
    std::string path;
    std::string updated;
};

class BacklogIndex {
public:
    explicit BacklogIndex(const std::filesystem::path& db_path);
    ~BacklogIndex();

    /**
     * Initialize DB tables if they don't exist.
     */
    void initialize();

    /**
     * Index or update a single item.
     */
    void index_item(const kano::backlog_core::BacklogItem& item);

    /**
     * Remove an item from the index by its ID.
     */
    void remove_item(const std::string& id);

    /**
     * Get the next sequential ID number for a project-type pair.
     * Atomically increments the counter in id_sequences table.
     */
    int get_next_number(const std::string& prefix, const std::string& type_code);

    /**
     * Lookup item path by ID.
     */
    std::optional<std::filesystem::path> get_path_by_id(const std::string& id);

    /**
     * Lookup item path by UID.
     */
    std::optional<std::filesystem::path> get_path_by_uid(const std::string& uid);

    /**
     * List items with basic filtering.
     */
    std::vector<IndexItem> query_items(
        std::optional<kano::backlog_core::ItemType> type = std::nullopt,
        std::optional<kano::backlog_core::ItemState> state = std::nullopt
    );

private:
    sqlite3* db_ = nullptr;
    std::filesystem::path db_path_;

    void execute(const std::string& sql);
};

} // namespace kano::backlog_ops
