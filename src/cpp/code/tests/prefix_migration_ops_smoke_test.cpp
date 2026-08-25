#include "kano/backlog_core/frontmatter/canonical_store.hpp"
#include "kano/backlog_core/process/noninteractive_errors.hpp"
#include "kano/backlog_ops/prefix_migration/prefix_migration_ops.hpp"
#include <algorithm>
#include <optional>
#include <vector>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

void expect(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

std::filesystem::path make_temp_root() {
    std::random_device source;
    std::mt19937 generator(source());
    std::uniform_int_distribution<unsigned int> distribution(0, 0xffffff);
    std::ostringstream suffix;
    suffix << std::hex << distribution(generator);
    const auto root =
        std::filesystem::temp_directory_path() /
        "kano-backlog-prefix-migration-smoke" / suffix.str();
    std::filesystem::create_directories(root / ".kano");
    return root;
}

void write_text(const std::filesystem::path& path, const std::string& content) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::binary);
    if (!output.is_open()) {
        throw std::runtime_error("failed to write " + path.string());
    }
    output << content;
}

std::string read_text(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input.is_open()) {
        throw std::runtime_error("failed to read " + path.string());
    }
    return std::string(
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>());
}

kano::backlog_core::BacklogItem create_item(
    const std::filesystem::path& product_root,
    const std::string& prefix,
    kano::backlog_core::ItemType type,
    int number,
    const std::string& title,
    const std::optional<std::string>& parent = std::nullopt
) {
    kano::backlog_core::CanonicalStore store(product_root);
    auto item = store.create(prefix, type, title, number, parent);
    item.priority = "P2";
    item.area = "fixture";
    item.iteration = "backlog";
    item.context = "Canonical fixture context.";
    item.goal = "Exercise prefix migration.";
    item.approach = "Use a disposable shared backlog.";
    item.acceptance_criteria = "Identity and references remain valid.";
    item.risks = "Disposable fixture only.";
    item.worklog.push_back(
        "2026-08-25 00:00 [agent=tester] Historical reference " + item.id);
    store.write(item);
    return item;
}

bool contains_prefix(
    const std::vector<std::string>& values,
    const std::string& prefix
) {
    return std::any_of(
        values.begin(), values.end(),
        [&](const auto& value) { return value.starts_with(prefix); });
}

} // namespace

