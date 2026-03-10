#include "kano/backlog_core/refs/ref_parser.hpp"
#include <regex>

namespace kano::backlog_core {

// Helper: trim whitespace
static std::string trim(const std::string& s) {
    size_t first = s.find_first_not_of(" \n\r\t");
    if (first == std::string::npos) return "";
    size_t last = s.find_last_not_of(" \n\r\t");
    return s.substr(first, (last - first + 1));
}

std::optional<ParsedRef> RefParser::parse(const std::string& ref) {
    auto d_ref = parse_display_id(ref);
    if (d_ref) return *d_ref;

    auto a_ref = parse_adr(ref);
    if (a_ref) return *a_ref;

    auto u_ref = parse_uuid(ref);
    if (u_ref) return *u_ref;

    return std::nullopt;
}

std::optional<DisplayIdRef> RefParser::parse_display_id(const std::string& ref) {
    static const std::regex pattern(R"(^([A-Z][A-Z0-9]{1,15})-(EPIC|FTR|USR|TSK|BUG)-(\d{4})$)");
    std::string s = trim(ref);
    std::smatch match;
    if (std::regex_match(s, match, pattern)) {
        DisplayIdRef res;
        res.product = match[1].str();
        res.type_abbrev = match[2].str();
        res.number = std::stoi(match[3].str());
        res.raw = s;
        return res;
    }
    return std::nullopt;
}

std::optional<AdrRef> RefParser::parse_adr(const std::string& ref) {
    static const std::regex pattern(R"(^ADR-(\d{4})(?:-appendix_([a-z0-9_-]+))?$)");
    std::string s = trim(ref);
    std::smatch match;
    if (std::regex_match(s, match, pattern)) {
        AdrRef res;
        res.number = std::stoi(match[1].str());
        if (match[2].matched) {
            res.appendix = match[2].str();
        }
        res.raw = s;
        return res;
    }
    return std::nullopt;
}

std::optional<UuidRef> RefParser::parse_uuid(const std::string& ref) {
    static const std::regex pattern(R"(^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$)");
    std::string s = trim(ref);
    if (std::regex_match(s, pattern)) {
        UuidRef res;
        res.uuid = s;
        res.raw = s;
        return res;
    }
    return std::nullopt;
}

} // namespace kano::backlog_core
