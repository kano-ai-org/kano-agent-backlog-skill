#include <CLI/CLI.hpp>
#include "version.hpp"
#include "kano/backlog_ops/workitem/workitem_ops.hpp"
#include "kano/backlog_ops/index/backlog_index.hpp"
#include "kano/backlog_ops/view/view_ops.hpp"
#include "kano/backlog_ops/orchestration/orchestration_ops.hpp"
#include "kano/backlog_ops/config/config_ops.hpp"
#include "kano/backlog_ops/doctor/doctor_ops.hpp"
#include <iostream>
#include <string>
#include <filesystem>

using namespace kano::backlog_core;
using namespace kano::backlog_ops;

int main(int InArgc, char* InArgv[]) {
    CLI::App app{
        "kano-backlog — Local-first backlog CLI\n"
        "Standalone: kano-backlog <command>\n"
        "Usage:      kano-backlog [options] <command> [args]",
        "kano-backlog"
    };

    // Context shared across commands
    std::string path_str = "."; 
    std::string product_name_opt;
    std::string sandbox_name_opt;
    
    // Global options
    auto* global_opts = app.add_option_group("Global Options");
    global_opts->add_option("-p,--path", path_str, "Resource path (default: .)");
    global_opts->add_option("-P,--product", product_name_opt, "Explicit product name");
    global_opts->add_option("-s,--sandbox", sandbox_name_opt, "Sandbox name");

    app.set_version_flag("--version,-V", std::string{kano::backlog::GetBuildVersion()});
    app.require_subcommand(0);
    app.fallthrough();

    auto resolve_ctx = [&]() {
        return BacklogContext::resolve(path_str, 
            product_name_opt.empty() ? std::nullopt : std::optional<std::string>(product_name_opt),
            sandbox_name_opt.empty() ? std::nullopt : std::optional<std::string>(sandbox_name_opt)
        );
    };

    try {
        // workitem group
        auto* workitemCmd = app.add_subcommand("workitem", "Work item operations");
        workitemCmd->alias("item");
        
        // workitem create
        auto* createCmd = workitemCmd->add_subcommand("create", "Create a new work item");
        std::string type_str, title, agent, parent;
        createCmd->add_option("-t,--type", type_str, "Item type (epic, feature, userstory, task, bug)")->required();
        createCmd->add_option("--title", title, "Item title")->required();
        createCmd->add_option("--agent", agent, "Agent ID")->required();
        createCmd->add_option("--parent", parent, "Parent item ID");
        
        createCmd->callback([&]() {
            auto ctx = resolve_ctx();
            BacklogIndex index(ctx.backlog_root / ".cache" / "index" / "backlog.db");
            index.initialize();
            
            auto type_opt = parse_item_type(type_str);
            if (!type_opt) throw std::runtime_error("Invalid item type: " + type_str);
            
            auto result = WorkitemOps::create_item(
                index, 
                ctx.product_root, 
                ctx.product_def.prefix,
                *type_opt, 
                title, 
                agent, 
                parent.empty() ? std::nullopt : std::optional<std::string>(parent)
            );
            
            std::cout << "Created item: " << result.id << " (" << result.uid << ")\n";
            std::cout << "Path: " << result.path.string() << "\n";
        });

        // workitem update-state
        auto* updateStateCmd = workitemCmd->add_subcommand("update-state", "Update item state");
        std::string ref, state_str, update_agent, update_msg;
        updateStateCmd->add_option("ref", ref, "Item ID or UID")->required();
        updateStateCmd->add_option("state", state_str, "New state (new, proposed, accepted, inprogress, inreview, done, blocked, trash)")->required();
        updateStateCmd->add_option("--agent", update_agent, "Agent ID")->required();
        updateStateCmd->add_option("-m,--message", update_msg, "Optional log message");
        bool update_force = false;
        updateStateCmd->add_flag("-f,--force", update_force, "Bypass Ready gate validation");

        updateStateCmd->callback([&]() {
            auto ctx = resolve_ctx();
            BacklogIndex index(ctx.backlog_root / ".cache" / "index" / "backlog.db");
            
            auto state_opt = parse_item_state(state_str);
            if (!state_opt) throw std::runtime_error("Invalid item state: " + state_str);
            
            auto result = WorkitemOps::update_state(
                index,
                ctx.product_root,
                ref,
                *state_opt,
                update_agent,
                update_msg.empty() ? std::nullopt : std::optional<std::string>(update_msg),
                update_force
            );
            
            if (result.worklog_appended) {
                std::cout << "Updated " << result.id << ": " << to_string(result.old_state) << " -> " << to_string(result.new_state);
                if (result.parent_synced) std::cout << " [Parent synced]";
                std::cout << "\n";
            } else {
                std::cout << "Item " << result.id << " is already in state " << to_string(result.new_state) << "\n";
            }
        });

        // workitem trash
        auto* trashCmd = workitemCmd->add_subcommand("trash", "Move item to trash");
        std::string trash_ref, trash_agent, trash_reason;
        trashCmd->add_option("ref", trash_ref, "Item ID or UID")->required();
        trashCmd->add_option("--agent", trash_agent, "Agent ID")->required();
        trashCmd->add_option("-r,--reason", trash_reason, "Reason for trashing");
        trashCmd->callback([&]() {
            auto ctx = resolve_ctx();
            BacklogIndex index(ctx.backlog_root / ".cache" / "index" / "backlog.db");
            auto result = WorkitemOps::trash_item(
                index, ctx.product_root, trash_ref, trash_agent,
                trash_reason.empty() ? std::nullopt : std::optional<std::string>(trash_reason)
            );
            std::cout << "Trashed item: " << result.item_ref << "\n";
            std::cout << "Source: " << result.source_path.string() << "\n";
            std::cout << "Trash: " << result.trashed_path.string() << "\n";
        });

        // workitem decision
        auto* decisionCmd = workitemCmd->add_subcommand("decision", "Record a decision for an item");
        std::string dec_ref, dec_text, dec_agent, dec_source;
        decisionCmd->add_option("ref", dec_ref, "Item ID or UID")->required();
        decisionCmd->add_option("text", dec_text, "Decision text")->required();
        decisionCmd->add_option("--agent", dec_agent, "Agent ID")->required();
        decisionCmd->add_option("--source", dec_source, "Source of decision (e.g. meeting, email)");
        decisionCmd->callback([&]() {
            auto ctx = resolve_ctx();
            BacklogIndex index(ctx.backlog_root / ".cache" / "index" / "backlog.db");
            auto result = WorkitemOps::add_decision_writeback(
                index, ctx.product_root, dec_ref, dec_text, dec_agent,
                dec_source.empty() ? std::nullopt : std::optional<std::string>(dec_source)
            );
            if (result.added) {
                std::cout << "Added decision to " << result.item_id << "\n";
            } else {
                std::cout << "Decision already exists in " << result.item_id << "\n";
            }
        });

        // workitem remap-id
        auto* remapIdCmd = workitemCmd->add_subcommand("remap-id", "Rename an item's ID and update references");
        std::string ri_ref, ri_to, ri_agent;
        remapIdCmd->add_option("ref", ri_ref, "Current item ID or UID")->required();
        remapIdCmd->add_option("--to", ri_to, "New ID")->required();
        remapIdCmd->add_option("--agent", ri_agent, "Agent ID")->required();
        remapIdCmd->callback([&]() {
            auto ctx = resolve_ctx();
            BacklogIndex index(ctx.backlog_root / ".cache" / "index" / "backlog.db");
            auto result = WorkitemOps::remap_id(index, ctx.product_root, ri_ref, ri_to, ri_agent);
            std::cout << "Remapped ID: " << result.old_id << " -> " << result.new_id << "\n";
            std::cout << "Updated " << result.updated_files << " files.\n";
        });

        // workitem remap-parent
        auto* remapCmd = workitemCmd->add_subcommand("remap-parent", "Remap item parent");
        std::string remap_ref, parent_ref, remap_agent;
        remapCmd->add_option("ref", remap_ref, "Item ID or UID")->required();
        remapCmd->add_option("parent", parent_ref, "New parent ID or UID (use 'none' to clear)")->required();
        remapCmd->add_option("--agent", remap_agent, "Agent ID")->required();

        remapCmd->callback([&]() {
            auto ctx = resolve_ctx();
            BacklogIndex index(ctx.backlog_root / ".cache" / "index" / "backlog.db");
            
            WorkitemOps::remap_parent(index, ctx.product_root, remap_ref, parent_ref, remap_agent);
            std::cout << "Successfully remapped parent for " << remap_ref << "\n";
        });

        // workitem list
        auto* listCmd = workitemCmd->add_subcommand("list", "List work items");
        listCmd->callback([&]() {
            auto ctx = resolve_ctx();
            BacklogIndex index(ctx.backlog_root / ".cache" / "index" / "backlog.db");
            
            ViewFilter filter;
            auto items = ViewOps::list_items(index, filter);
            std::cout << ViewOps::render_table(items);
        });

        // config group
        auto* configCmd = app.add_subcommand("config", "Configuration management");
        
        auto* configDumpCmd = configCmd->add_subcommand("dump", "Dump effective configuration as JSON");
        configDumpCmd->alias("show");
        configDumpCmd->callback([&]() {
            auto ctx = resolve_ctx();
            std::cout << ConfigOps::dump_effective_config_json(ctx) << std::endl;
        });

        // doctor command
        auto* doctorCmd = app.add_subcommand("doctor", "Environment healthy check");
        doctorCmd->callback([&]() {
            auto results = DoctorOps::run_all_checks(path_str);
            for (const auto& res : results) {
                std::cout << (res.passed ? "[PASS] " : "[FAIL] ") << res.name << ": " << res.message << "\n";
                if (!res.details.empty()) {
                    std::cout << "       " << res.details << "\n";
                }
            }
        });

        // admin group
        auto* adminCmd = app.add_subcommand("admin", "Administrative operations");
        
        // admin init
        auto* initCmd = adminCmd->add_subcommand("init", "Initialize a new backlog");
        std::string init_agent;
        initCmd->add_option("--agent", init_agent, "Agent ID")->required();
        initCmd->callback([&]() {
            std::filesystem::path backlog_root(path_str);
            OrchestrationOps::initialize_backlog(backlog_root, init_agent);
            std::cout << "Initialized backlog at: " << std::filesystem::absolute(backlog_root).string() << "\n";
        });

        // Other groups (stubs for now)
        app.add_subcommand("view", "Dashboard and view management");
        app.add_subcommand("topic", "Topic context management");
        app.add_subcommand("workset", "Workset management");
        app.add_subcommand("search", "Hybrid search");

        auto* versionCmd = app.add_subcommand("version", "Show version");
        versionCmd->callback([&]() {
            std::cout << "kano-backlog " << kano::backlog::GetVersion() << "\n";
            std::cout << kano::backlog::GetBuildInfo() << "\n";
        });

        if (InArgc <= 1) {
            std::cout << app.help() << std::endl;
            return 0;
        }

        app.parse(InArgc, InArgv);
    } catch (const CLI::ParseError& e) {
        return app.exit(e);
    } catch (const std::exception& e) {
        std::cerr << "Fatal error: " << e.what() << "\n";
        return 1;
    } catch (...) {
        std::cerr << "Fatal error: unknown exception\n";
        return 1;
    }
    return 0;
}
