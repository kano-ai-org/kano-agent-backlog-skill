#include "kano/backlog_ops/topic/topic_ops.hpp"
#include <filesystem>
#include <fstream>

namespace kano::backlog_ops {

// For now, we use a simple file-based storage for the active topic, 
// similar to how the Python version might store it in a local state file.
static const std::string TOPIC_STATE_FILE = ".kano_topic";

void TopicOps::set_current_topic(const std::string& topic_id, const std::string& agent) {
    std::ofstream ofs(TOPIC_STATE_FILE);
    ofs << topic_id;
}

std::optional<std::string> TopicOps::get_current_topic() {
    if (!std::filesystem::exists(TOPIC_STATE_FILE)) {
        return std::nullopt;
    }
    std::ifstream ifs(TOPIC_STATE_FILE);
    std::string topic_id;
    ifs >> topic_id;
    return topic_id;
}

TopicOps::TopicStatus TopicOps::get_topic_status(const std::string& topic_id) {
    // This would normally query the index for items with this topic tag or parent
    return {topic_id, "Sample Topic", true, 0};
}

} // namespace kano::backlog_ops
