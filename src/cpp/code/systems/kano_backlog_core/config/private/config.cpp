#include "kano/backlog_core/config/config.hpp"
#include "kano/backlog_core/models/errors.hpp"
#include <toml++/toml.hpp>
#include <iostream>

namespace kano::backlog_core {

// ProjectConfig Implementation
std::optional<ProjectConfig> ProjectConfig::load_from_toml(const std::filesystem::path& file_path) {
    if (!std::filesystem::exists(file_path)) {
        return std::nullopt;
    }

    try {
        auto tbl = toml::parse_file(file_path.string());
        ProjectConfig config;

        if (auto products_node = tbl.get_as<toml::table>("products")) {
            for (auto it = products_node->begin(); it != products_node->end(); ++it) {
                if (auto product_tbl = it->second.as_table()) {
                    ProductDefinition pd;
                    std::string key = std::string(it->first.str());
                    
                    pd.name = product_tbl->get_as<std::string>("name") ? product_tbl->get_as<std::string>("name")->get() : key;
                    pd.prefix = product_tbl->get_as<std::string>("prefix") ? product_tbl->get_as<std::string>("prefix")->get() : "";
                    pd.backlog_root = product_tbl->get_as<std::string>("backlog_root") ? product_tbl->get_as<std::string>("backlog_root")->get() : "";

                    // Optional fields
                    if (auto n = product_tbl->get_as<bool>("vector_enabled")) pd.vector_enabled = n->get();
                    if (auto n = product_tbl->get_as<std::string>("vector_backend")) pd.vector_backend = n->get();
                    if (auto n = product_tbl->get_as<std::string>("vector_metric")) pd.vector_metric = n->get();
                    if (auto n = product_tbl->get_as<bool>("analysis_llm_enabled")) pd.analysis_llm_enabled = n->get();
                    if (auto n = product_tbl->get_as<std::string>("cache_root")) pd.cache_root = n->get();
                    if (auto n = product_tbl->get_as<bool>("log_debug")) pd.log_debug = n->get();
                    if (auto n = product_tbl->get_as<std::string>("log_verbosity")) pd.log_verbosity = n->get();
                    if (auto n = product_tbl->get_as<std::string>("embedding_provider")) pd.embedding_provider = n->get();
                    if (auto n = product_tbl->get_as<std::string>("embedding_model")) pd.embedding_model = n->get();
                    if (auto n = product_tbl->get_as<int64_t>("embedding_dimension")) pd.embedding_dimension = static_cast<int>(n->get());
                    if (auto n = product_tbl->get_as<int64_t>("chunking_target_tokens")) pd.chunking_target_tokens = static_cast<int>(n->get());
                    if (auto n = product_tbl->get_as<int64_t>("chunking_max_tokens")) pd.chunking_max_tokens = static_cast<int>(n->get());
                    if (auto n = product_tbl->get_as<std::string>("tokenizer_adapter")) pd.tokenizer_adapter = n->get();
                    if (auto n = product_tbl->get_as<std::string>("tokenizer_model")) pd.tokenizer_model = n->get();

                    config.products[key] = pd;
                }
            }
        }
        return config;
    } catch (const toml::parse_error& err) {
        throw ConfigError("Failed to parse TOML from " + file_path.string() + ": " + std::string(err.description()));
    }
}

std::optional<ProductDefinition> ProjectConfig::get_product(const std::string& name) const {
    auto it = products.find(name);
    if (it != products.end()) {
        return it->second;
    }
    return std::nullopt;
}

std::optional<std::filesystem::path> ProjectConfig::resolve_backlog_root(const std::string& product_name, const std::filesystem::path& config_file_path) const {
    auto product = get_product(product_name);
    if (!product) {
        return std::nullopt;
    }

    std::filesystem::path backlog_root(product->backlog_root);
    if (backlog_root.is_absolute()) {
        return backlog_root;
    }

    std::filesystem::path project_root;
    if (config_file_path.parent_path().filename() == ".kano") {
        project_root = config_file_path.parent_path().parent_path();
    } else {
        project_root = config_file_path.parent_path();
    }

    return std::filesystem::weakly_canonical(project_root / backlog_root);
}

// ConfigLoader Implementation
std::optional<std::filesystem::path> ConfigLoader::find_project_config(const std::filesystem::path& start_path) {
    std::filesystem::path current = std::filesystem::is_directory(start_path) ? start_path : start_path.parent_path();
    
    while (true) {
        std::filesystem::path config_path = current / ".kano" / "backlog_config.toml";
        if (std::filesystem::exists(config_path)) {
            return config_path;
        }
        
        if (!current.has_parent_path() || current == current.parent_path()) {
            break;
        }
        current = current.parent_path();
    }
    return std::nullopt;
}

// BacklogContext Implementation
BacklogContext BacklogContext::resolve(
    const std::filesystem::path& resource_path, 
    const std::optional<std::string>& product_name_opt, 
    const std::optional<std::string>& sandbox_name
) {
    std::filesystem::path abs_resource = std::filesystem::absolute(resource_path);
    
    auto config_path = ConfigLoader::find_project_config(abs_resource);
    if (!config_path) {
        throw ConfigError("Project config required but not found. Create .kano/backlog_config.toml in project root.");
    }

    auto project_config = ProjectConfig::load_from_toml(*config_path);
    if (!project_config) {
        throw ConfigError("Failed to parse project config at " + config_path->string());
    }

    std::string product_name;
    bool is_sandbox = false;

    // The effective product definition resolved for this context
    ProductDefinition product_def;
    if (!product_name_opt || product_name_opt->empty()) {
        if (project_config->products.size() == 1) {
            product_name = project_config->products.begin()->first;
        } else if (project_config->products.size() > 1) {
            throw ConfigError("Multiple products found; specify product explicitly.");
        } else {
            throw ConfigError("No products defined in project config");
        }
    } else {
        product_name = *product_name_opt;
    }

    auto product_root = project_config->resolve_backlog_root(product_name, *config_path);
    if (!product_root) {
        throw ConfigError("Product '" + product_name + "' not found in project config");
    }

    std::filesystem::path project_root;
    if (config_path->parent_path().filename() == ".kano") {
        project_root = config_path->parent_path().parent_path();
    } else {
        project_root = config_path->parent_path();
    }

    std::filesystem::path backlog_root = *product_root;
    if (product_root->parent_path().filename() == "products" && product_root->parent_path().parent_path().filename() == "backlog") {
        backlog_root = product_root->parent_path().parent_path();
    }

    BacklogContext ctx;
    ctx.project_root = project_root;
    ctx.product_root = *product_root;
    ctx.backlog_root = backlog_root;
    ctx.product_name = product_name;
    
    // Find the actual product definition from config
    auto it = project_config->products.find(product_name);
    if (it != project_config->products.end()) {
        ctx.product_def = it->second;
    }

    if (sandbox_name && !sandbox_name->empty()) {
        ctx.sandbox_root = backlog_root.parent_path() / "backlog_sandbox" / *sandbox_name;
        ctx.is_sandbox = true;
    }

    return ctx;
}

} // namespace kano::backlog_core
