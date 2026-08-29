#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace kano::backlog_ops {

inline constexpr const char* kPrefixMigrationPlanSchema = "kob.product_prefix_migration.plan.v2";
inline constexpr const char* kPrefixMigrationResultSchema = "kob.product_prefix_migration.result.v3";
inline constexpr const char* kPrefixMigrationVerificationSchema = "kob.product_prefix_migration.verification.v3";
inline constexpr const char* kPrefixMigrationStatusSchema = "kob.product_prefix_migration.status.v3";
inline constexpr const char* kPrefixMigrationRollbackSchema = "kob.product_prefix_migration.rollback.v3";
inline constexpr std::size_t kDefaultPrefixMigrationMaxFiles = 500000;
inline constexpr std::uintmax_t kDefaultPrefixMigrationMaxBytes = 16ull * 1024ull * 1024ull * 1024ull;

struct PrefixMigrationRequest {
    std::string product;
    std::optional<std::string> expected_from_prefix;
    std::string to_prefix;
    std::size_t max_files = kDefaultPrefixMigrationMaxFiles;
    std::uintmax_t max_bytes = kDefaultPrefixMigrationMaxBytes;
};

struct PrefixMigrationItemMapping {
    std::string source_id;
    std::string target_id;
    std::string uid;
    std::string source_path;
    std::string target_path;
};

struct PrefixMigrationFileChange {
    std::string action;
    std::string kind;
    std::string source_path;
    std::string target_path;
    bool rewrites_canonical_refs = false;
    bool preserves_file_bytes = false;
};

struct PrefixMigrationPlan {
    std::string schema = kPrefixMigrationPlanSchema;
    std::string status = "blocked";
    PrefixMigrationRequest request;
    std::string product;
    std::string from_prefix;
    std::string to_prefix;
    std::string source_revision;
    std::string config_path;
    std::string compatibility_policy = "no-legacy-prefix-alias";
    std::vector<PrefixMigrationItemMapping> items;
    std::vector<PrefixMigrationFileChange> files;
    std::vector<std::string> resolver_checks;
    std::vector<std::string> preserved_historical_surfaces;
    std::vector<std::string> required_external_updates;
    std::vector<std::string> blockers;
    std::vector<std::string> warnings;
    std::string plan_hash;
    bool dry_run = true;
    bool mutates_backlog = false;

    [[nodiscard]] bool ready() const;
    [[nodiscard]] std::string to_json(bool pretty = false) const;
};

struct PrefixMigrationResult {
    std::string schema = kPrefixMigrationResultSchema;
    std::string status;
    std::string plan_hash;
    std::vector<std::string> changed_paths;
    std::vector<std::string> operation_receipts;
    std::string receipt_path;
    std::string recovery_status;
    std::optional<std::string> apply_agent;
    std::optional<std::string> rollback_agent;
    std::optional<std::string> rollback_mode;
    std::optional<std::string> rollback_attempted_at;
    std::optional<std::string> rolled_back_at;
    bool idempotent_replay = false;

    [[nodiscard]] std::string to_json(bool pretty = false) const;
};

struct PrefixMigrationVerification {
    std::string schema = kPrefixMigrationVerificationSchema;
    std::string status;
    std::string plan_hash;
    std::vector<std::string> postconditions;
    std::vector<std::string> failures;
    std::optional<std::string> apply_agent;

    [[nodiscard]] std::string to_json(bool pretty = false) const;
};

struct PrefixMigrationStatus {
    std::string schema = kPrefixMigrationStatusSchema;
    std::string status;
    std::string plan_hash;
    std::string recovery_status;
    std::optional<std::string> apply_agent;
    std::optional<std::string> rollback_agent;
    std::optional<std::string> rollback_mode;
    std::optional<std::string> rollback_attempted_at;
    std::optional<std::string> rolled_back_at;
    bool rollback_supported = false;

    [[nodiscard]] std::string to_json(bool pretty = false) const;
};

struct PrefixMigrationRollback {
    std::string schema = kPrefixMigrationRollbackSchema;
    std::string status;
    std::string plan_hash;
    std::vector<std::string> restored_paths;
    std::vector<std::string> failures;
    std::optional<std::string> apply_agent;
    std::optional<std::string> rollback_agent;
    std::optional<std::string> rollback_mode;
    std::optional<std::string> rollback_attempted_at;
    std::optional<std::string> rolled_back_at;

    [[nodiscard]] std::string to_json(bool pretty = false) const;
};

class PrefixMigrationOps {
public:
    struct PlanOptions {
        std::filesystem::path start_path = ".";
        std::optional<std::filesystem::path> backlog_root;
        PrefixMigrationRequest request;
    };

    struct ApplyOptions {
        PlanOptions plan;
        std::string expected_plan_hash;
        std::optional<std::string> agent;
        bool confirm = false;

        // Test-only deterministic failure injection; never exposed by CLI/env.
        std::optional<std::string> inject_failure_after;
        std::optional<std::size_t> inject_rollback_failure_after;
        std::optional<std::string> inject_automatic_recovery_failure;
    };

    struct RecoveryOptions {
        std::filesystem::path start_path = ".";
        std::optional<std::filesystem::path> backlog_root;
        std::string plan_hash;
        std::optional<std::string> agent;
        bool confirm = false;

        // Test-only deterministic failure injection; never exposed by the CLI.
        std::optional<std::size_t> inject_rollback_failure_after;
    };

    static PrefixMigrationPlan plan(const PlanOptions& options);
    static PrefixMigrationResult apply(const ApplyOptions& options);
    static PrefixMigrationVerification verify(const RecoveryOptions& options);
    static PrefixMigrationStatus status(const RecoveryOptions& options);
    static PrefixMigrationRollback rollback(const RecoveryOptions& options);
};

} // namespace kano::backlog_ops
