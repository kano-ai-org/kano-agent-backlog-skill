#include "kano/backlog_ops/config/config_ops.hpp"
#include <json/json.h>
#include <sstream>

namespace kano::backlog_ops {

std::string ConfigOps::dump_effective_config_json(const kano::backlog_core::BacklogContext& ctx) {
    Json::Value root;
    
    // Context
    Json::Value context;
    context["project_root"] = ctx.project_root.string();
    context["backlog_root"] = ctx.backlog_root.string();
    context["product_root"] = ctx.product_root.string();
    context["product_name"] = ctx.product_name;
    context["is_sandbox"] = ctx.is_sandbox;
    if (ctx.sandbox_root) {
        context["sandbox_root"] = ctx.sandbox_root->string();
    }
    root["context"] = context;

    // Config (Flattened Product Definition)
    Json::Value config;
    const auto& pd = ctx.product_def;
    config["name"] = pd.name;
    config["prefix"] = pd.prefix;
    config["backlog_root"] = pd.backlog_root;

    if (pd.vector_enabled) config["vector_enabled"] = *pd.vector_enabled;
    if (pd.vector_backend) config["vector_backend"] = *pd.vector_backend;
    if (pd.vector_metric) config["vector_metric"] = *pd.vector_metric;
    if (pd.analysis_llm_enabled) config["analysis_llm_enabled"] = *pd.analysis_llm_enabled;
    if (pd.cache_root) config["cache_root"] = *pd.cache_root;
    if (pd.log_debug) config["log_debug"] = *pd.log_debug;
    if (pd.log_verbosity) config["log_verbosity"] = *pd.log_verbosity;
    if (pd.embedding_provider) config["embedding_provider"] = *pd.embedding_provider;
    if (pd.embedding_model) config["embedding_model"] = *pd.embedding_model;
    if (pd.embedding_dimension) config["embedding_dimension"] = *pd.embedding_dimension;
    if (pd.chunking_target_tokens) config["chunking_target_tokens"] = *pd.chunking_target_tokens;
    if (pd.chunking_max_tokens) config["chunking_max_tokens"] = *pd.chunking_max_tokens;
    if (pd.tokenizer_adapter) config["tokenizer_adapter"] = *pd.tokenizer_adapter;
    if (pd.tokenizer_model) config["tokenizer_model"] = *pd.tokenizer_model;

    root["config"] = config;

    Json::StreamWriterBuilder wbuilder;
    wbuilder["indentation"] = "  ";
    return Json::writeString(wbuilder, root);
}

std::string ConfigOps::get_config_summary(const kano::backlog_core::BacklogContext& ctx) {
    std::stringstream ss;
    ss << "Product: " << ctx.product_name << "\n";
    ss << "Prefix:  " << ctx.product_def.prefix << "\n";
    ss << "Root:    " << ctx.product_root.string() << "\n";
    return ss.str();
}

} // namespace kano::backlog_ops
