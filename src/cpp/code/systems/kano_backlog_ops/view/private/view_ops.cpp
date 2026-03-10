#include "kano/backlog_ops/view/view_ops.hpp"
#include <sstream>
#include <iomanip>
#include <algorithm>

namespace kano::backlog_ops {

using namespace kano::backlog_core;

std::vector<IndexItem> ViewOps::list_items(BacklogIndex& index, const ViewFilter& filter) {
    // For now, we delegate simple type/state filtering to the index's query method.
    // In a more advanced implementation, we'd add complex filtering here.
    return index.query_items(filter.type, filter.state);
}

std::string ViewOps::render_table(const std::vector<IndexItem>& items) {
    if (items.empty()) {
        return "No items found.\n";
    }

    std::stringstream ss;
    
    // Header
    ss << std::left 
       << std::setw(20) << "ID" 
       << std::setw(15) << "Type" 
       << std::setw(15) << "State" 
       << "Title" << "\n";
    ss << std::string(80, '-') << "\n";

    for (const auto& item : items) {
        ss << std::left 
           << std::setw(20) << item.id 
           << std::setw(15) << to_string(item.type) 
           << std::setw(15) << to_string(item.state) 
           << item.title << "\n";
    }

    return ss.str();
}

} // namespace kano::backlog_ops
