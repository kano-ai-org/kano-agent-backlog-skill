#include "kano/backlog_ops/view/view_ops.hpp"
#include "kano/backlog_core/frontmatter/canonical_store.hpp"
#include "kano/backlog_ops/topic/topic_ops.hpp"
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <chrono>
#include <map>
#include <cctype>
#include <optional>
#include <set>

namespace {

std::optional<std::chrono::sys_days> parse_iso_date(const std::string& value) {
    if (value.size() != 10 || value[4] != '-' || value[7] != '-') {
        return std::nullopt;
    }
    const auto parse_component = [&](std::size_t offset, std::size_t length) -> std::optional<unsigned> {
        unsigned result = 0;
        for (std::size_t index = 0; index < length; ++index) {
            const auto ch = static_cast<unsigned char>(value[offset + index]);
            if (!std::isdigit(ch)) {
                return std::nullopt;
            }
            result = result * 10U + static_cast<unsigned>(ch - static_cast<unsigned char>('0'));
        }
        return result;
    };

    const auto parsed_year = parse_component(0, 4);
    const auto parsed_month = parse_component(5, 2);
    const auto parsed_day = parse_component(8, 2);
    if (!parsed_year || !parsed_month || !parsed_day) {
        return std::nullopt;
    }

    const std::chrono::year_month_day calendar_date{
        std::chrono::year{static_cast<int>(*parsed_year)},
        std::chrono::month{*parsed_month},
        std::chrono::day{*parsed_day}
    };
    if (!calendar_date.ok()) {
        return std::nullopt;
    }
    return std::chrono::sys_days{calendar_date};
}

std::string lower_ascii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

std::string encode_group_component(const std::string& value, bool normalize_case) {
    std::ostringstream escaped;
    const auto source = normalize_case ? lower_ascii(value) : value;
    for (const auto raw_ch : source) {
        const auto ch = static_cast<unsigned char>(raw_ch);
        if (std::isalnum(ch) || ch == '-' || ch == '_' || ch == '.') {
            escaped << static_cast<char>(ch);
            continue;
        }
        escaped << '%' << std::uppercase << std::hex << std::setw(2) << std::setfill('0')
                << static_cast<int>(ch) << std::nouppercase << std::dec;
    }
    return escaped.str();
}

std::string group_component(const std::string& value) {
    return encode_group_component(value, true);
}

std::string exact_group_component(const std::string& value) {
    return encode_group_component(value, false);
}

std::string format_iso_date(const std::chrono::sys_days& value) {
    const std::chrono::year_month_day calendar_date{value};
    std::ostringstream out;
    out << std::setfill('0')
        << std::setw(4) << static_cast<int>(calendar_date.year()) << '-'
        << std::setw(2) << static_cast<unsigned>(calendar_date.month()) << '-'
        << std::setw(2) << static_cast<unsigned>(calendar_date.day());
    return out.str();
}

std::string topic_set_component(const kano::backlog_ops::ListItemProjection& item) {
    if (item.topics.empty()) {
        return "0";
    }
    std::ostringstream out;
    out << item.topics.size() << ':';
    for (std::size_t index = 0; index < item.topics.size(); ++index) {
        if (index > 0) {
            out << '+';
        }
        out << exact_group_component(item.topics[index]);
    }
    return out.str();
}

std::string priority_component(const kano::backlog_ops::ListItemProjection& item) {
    if (!item.priority) {
        return "0";
    }
    return "1:" + exact_group_component(*item.priority);
}

std::string item_recency(
    const kano::backlog_ops::ListItemProjection& item,
    const std::optional<std::chrono::sys_days>& cutoff
) {
    const auto item_date = parse_iso_date(item.updated);
    if (!item_date || !cutoff) {
        return "unknown";
    }
    return *item_date >= *cutoff ? "recent" : "older";
}

std::string compact_group_id(
    const kano::backlog_ops::ListItemProjection& item,
    const std::string& recency,
    const std::string& cutoff_date
) {
    std::string updated_selector = "unknown";
    if (recency == "older") {
        updated_selector = "before-" + cutoff_date;
    } else if (recency == "recent") {
        updated_selector = "on-or-after-" + cutoff_date;
    }
    return "state:" + group_component(kano::backlog_core::to_string(item.state)) +
           "/type:" + group_component(kano::backlog_core::to_string(item.type)) +
           "/priority:" + priority_component(item) +
           "/topics:" + topic_set_component(item) +
           "/updated:" + updated_selector;
}

std::optional<std::chrono::sys_days> cutoff_from_group_id(
    const std::string& group_id,
    std::string& cutoff_date
) {
    for (const auto& marker : {
             std::string("/updated:before-"),
             std::string("/updated:on-or-after-")
         }) {
        const auto position = group_id.find(marker);
        if (position == std::string::npos) {
            continue;
        }
        const auto value_start = position + marker.size();
        if (value_start + 10 > group_id.size()) {
            return std::nullopt;
        }
        const auto candidate = group_id.substr(value_start, 10);
        const auto parsed = parse_iso_date(candidate);
        if (parsed) {
            cutoff_date = candidate;
        }
        return parsed;
    }
    return std::nullopt;
}

bool contains_topic(
    const kano::backlog_ops::ListItemProjection& item,
    const std::string& topic
) {
    return std::find(item.topics.begin(), item.topics.end(), topic) != item.topics.end();
}

bool has_dependency_attention(const kano::backlog_ops::ListItemProjection& item) {
    return !item.links.blocks.empty() || !item.links.blocked_by.empty();
}

} // namespace

