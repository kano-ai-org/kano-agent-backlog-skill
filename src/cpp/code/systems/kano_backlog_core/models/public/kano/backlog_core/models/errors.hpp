#pragma once

#include <stdexcept>
#include <string>
#include <vector>
#include <filesystem>

namespace kano::backlog_core {

class BacklogError : public std::runtime_error {
public:
    explicit BacklogError(const std::string& message) : std::runtime_error(message) {}
};

class ConfigError : public BacklogError {
public:
    explicit ConfigError(const std::string& message) : BacklogError(message) {}
};

class ItemNotFoundError : public BacklogError {
public:
    std::filesystem::path path;
    explicit ItemNotFoundError(const std::filesystem::path& p)
        : BacklogError("Item not found: " + p.string()), path(p) {}
};

class ParseError : public BacklogError {
public:
    std::filesystem::path path;
    std::string details;
    ParseError(const std::filesystem::path& p, const std::string& d)
        : BacklogError("Parse error in " + p.string() + ": " + d), path(p), details(d) {}
};

class ValidationError : public BacklogError {
public:
    std::vector<std::string> errors;
    explicit ValidationError(const std::vector<std::string>& errs)
        : BacklogError(format_errors(errs)), errors(errs) {}
private:
    static std::string format_errors(const std::vector<std::string>& errs);
};

class WriteError : public BacklogError {
public:
    explicit WriteError(const std::string& message) : BacklogError(message) {}
};

class InvalidTransitionError : public BacklogError {
public:
    std::string from_state;
    std::string to_state;
    std::string reason;

    InvalidTransitionError(const std::string& from, const std::string& to, const std::string& r)
        : BacklogError("Invalid transition " + from + " -> " + to + ": " + r),
          from_state(from), to_state(to), reason(r) {}
};

class ReadyGateError : public BacklogError {
public:
    std::vector<std::string> errors;
    explicit ReadyGateError(const std::vector<std::string>& errs)
        : BacklogError(format_errors(errs)), errors(errs) {}
private:
    static std::string format_errors(const std::vector<std::string>& errs);
};

class RefNotFoundError : public BacklogError {
public:
    std::string ref;
    explicit RefNotFoundError(const std::string& r)
        : BacklogError("Reference not found: " + r), ref(r) {}
};

class AmbiguousRefError : public BacklogError {
public:
    std::string ref;
    std::vector<std::string> matches;
    AmbiguousRefError(const std::string& r, const std::vector<std::string>& m)
        : BacklogError(format_matches(r, m)), ref(r), matches(m) {}
private:
    static std::string format_matches(const std::string& r, const std::vector<std::string>& m);
};

class IndexError : public BacklogError {
public:
    explicit IndexError(const std::string& message) : BacklogError(message) {}
};

class MigrationError : public IndexError {
public:
    int current_version;
    int target_version;
    std::string details;

    MigrationError(int current, int target, const std::string& d)
        : IndexError("Migration failed (v" + std::to_string(current) + " -> v" + std::to_string(target) + "): " + d),
          current_version(current), target_version(target), details(d) {}
};

} // namespace kano::backlog_core
