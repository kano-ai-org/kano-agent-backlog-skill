#include "kano/backlog_ops/doctor/doctor_ops.hpp"
#include "kano/backlog_core/config/config.hpp"
#include <iostream>
#include <sstream>
#include <sqlite3.h>

namespace kano::backlog_ops {

std::vector<DoctorCheckResult> DoctorOps::run_all_checks(const std::filesystem::path& start_path) {
    std::vector<DoctorCheckResult> results;
    
    // 1. Find backlog root
    std::filesystem::path current = std::filesystem::absolute(start_path);
    std::filesystem::path backlog_root;
    while (true) {
        if (std::filesystem::exists(current / "_kano" / "backlog")) {
            backlog_root = current / "_kano" / "backlog";
            break;
        }
        if (!current.has_parent_path() || current == current.parent_path()) break;
        current = current.parent_path();
    }

    results.push_back(check_backlog_structure(backlog_root));
    results.push_back(check_backlog_initialized(backlog_root));
    results.push_back(check_sqlite_status(backlog_root));

    return results;
}

DoctorCheckResult DoctorOps::check_backlog_structure(const std::filesystem::path& root) {
    DoctorCheckResult res;
    res.name = "Backlog Structure";
    
    if (root.empty() || !std::filesystem::exists(root)) {
        res.passed = false;
        res.message = "Backlog root not found";
        res.details = "Run 'kano-backlog admin init' to initialize.";
        return res;
    }

    std::vector<std::string> missing;
    if (!std::filesystem::exists(root / "products")) missing.push_back("products");
    
    if (!missing.empty()) {
        res.passed = false;
        res.message = "Missing required directories";
        std::stringstream ss;
        ss << "Missing: ";
        for (const auto& m : missing) ss << m << " ";
        res.details = ss.str();
    } else {
        res.passed = true;
        res.message = "Backlog structure is valid";
    }
    return res;
}

DoctorCheckResult DoctorOps::check_backlog_initialized(const std::filesystem::path& root) {
    DoctorCheckResult res;
    res.name = "Backlog Initialized";
    
    if (root.empty() || !std::filesystem::exists(root)) {
        res.passed = false;
        res.message = "Cannot check initialization without root";
        return res;
    }

    auto project_root = root.parent_path().parent_path();
    auto config_path = project_root / ".kano" / "backlog_config.toml";
    
    if (!std::filesystem::exists(config_path)) {
        res.passed = false;
        res.message = "Project config not found";
        res.details = "Expected: " + config_path.string();
    } else {
        res.passed = true;
        res.message = "Project config found at " + config_path.string();
    }
    return res;
}

DoctorCheckResult DoctorOps::check_sqlite_status(const std::filesystem::path& root) {
    DoctorCheckResult res;
    res.name = "SQLite Status";
    
    res.message = "SQLite version: " + std::string(sqlite3_libversion());
    
    if (!root.empty()) {
        auto db_path = root / ".cache" / "index" / "backlog.db";
        if (std::filesystem::exists(db_path)) {
            sqlite3* db;
            if (sqlite3_open(db_path.string().c_str(), &db) == SQLITE_OK) {
                res.passed = true;
                res.details = "Database index found and accessible: " + db_path.string();
                sqlite3_close(db);
            } else {
                res.passed = false;
                res.details = "Database index found but NOT accessible: " + db_path.string();
            }
        } else {
            res.passed = true; // Informational
            res.message += " (No index DB found yet)";
            res.details = "Expected: " + db_path.string();
        }
    } else {
        res.passed = true;
    }
    
    return res;
}

} // namespace kano::backlog_ops
