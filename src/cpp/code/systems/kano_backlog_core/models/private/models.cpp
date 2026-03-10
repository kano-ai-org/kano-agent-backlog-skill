#include "kano/backlog_core/models/models.hpp"
#include <regex>

namespace kano::backlog_core {

std::string to_string(ItemType type) {
    switch (type) {
        case ItemType::Epic: return "Epic";
        case ItemType::Feature: return "Feature";
        case ItemType::UserStory: return "UserStory";
        case ItemType::Task: return "Task";
        case ItemType::Bug: return "Bug";
        default: return "Unknown";
    }
}

std::optional<ItemType> parse_item_type(const std::string& str) {
    if (str == "Epic" || str == "epic") return ItemType::Epic;
    if (str == "Feature" || str == "feature") return ItemType::Feature;
    if (str == "UserStory" || str == "userstory") return ItemType::UserStory;
    if (str == "Task" || str == "task") return ItemType::Task;
    if (str == "Bug" || str == "bug") return ItemType::Bug;
    return std::nullopt;
}

std::string to_string(ItemState state) {
    switch (state) {
        case ItemState::New: return "New";
        case ItemState::Proposed: return "Proposed";
        case ItemState::Planned: return "Planned";
        case ItemState::Ready: return "Ready";
        case ItemState::InProgress: return "InProgress";
        case ItemState::Review: return "Review";
        case ItemState::Done: return "Done";
        case ItemState::Blocked: return "Blocked";
        case ItemState::Dropped: return "Dropped";
        default: return "Unknown";
    }
}

std::optional<ItemState> parse_item_state(const std::string& str) {
    if (str == "New" || str == "new") return ItemState::New;
    if (str == "Proposed" || str == "proposed") return ItemState::Proposed;
    if (str == "Planned" || str == "planned") return ItemState::Planned;
    if (str == "Ready" || str == "ready") return ItemState::Ready;
    if (str == "InProgress" || str == "inprogress") return ItemState::InProgress;
    if (str == "Review" || str == "review") return ItemState::Review;
    if (str == "Done" || str == "done") return ItemState::Done;
    if (str == "Blocked" || str == "blocked") return ItemState::Blocked;
    if (str == "Dropped" || str == "dropped") return ItemState::Dropped;
    return std::nullopt;
}

std::string to_string(StateAction action) {
    switch (action) {
        case StateAction::Propose: return "propose";
        case StateAction::Ready: return "ready";
        case StateAction::Start: return "start";
        case StateAction::Review: return "review";
        case StateAction::Done: return "done";
        case StateAction::Block: return "block";
        case StateAction::Drop: return "drop";
        default: return "unknown";
    }
}

std::optional<StateAction> parse_state_action(const std::string& str) {
    if (str == "propose") return StateAction::Propose;
    if (str == "ready") return StateAction::Ready;
    if (str == "start") return StateAction::Start;
    if (str == "review") return StateAction::Review;
    if (str == "done") return StateAction::Done;
    if (str == "block") return StateAction::Block;
    if (str == "drop") return StateAction::Drop;
    return std::nullopt;
}

std::optional<WorklogEntry> WorklogEntry::parse(const std::string& line) {
    // Regex pattern matching:
    // 2026-01-07 19:59 [agent=copilot] Message
    // 2026-01-07 19:59 [agent=copilot] [model=claude-sonnet-4.5] Message
    static const std::regex pattern(R"(^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \[agent=([^\]]+)\](?:\s+\[model=([^\]]+)\])? (.+)$)");
    std::smatch match;

    if (std::regex_match(line, match, pattern)) {
        WorklogEntry entry;
        entry.timestamp = match[1].str();
        entry.agent = match[2].str();
        if (match[3].matched && !match[3].str().empty()) {
            entry.model = match[3].str();
        }
        entry.message = match[4].str();
        return entry;
    }
    return std::nullopt;
}

std::string WorklogEntry::format() const {
    if (model.has_value() && !model->empty()) {
        return timestamp + " [agent=" + agent + "] [model=" + *model + "] " + message;
    }
    return timestamp + " [agent=" + agent + "] " + message;
}

} // namespace kano::backlog_core