int main() {
    kano::backlog_core::ConfigureNoninteractiveErrorHandling();
    using kano::backlog_core::CanonicalStore;
    using kano::backlog_core::ItemType;
    using kano::backlog_ops::PrefixMigrationOps;

    std::filesystem::path root;
    try {
        root = make_temp_root();
        const std::string config =
            "[products.quick-source]\n"
            "name = \"Quick source\"\n"
            "prefix = \"QS\"\n"
            "backlog_root = \"products/quick-source\"\n\n"
            "[products.parametric]\n"
            "name = \"Parametric\"\n"
            "prefix = \"NEWQSEO\"\n"
            "backlog_root = \"products/parametric\"\n\n"
            "[products.observer]\n"
            "name = \"Observer\"\n"
            "prefix = \"OBS\"\n"
            "backlog_root = \"products/observer\"\n";
        write_text(root / ".kano" / "backlog_config.toml", config);

        const auto source_root = root / "products" / "quick-source";
        const auto observer_root = root / "products" / "observer";
        std::filesystem::create_directories(
            root / "products" / "parametric" / "items");

        auto feature = create_item(
            source_root, "QS", ItemType::Feature, 1, "Prefix fixture feature");
        auto task = create_item(
            source_root, "QS", ItemType::Task, 1, "Prefix fixture task",
            feature.id);
        feature.context =
            "Canonical dependency " + task.id +
            " and missing ref QS-TSK-9999 must migrate.";
        CanonicalStore(source_root).write(feature);

        auto observer = create_item(
            observer_root, "OBS", ItemType::Task, 1, "External observer");
        observer.links.relates.push_back(task.id);
        observer.context = "Canonical external reference " + task.id + ".";
        observer.worklog.push_back(
            "2026-08-25 00:01 [agent=tester] Historical external " + task.id);
        CanonicalStore(observer_root).write(observer);

        const auto artifact =
            source_root / "artifacts" / task.id / "evidence.json";
        const std::string artifact_bytes =
            "{\"historical_owner\":\"" + task.id + "\"}\n";
        write_text(artifact, artifact_bytes);

        const auto admission =
            source_root / "_meta" / "duplicate-admission" /
            (task.id + ".json");
        const std::string admission_bytes =
            "{\"item_id\":\"" + task.id + "\",\"historical\":true}\n";
        write_text(admission, admission_bytes);

        const auto derived =
            source_root / "items" / "feature" / "0000" /
            (feature.id + "_fixture.index.md");
        write_text(
            derived,
            "# Fixture index\n\nCanonical " + feature.id +
                " links " + task.id + ".\n");
        write_text(
            source_root / "_meta" / "indexes.md",
            "- " + feature.id + " -> " + derived.filename().generic_string() +
                "\n");

        PrefixMigrationOps::PlanOptions options;
        options.start_path = root;
        options.backlog_root = root;
        options.request.product = "quick-source";
        options.request.expected_from_prefix = "QS";
        options.request.to_prefix = "NEWQS";
        options.request.max_files = 100;
        options.request.max_bytes = 4u * 1024u * 1024u;

        const auto source_feature_before = read_text(*feature.file_path);
        const auto source_task_before = read_text(*task.file_path);
        const auto observer_before = read_text(*observer.file_path);
        const auto config_before = read_text(
            root / ".kano" / "backlog_config.toml");

        const auto first = PrefixMigrationOps::plan(options);
        const auto second = PrefixMigrationOps::plan(options);
        if (!first.ready()) {
            std::cerr << first.to_json(true) << "\n";
        }
        expect(first.ready(), "fixture should produce a ready plan");
        expect(first.items.size() == 2, "planner should map both source items");
        expect(
            first.plan_hash.size() == 64 &&
                first.plan_hash == second.plan_hash,
            "identical inputs should produce one deterministic SHA-256 plan");
        expect(
            first.compatibility_policy == "no-legacy-prefix-alias",
            "pre-1.0 policy should not invent a legacy prefix alias");
        expect(
            contains_prefix(
                first.resolver_checks,
                "token_boundary_distinct:NEWQS:NEWQSEO:parametric"),
            "planner should report the longer-prefix resolver check");
        expect(
            first.to_json().find(root.generic_string()) == std::string::npos &&
                first.to_json().find(root.string()) == std::string::npos,
            "plan output should expose only backlog-relative paths");
        expect(
            read_text(*feature.file_path) == source_feature_before &&
                read_text(*task.file_path) == source_task_before &&
                read_text(*observer.file_path) == observer_before,
            "dry-run must not mutate canonical items");

        auto stale_apply = PrefixMigrationOps::ApplyOptions{
            .plan = options,
            .expected_plan_hash = first.plan_hash,
            .confirm = true,
        };
        write_text(
            *feature.file_path,
            source_feature_before + "\n<!-- concurrent drift -->\n");
        const auto stale_result = PrefixMigrationOps::apply(stale_apply);
        expect(
            stale_result.status == "blocked" &&
                contains_prefix(
                    stale_result.operation_receipts,
                    "stale_or_mismatched_plan_hash"),
            "apply should reject a stale reviewed plan hash");
        write_text(*feature.file_path, source_feature_before);

        auto unconfirmed = stale_apply;
        unconfirmed.confirm = false;
        const auto unconfirmed_result =
            PrefixMigrationOps::apply(unconfirmed);
        expect(
            unconfirmed_result.status == "blocked" &&
                contains_prefix(
                    unconfirmed_result.operation_receipts,
                    "confirmation_required"),
            "apply should require explicit confirmation");

        auto injected = stale_apply;
        injected.inject_failure_after = "after_config_publish";
        const auto injected_result = PrefixMigrationOps::apply(injected);
        expect(
            injected_result.status == "rolled_back" &&
                contains_prefix(
                    injected_result.operation_receipts,
                    "automatic_rollback_completed"),
            "a deterministic mid-apply failure should roll back automatically");
        expect(
            read_text(root / ".kano" / "backlog_config.toml") == config_before &&
                read_text(*feature.file_path) == source_feature_before &&
                read_text(*task.file_path) == source_task_before,
            "automatic rollback should restore exact pre-migration bytes");

        const auto applied = PrefixMigrationOps::apply(stale_apply);
        if (applied.status != "applied") {
            std::cerr << applied.to_json(true) << "\n";
        }
        expect(applied.status == "applied", "confirmed apply should complete");
        expect(
            std::filesystem::is_regular_file(root / applied.receipt_path),
            "apply should persist an immutable migration receipt");
        const auto replayed = PrefixMigrationOps::apply(stale_apply);
        expect(
            replayed.status == "applied" &&
                replayed.idempotent_replay &&
                replayed.receipt_path == applied.receipt_path &&
                contains_prefix(
                    replayed.operation_receipts, "postconditions_verified"),
            "an exact confirmed replay should verify and return the applied receipt");

        PrefixMigrationOps::RecoveryOptions recovery;
        recovery.backlog_root = root;
        recovery.plan_hash = first.plan_hash;
        const auto verification = PrefixMigrationOps::verify(recovery);
        if (verification.status != "verified") {
            std::cerr << verification.to_json(true) << "\n";
        }
        expect(
            verification.status == "verified",
            "post-apply verification should pass");
        const auto status = PrefixMigrationOps::status(recovery);
        expect(
            status.status == "applied" && status.rollback_supported,
            "applied transaction should expose rollback status");

        CanonicalStore migrated(source_root);
        const auto migrated_feature_path =
            migrated.find_item_path_by_id("NEWQS-FTR-0001");
        const auto migrated_task_path =
            migrated.find_item_path_by_id("NEWQS-TSK-0001");
        expect(
            migrated_feature_path && migrated_task_path,
            "migrated IDs should be readable");
        const auto migrated_feature = migrated.read(*migrated_feature_path);
        const auto migrated_task = migrated.read(*migrated_task_path);
        expect(
            migrated_feature.uid == feature.uid &&
                migrated_task.uid == task.uid,
            "migration should preserve immutable UIDs");
        expect(
            migrated_task.parent == std::optional<std::string>(
                "NEWQS-FTR-0001"),
            "migration should preserve hierarchy through rewritten refs");
        expect(
            read_text(*migrated_feature_path).find(
                "Historical reference QS-FTR-0001") != std::string::npos,
            "historical Worklog text should remain byte-preserved");
        expect(
            read_text(*migrated_feature_path).find(
                "Canonical dependency NEWQS-TSK-0001") !=
                std::string::npos,
            "canonical refs outside Worklog should migrate");
        expect(
            read_text(*migrated_feature_path).find(
                "missing ref NEWQS-TSK-9999") != std::string::npos &&
                contains_prefix(first.warnings, "missing_reference_reprefixed:"),
            "missing canonical refs should remain missing under the new prefix and be diagnosed");

        const auto migrated_observer =
            CanonicalStore(observer_root).read(*observer.file_path);
        expect(
            migrated_observer.links.relates ==
                std::vector<std::string>{"NEWQS-TSK-0001"},
            "cross-product canonical refs should migrate");
        expect(
            read_text(*observer.file_path).find(
                "Historical external QS-TSK-0001") != std::string::npos,
            "cross-product Worklog history should remain unchanged");

        const auto migrated_artifact =
            source_root / "artifacts" / "NEWQS-TSK-0001" /
            "evidence.json";
        const auto migrated_admission =
            source_root / "_meta" / "duplicate-admission" /
            "NEWQS-TSK-0001.json";
        expect(
            read_text(migrated_artifact) == artifact_bytes &&
                read_text(migrated_admission) == admission_bytes,
            "artifact and duplicate-admission payload bytes should be immutable");
        expect(
            std::filesystem::is_regular_file(
                source_root / "items" / "feature" / "0000" /
                "NEWQS-FTR-0001_fixture.index.md"),
            "derived index path should migrate");
        expect(
            migrated.get_max_id_number("NEWQS", ItemType::Task) == 1,
            "sequence allocation should derive from migrated IDs");

        recovery.confirm = true;
        const auto rolled_back = PrefixMigrationOps::rollback(recovery);
        expect(
            rolled_back.status == "rolled_back",
            "confirmed rollback should restore the pre-migration state");
        expect(
            read_text(root / ".kano" / "backlog_config.toml") == config_before &&
                read_text(*feature.file_path) == source_feature_before &&
                read_text(*task.file_path) == source_task_before &&
                read_text(*observer.file_path) == observer_before &&
                read_text(artifact) == artifact_bytes &&
                read_text(admission) == admission_bytes,
            "rollback should restore exact canonical and historical bytes");
        expect(
            !std::filesystem::exists(root / applied.receipt_path),
            "rollback should remove the migration receipt");

        const auto duplicate_path =
            source_root / "items" / "task" / "0000" /
            "QS-TSK-0001_duplicate-fixture.md";
        write_text(duplicate_path, source_task_before);
        const auto duplicate_plan = PrefixMigrationOps::plan(options);
        expect(
            !duplicate_plan.ready() &&
                contains_prefix(
                    duplicate_plan.blockers,
                    "duplicate_source_display_id:QS-TSK-0001"),
            "planner should fail closed on duplicate source display IDs");
        std::filesystem::remove(duplicate_path);

        std::filesystem::remove_all(root);
        std::cout << "prefix_migration_ops_smoke_test: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        if (!root.empty()) {
            std::filesystem::remove_all(root);
        }
        std::cerr << "prefix_migration_ops_smoke_test: FAIL: "
                  << error.what() << "\n";
        return 1;
    }
}