namespace kano::backlog_ops {

using namespace kano::backlog_core;

std::vector<IndexItem> ViewOps::list_items(BacklogIndex& index, const ViewFilter& filter) {
    if (!filter.product_root) {
        return index.query_items(filter.type, filter.state, filter.product);
    }
    IndexQuery query;
    query.type = filter.type;
    query.state = filter.state;
    const auto product = filter.product.value_or(filter.product_root->filename().string());
    return index.query_metadata(*filter.product_root, product, query).items;
}

IndexQueryResult ViewOps::list_items_with_diagnostics(
    const std::filesystem::path& index_path,
    const ViewFilter& filter
) {
    if (!filter.product_root) {
        throw std::runtime_error("metadata_index_product_root_required");
    }
    IndexQuery query;
    query.type = filter.type;
    query.state = filter.state;
    const auto product = filter.product.value_or(filter.product_root->filename().string());
    return query_metadata_index(index_path, *filter.product_root, product, query);
}

std::vector<ListItemProjection> ViewOps::list_item_projections(
    const std::filesystem::path& product_root,
    const std::filesystem::path& backlog_root
) {
    CanonicalStore store(product_root);
    std::vector<ListItemProjection> items;
    for (const auto& path : store.list_items()) {
        const auto item = store.read_metadata(path);
        ListItemProjection projected;
        projected.id = item.id;
        projected.uid = item.uid;
        projected.type = item.type;
        projected.title = item.title;
        projected.state = item.state;
        projected.priority = item.priority;
        projected.parent = item.parent;
        projected.duplicate_of = item.duplicate_of;
        projected.tags = item.tags;
        projected.updated = item.updated;
        projected.links = item.links;
        items.push_back(std::move(projected));
    }

    std::sort(items.begin(), items.end(), [](const auto& left, const auto& right) {
        if (left.updated != right.updated) {
            return left.updated > right.updated;
        }
        return left.id < right.id;
    });

    std::map<std::string, std::vector<std::string>> topics_by_item_ref;
    for (const auto& topic : TopicOps::list_topics(backlog_root)) {
        const auto topic_path = TopicOps::get_topic_path(topic.id, backlog_root);
        const auto manifest = TopicOps::load_manifest(topic_path);
        if (!manifest) {
            continue;
        }
        for (const auto& item_ref : manifest->seed_items) {
            topics_by_item_ref[item_ref].push_back(topic.id);
        }
    }

    for (std::size_t index = 0; index < items.size(); ++index) {
        auto& item = items[index];
        item.canonical_position = index;
        std::set<std::string> memberships;
        for (const auto& ref : {item.id, item.uid}) {
            const auto found = topics_by_item_ref.find(ref);
            if (found == topics_by_item_ref.end()) {
                continue;
            }
            memberships.insert(found->second.begin(), found->second.end());
        }
        item.topics.assign(memberships.begin(), memberships.end());
    }

    return items;
}

CompactListResult ViewOps::compact_items(
    const std::vector<ListItemProjection>& canonical_items,
    const CompactListOptions& options
) {
    if (options.recent_days < 0) {
        throw std::invalid_argument("recent_days must be non-negative");
    }

    std::optional<std::chrono::sys_days> latest_date;
    std::string latest_updated;
    for (const auto& item : canonical_items) {
        const auto parsed = parse_iso_date(item.updated);
        if (parsed && (!latest_date || *parsed > *latest_date)) {
            latest_date = parsed;
            latest_updated = item.updated.substr(0, 10);
        }
    }

    std::optional<std::chrono::sys_days> cutoff_date;
    std::string cutoff_text;
    if (latest_date) {
        cutoff_date = *latest_date - std::chrono::days{options.recent_days};
        cutoff_text = format_iso_date(*cutoff_date);
    }
    bool replayed_group_cutoff = false;
    if (options.group) {
        std::string selected_cutoff;
        const auto parsed_cutoff = cutoff_from_group_id(*options.group, selected_cutoff);
        if (parsed_cutoff) {
            cutoff_date = parsed_cutoff;
            cutoff_text = selected_cutoff;
            replayed_group_cutoff = true;
        }
    }

    CompactListResult result;
    result.canonical_total = canonical_items.size();
    result.latest_updated = latest_updated;
    result.cutoff_date = cutoff_text;
    result.cutoff_source = replayed_group_cutoff
        ? "group_selector"
        : "latest_updated_window";
    result.recent_days = replayed_group_cutoff
        ? std::nullopt
        : std::optional<int>(options.recent_days);
    result.expanded_retrieval =
        options.exact_item.has_value() ||
        options.state.has_value() ||
        options.topic.has_value() ||
        options.group.has_value();

    std::map<std::string, std::size_t> group_indexes;
    for (const auto& item : canonical_items) {
        const auto recency = item_recency(item, cutoff_date);
        const auto group_id = compact_group_id(item, recency, cutoff_text);

        if (options.type && item.type != *options.type) {
            continue;
        }
        if (options.state && item.state != *options.state) {
            continue;
        }
        if (options.exact_item &&
            item.id != *options.exact_item &&
            item.uid != *options.exact_item) {
            continue;
        }
        if (options.topic && !contains_topic(item, *options.topic)) {
            continue;
        }
        if (options.group && group_id != *options.group) {
            continue;
        }

        ++result.selection_total;

        auto group_it = group_indexes.find(group_id);
        if (group_it == group_indexes.end()) {
            CompactListGroup group;
            group.id = group_id;
            group.state = item.state;
            group.type = item.type;
            group.priority = item.priority;
            group.topics = item.topics;
            group.recency = recency;
            result.groups.push_back(std::move(group));
            group_it = group_indexes.emplace(group_id, result.groups.size() - 1).first;
        }

        auto& group = result.groups[group_it->second];
        ++group.total_count;

        const bool protected_state =
            item.state == ItemState::Ready ||
            item.state == ItemState::Review ||
            item.state == ItemState::Blocked;
        const bool show_item =
            result.expanded_retrieval ||
            item.state != ItemState::Done ||
            recency != "older" ||
            protected_state ||
            has_dependency_attention(item);
        if (show_item) {
            result.items.push_back(item);
            ++result.shown_count;
            ++group.shown_count;
        } else {
            ++result.omitted_count;
            ++group.omitted_count;
        }
    }

    return result;
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
       << std::setw(20) << "Duplicate Of"
       << "Title" << "\n";
    ss << std::string(100, '-') << "\n";

    for (const auto& item : items) {
        ss << std::left 
           << std::setw(20) << item.id 
           << std::setw(15) << to_string(item.type) 
           << std::setw(15) << to_string(item.state) 
           << std::setw(20) << item.duplicate_of.value_or("")
           << item.title << "\n";
    }

    return ss.str();
}

std::string ViewOps::render_compact_table(const CompactListResult& result) {
    std::stringstream ss;
    ss << "Compact work item list (opt-in)\n";
    ss << "Canonical items: " << result.canonical_total
       << " | Selected: " << result.selection_total
       << " | Shown: " << result.shown_count
       << " | Omitted: " << result.omitted_count << "\n";
    if (!result.latest_updated.empty()) {
        ss << "Recency anchor: " << result.latest_updated
           << " | Cutoff: " << result.cutoff_date
           << " | Cutoff source: " << result.cutoff_source;
        if (result.recent_days) {
            ss << " | Recent window: " << *result.recent_days << " days";
        }
        ss << "\n";
    }
    ss << "Safety: Ready, Review, Blocked, and dependency-bearing items are always shown.\n\n";

    std::vector<IndexItem> table_items;
    table_items.reserve(result.items.size());
    for (const auto& item : result.items) {
        IndexItem indexed;
        indexed.id = item.id;
        indexed.uid = item.uid;
        indexed.type = item.type;
        indexed.title = item.title;
        indexed.state = item.state;
        indexed.duplicate_of = item.duplicate_of;
        indexed.updated = item.updated;
        table_items.push_back(std::move(indexed));
    }
    ss << render_table(table_items);

    if (result.omitted_count > 0) {
        ss << "\nOmitted groups:\n";
        for (const auto& group : result.groups) {
            if (group.omitted_count == 0) {
                continue;
            }
            ss << "- " << group.id
               << " | total=" << group.total_count
               << " shown=" << group.shown_count
               << " omitted=" << group.omitted_count << "\n";
            ss << "  Retrieval selector: operation=workitem.list"
               << " kind=group value=" << group.id << "\n";
        }
    } else if (result.expanded_retrieval) {
        ss << "\nRetrieval selection expanded; no matched items were omitted.\n";
    }

    return ss.str();
}

} // namespace kano::backlog_ops
