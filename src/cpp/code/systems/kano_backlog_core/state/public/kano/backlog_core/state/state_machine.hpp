#pragma once

#include "kano/backlog_core/models/models.hpp"
#include <string>
#include <vector>
#include <optional>

namespace kano::backlog_core {

class ReadyValidator {
public:
    /**
     * Check if item passes Ready gate business rules.
     * Returns list of missing section names.
     */
    static std::vector<std::string> check(const BacklogItem& item);
};

class StateMachine {
public:
    /**
     * Check if a transition is valid based on state and action alone.
     */
    static bool can_transition(ItemState state, StateAction action);

    /**
     * Execute state transition with side effects (timestamp, worklog).
     * Throws ValidationError if rules are violated.
     */
    static void transition(
        BacklogItem& item, 
        StateAction action, 
        const std::optional<std::string>& agent = std::nullopt, 
        const std::optional<std::string>& message = std::nullopt,
        const std::optional<std::string>& model = std::nullopt
    );

    /**
     * Helper to append a formatted worklog entry without a state transition.
     */
    static void record_worklog(
        BacklogItem& item,
        const std::string& agent,
        const std::string& message,
        const std::optional<std::string>& model = std::nullopt
    );

private:
    // Internal transition table key
    struct TransitionKey {
        ItemState from;
        StateAction action;
        
        bool operator<(const TransitionKey& other) const {
            if (from != other.from) return from < other.from;
            return action < other.action;
        }
    };
    
    static const std::map<TransitionKey, ItemState>& get_transitions();
};

} // namespace kano::backlog_core
