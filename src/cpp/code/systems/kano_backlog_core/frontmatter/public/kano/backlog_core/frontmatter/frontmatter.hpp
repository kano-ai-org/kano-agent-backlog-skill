#pragma once

#include <string>
#include <map>
#include <vector>
#include <yaml-cpp/yaml.h>

namespace kano::backlog_core {

struct FrontmatterContext {
    YAML::Node metadata;
    std::string body;
};

class Frontmatter {
public:
    /**
     * Parse markdown content into metadata (YAML) and body text.
     * Expects standard --- delimiters at the start.
     */
    static FrontmatterContext parse(const std::string& content);

    /**
     * Serialize metadata and body back to a markdown string with --- delimiters.
     */
    static std::string serialize(const FrontmatterContext& ctx);
    
    /**
     * Extract specific body sections (e.g., # Context) into a map.
     */
    static std::map<std::string, std::string> parse_body_sections(const std::string& body);
    
    /**
     * Reconstruct body from sections.
     */
    static std::string serialize_body_sections(const std::map<std::string, std::string>& sections);
};

} // namespace kano::backlog_core
