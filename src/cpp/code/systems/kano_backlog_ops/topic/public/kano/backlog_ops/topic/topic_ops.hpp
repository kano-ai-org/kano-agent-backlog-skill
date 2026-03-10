#pragma once

#include "kano/backlog_core/models/models.hpp"
#include <string>
#include <vector>
#include <optional>

namespace kano::backlog_ops {

/**
 * TopicOps manages "topic-scoped" work context.
 * Ported from topic.py
 */
class TopicOps {
public:
    struct TopicStatus {
        std::string id;
        std::string title;
        bool is_active;
        int item_count;
    };

    /**
     * Create or switch to a topic.
     */
    static void set_current_topic(const std::string& topic_id, const std::string& agent);

    /**
     * Get the currently active topic ID.
     */
    static std::optional<std::string> get_current_topic();

    /**
     * Get status of a specific topic.
     */
    static TopicStatus get_topic_status(const std::string& topic_id);
};

} // namespace kano::backlog_ops
