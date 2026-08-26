#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "kano/backlog_core/frontmatter/canonical_store.hpp"
#include "kano/backlog_core/models/models.hpp"
#include "kano/backlog_core/process/noninteractive_errors.hpp"
#include "kano/backlog_ops/index/backlog_index.hpp"
#include "kano/backlog_ops/workitem/workitem_ops.hpp"

namespace {

using kano::backlog_core::BacklogItem;
using kano::backlog_core::CanonicalStore;
using kano::backlog_core::ItemState;
using kano::backlog_core::ItemType;
using kano::backlog_ops::BacklogIndex;
using kano::backlog_ops::IndexQuery;
using kano::backlog_ops::IndexQueryResult;
using kano::backlog_ops::WorkitemOps;

void expect(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

std::filesystem::path make_temp_root() {
    const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto root = std::filesystem::temp_directory_path() /
        ("kano-backlog-metadata-index-" + std::to_string(nonce));
    std::filesystem::create_directories(root);
    return root;
}

std::string read_text(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input.is_open()) {
        throw std::runtime_error("failed to read fixture");
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

void write_text(const std::filesystem::path& path, const std::string& value) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output.is_open()) {
        throw std::runtime_error("failed to write fixture");
    }
    output << value;
}

void set_ready_fields(BacklogItem& item) {
    item.context = "Exercise a derived metadata index mutation.";
    item.goal = "Keep canonical item metadata authoritative.";
    item.approach = "Update canonical state and publish one derived row.";
    item.acceptance_criteria = "The validated index remains current.";
    item.risks = "Fixture-only mutation.";
}

double percentile_95(std::vector<double> samples) {
    expect(!samples.empty(), "timing samples must not be empty");
    std::sort(samples.begin(), samples.end());
    const auto index = static_cast<std::size_t>(
        std::ceil(static_cast<double>(samples.size()) * 0.95)) - 1U;
    return samples[std::min(index, samples.size() - 1U)];
}

template <typename Fn>
double timed_ms(Fn&& fn) {
    const auto start = std::chrono::steady_clock::now();
    fn();
    return std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - start).count();
}

void expect_exact(
    const IndexQueryResult& result,
    const std::string& id,
    const std::string& title
) {
    expect(result.items.size() == 1, "exact metadata query must return one item");
    expect(result.items.front().id == id, "exact metadata query returned the wrong ID");
    expect(result.items.front().title == title, "exact metadata query returned a stale title");
}

std::map<std::string, std::pair<ItemState, std::string>> canonical_projection(
    const std::filesystem::path& product_root
) {
    CanonicalStore store(product_root);
    std::map<std::string, std::pair<ItemState, std::string>> result;
    for (const auto& path : store.list_items()) {
        const auto item = store.read_metadata(path);
        result.emplace(item.id, std::make_pair(item.state, item.title));
    }
    return result;
}

} // namespace

int main() {
    kano::backlog_core::ConfigureNoninteractiveErrorHandling();

    std::filesystem::path fixture_root;
    try {
        fixture_root = make_temp_root();
        const auto backlog_root = fixture_root / "backlog";
        const std::string product = "metadata-product";
        const auto product_root = backlog_root / "products" / product;
        const auto index_path = backlog_root / ".cache" / "index" / "backlog.db";
        std::filesystem::create_directories(product_root / "items");

        CanonicalStore store(product_root);
        std::vector<BacklogItem> fixtures;
        fixtures.reserve(650);
        for (int number = 1; number <= 650; ++number) {
            std::ostringstream padded;
            padded.width(4);
            padded.fill('0');
            padded << number;
            auto item = store.create(
                "MDI",
                ItemType::Task,
                "Metadata fixture " + padded.str() + " needle-" + padded.str(),
                number);
            item.priority = number % 2 == 0 ? "P1" : "P2";
            store.write(item);
            fixtures.push_back(std::move(item));
        }

        const auto target_id = fixtures.back().id;
        const auto target_uid = fixtures.back().uid;
        IndexQuery exact_query;
        exact_query.exact_ref = target_id;
        exact_query.limit = 1;

        const auto cold = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, exact_query);
        expect_exact(cold, target_id, fixtures.back().title);
        expect(!cold.diagnostics.index_used &&
                   cold.diagnostics.index_status == "missing" &&
                   cold.diagnostics.fallback_scan,
            "cold read must use an explicit canonical fallback");
        expect(cold.diagnostics.scanned_count == 650,
            "cold fallback must not silently omit canonical items");

        const auto built = kano::backlog_ops::build_index(
            product_root, index_path, true, product);
        expect(built.items_indexed == 650, "rebuild must index every canonical item");
        expect(!built.index_revision.empty() &&
                   built.index_revision == built.canonical_revision,
            "rebuild must publish one verified canonical revision");

        const auto fresh = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, exact_query);
        expect_exact(fresh, target_id, fixtures.back().title);
        expect(fresh.diagnostics.index_used &&
                   fresh.diagnostics.index_status == "ready" &&
                   !fresh.diagnostics.fallback_scan,
            "fresh read must use the validated metadata index");
        expect(fresh.diagnostics.index_revision ==
                   fresh.diagnostics.canonical_revision,
            "fresh index and canonical revisions must agree");
        expect(fresh.diagnostics.scanned_count == 1,
            "exact indexed lookup must report bounded row scan work");
        expect(fresh.items.front().uid == target_uid &&
                   fresh.items.front().product == product &&
                   fresh.items.front().estimated_tokens > 0,
            "indexed identity, product, and token metadata must remain intact");
        expect(!std::filesystem::path(fresh.items.front().source_ref).is_absolute() &&
                   fresh.items.front().source_ref.find("..") == std::string::npos &&
                   fresh.items.front().source_ref.find(fixture_root.string()) ==
                       std::string::npos,
            "metadata index must expose only bounded product-relative source refs");
        {
            BacklogIndex unscoped(index_path);
            const auto id_path = unscoped.get_path_by_id(target_id);
            const auto uid_path = unscoped.get_path_by_uid(target_uid);
            expect(id_path && uid_path &&
                       id_path->lexically_normal() ==
                           fixtures.back().file_path->lexically_normal() &&
                       uid_path->lexically_normal() ==
                           fixtures.back().file_path->lexically_normal(),
                "shared unscoped lookups must materialize the product canonical path");
        }

        IndexQuery all_query;
        const auto all_fresh = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, all_query);
        const auto canonical_fresh = canonical_projection(product_root);
        expect(all_fresh.items.size() == canonical_fresh.size(),
            "indexed list count must match canonical metadata");
        for (const auto& indexed : all_fresh.items) {
            const auto canonical = canonical_fresh.find(indexed.id);
            expect(canonical != canonical_fresh.end() &&
                       canonical->second.first == indexed.state &&
                       canonical->second.second == indexed.title,
                "indexed list state/title must match canonical metadata");
        }

        std::vector<double> exact_samples;
        std::vector<double> revision_samples;
        for (int sample = 0; sample < 30; ++sample) {
            IndexQueryResult result;
            exact_samples.push_back(timed_ms([&]() {
                result = kano::backlog_ops::query_metadata_index(
                    index_path, product_root, product, exact_query);
            }));
            expect(result.diagnostics.index_used, "exact benchmark must use the index");
            revision_samples.push_back(result.diagnostics.revision_check_ms);
        }
        const auto exact_p95_ms = percentile_95(exact_samples);
        const auto revision_p95_ms = percentile_95(revision_samples);
        expect(exact_p95_ms < 100.0,
            "650-item exact lookup p95 must remain below 100 ms (actual " +
                std::to_string(exact_p95_ms) + " ms)");
        expect(revision_p95_ms < 100.0,
            "650-item canonical revision check p95 must remain below 100 ms (actual " +
                std::to_string(revision_p95_ms) + " ms)");

        IndexQuery metadata_query;
        metadata_query.type = ItemType::Task;
        metadata_query.state = ItemState::New;
        std::vector<double> metadata_samples;
        for (int sample = 0; sample < 12; ++sample) {
            metadata_samples.push_back(timed_ms([&]() {
                const auto result = kano::backlog_ops::query_metadata_index(
                    index_path, product_root, product, metadata_query);
                expect(result.items.size() == 650,
                    "metadata filter must preserve canonical parity");
            }));
        }
        const auto metadata_p95_ms = percentile_95(metadata_samples);
        expect(metadata_p95_ms < 500.0,
            "650-item metadata query p95 must remain below 500 ms");

        IndexQuery token_query;
        token_query.text = "needle-0649";
        token_query.limit = 20;
        std::vector<double> token_samples;
        for (int sample = 0; sample < 8; ++sample) {
            token_samples.push_back(timed_ms([&]() {
                const auto result = kano::backlog_ops::query_metadata_index(
                    index_path, product_root, product, token_query);
                expect(result.items.size() == 1 &&
                           result.items.front().id == "MDI-TSK-0649",
                    "bounded token query must return the canonical match");
            }));
        }
        const auto token_p95_ms = percentile_95(token_samples);
        expect(token_p95_ms < 2000.0,
            "650-item bounded token query p95 must remain below 2 seconds");

        {
        BacklogIndex index(index_path, product, product_root);
        index.invalidate_metadata(product, "fixture_explicit_invalidation");
        const auto invalidated = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, exact_query);
        expect(!invalidated.diagnostics.index_used &&
                   invalidated.diagnostics.index_status == "stale" &&
                   invalidated.diagnostics.stale_reason &&
                   *invalidated.diagnostics.stale_reason ==
                       "fixture_explicit_invalidation",
            "explicit invalidation must fail over to canonical metadata");
        index.rebuild_metadata(product_root, product);

        auto target = store.read(*fixtures.back().file_path);
        target.title = "Canonical mutation title";
        store.write(target);
        index.index_item(target);
        const auto updated = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, exact_query);
        expect_exact(updated, target_id, target.title);
        expect(updated.diagnostics.index_used,
            "tracked canonical update must keep a healthy snapshot readable");

        index.sync_sequences(product_root);
        kano::backlog_ops::DuplicateAdmissionEvidence admission;
        admission.search_query = "Lifecycle-created metadata item";
        admission.search_scope = product;
        admission.decision = "create";
        const auto created = WorkitemOps::create_item(
            index,
            product_root,
            "MDI",
            ItemType::Task,
            "Lifecycle-created metadata item",
            "metadata-index-test",
            std::nullopt,
            "P2",
            {},
            "general",
            "backlog",
            std::nullopt,
            std::nullopt,
            "",
            "",
            admission);
        IndexQuery created_query;
        created_query.exact_ref = created.id;
        created_query.limit = 1;
        const auto created_read = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, created_query);
        expect_exact(created_read, created.id, "Lifecycle-created metadata item");
        expect(created_read.diagnostics.index_used,
            "newly created item must be published to a healthy index");

        auto parent_feature = store.create(
            "MDI", ItemType::Feature, "Metadata lifecycle parent", 1);
        store.write(parent_feature);
        index.index_item(parent_feature);
        WorkitemOps::remap_parent(
            index, product_root, created.id, parent_feature.id, "metadata-index-test");
        const auto reparented = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, created_query);
        expect(reparented.items.front().parent &&
                   *reparented.items.front().parent == parent_feature.id,
            "reparent mutation must update indexed parent metadata");

        auto created_item = store.read(
            *store.find_item_path_by_id(created.id));
        set_ready_fields(created_item);
        created_item.state = ItemState::Ready;
        store.write(created_item);
        index.index_item(created_item);
        const auto started = WorkitemOps::transition_state_action(
            product_root,
            created.id,
            kano::backlog_core::StateAction::Start,
            std::string("metadata-index-test"),
            std::string("Exercise indexed state transition"),
            std::nullopt,
            &index);
        expect(started.state == ItemState::InProgress,
            "state transition fixture must start");
        const auto started_read = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, created_query);
        expect(started_read.diagnostics.index_used &&
                   started_read.items.front().state == ItemState::InProgress,
            "state transition must publish current indexed state");

        (void)WorkitemOps::add_decision_writeback(
            index,
            product_root,
            created.id,
            "Keep canonical metadata authoritative.",
            "metadata-index-test",
            std::string("fixture"));
        expect(kano::backlog_ops::query_metadata_index(
                   index_path, product_root, product, created_query)
                   .diagnostics.index_used,
            "decision writeback must preserve a healthy derived snapshot");

        const auto removed_id = fixtures[10].id;
        std::filesystem::remove(*fixtures[10].file_path);
        index.remove_item(removed_id);
        const auto after_tracked_delete = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, all_query);
        expect(after_tracked_delete.diagnostics.index_used &&
                   after_tracked_delete.items.size() == 651,
            "tracked deletion must remove one row without invalidating current data");

        target = store.read(*target.file_path);
        target.title = "Canonical out-of-band title";
        store.write(target);
        const auto stale = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, exact_query);
        expect_exact(stale, target_id, target.title);
        expect(!stale.diagnostics.index_used &&
                   stale.diagnostics.index_status == "stale" &&
                   stale.diagnostics.fallback_scan,
            "out-of-band canonical change must use canonical fallback");
        index.rebuild_metadata(product_root, product);

        std::filesystem::remove(*fixtures[11].file_path);
        const auto after_untracked_delete = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, all_query);
        expect(!after_untracked_delete.diagnostics.index_used &&
                   after_untracked_delete.diagnostics.index_status == "stale" &&
                   after_untracked_delete.items.size() == 650,
            "untracked deletion must not leave an orphaned row authoritative");
        index.rebuild_metadata(product_root, product);

        target = store.read(*target.file_path);
        target.title = "Canonical source hash marker A";
        store.write(target);
        index.index_item(target);
        const auto original_time = std::filesystem::last_write_time(*target.file_path);
        auto raw = read_text(*target.file_path);
        const auto marker = raw.find("Canonical source hash marker A");
        expect(marker != std::string::npos, "source hash marker must be serialized");
        raw.replace(
            marker,
            std::string("Canonical source hash marker A").size(),
            "Canonical source hash marker B");
        write_text(*target.file_path, raw);
        std::filesystem::last_write_time(*target.file_path, original_time);
        const auto hash_fallback = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, exact_query);
        expect_exact(
            hash_fallback, target_id, "Canonical source hash marker B");
        expect(!hash_fallback.diagnostics.index_used &&
                   hash_fallback.diagnostics.index_status == "stale" &&
                   hash_fallback.diagnostics.stale_reason &&
                   *hash_fallback.diagnostics.stale_reason ==
                       "canonical_source_hash_changed",
            "exact lookup must reject same-size/mtime canonical content drift");
        const auto hash_doctor = index.doctor_metadata(product_root, product, true);
        expect(!hash_doctor.healthy &&
                   hash_doctor.source_hash_mismatches == 1 &&
                   hash_doctor.diagnostics.stale_reason,
            "deep doctor must detect content drift hidden from cheap inventory metadata");
        index.rebuild_metadata(product_root, product);

        const auto incomplete_path =
            backlog_root / ".cache" / "index" / "incomplete.db";
        {
            BacklogIndex incomplete(incomplete_path, product, product_root);
            incomplete.initialize();
        }
        const auto incomplete = kano::backlog_ops::query_metadata_index(
            incomplete_path, product_root, product, exact_query);
        expect(!incomplete.diagnostics.index_used &&
                   incomplete.diagnostics.index_status == "missing" &&
                   incomplete.diagnostics.fallback_scan,
            "incomplete snapshot must fall back to canonical metadata");

        const auto corrupt_path =
            backlog_root / ".cache" / "index" / "corrupt.db";
        write_text(corrupt_path, "not-a-sqlite-index");
        const auto corrupt = kano::backlog_ops::query_metadata_index(
            corrupt_path, product_root, product, all_query);
        expect(!corrupt.diagnostics.index_used &&
                   corrupt.diagnostics.index_status == "corrupt" &&
                   corrupt.diagnostics.fallback_scan &&
                   corrupt.items.size() == 650,
            "corrupt index must fall back without omitting canonical items");

        const std::string second_product = "metadata-product-two";
        const auto second_root = backlog_root / "products" / second_product;
        CanonicalStore second_store(second_root);
        auto second_item = second_store.create(
            "MDT", ItemType::Task, "Second product isolated item", 1);
        second_store.write(second_item);
        const auto second_build = kano::backlog_ops::build_index(
            second_root, index_path, true, second_product);
        expect(second_build.items_indexed == 1,
            "second product rebuild must remain product-scoped");
        IndexQuery second_exact;
        second_exact.exact_ref = second_item.id;
        second_exact.limit = 1;
        const auto second_result = kano::backlog_ops::query_metadata_index(
            index_path, second_root, second_product, second_exact);
        expect_exact(second_result, second_item.id, second_item.title);
        const auto first_result = kano::backlog_ops::query_metadata_index(
            index_path, product_root, product, exact_query);
        expect(first_result.diagnostics.index_used &&
                   first_result.items.front().product == product,
            "shared index database must preserve product isolation");

        const auto status = kano::backlog_ops::get_index_status(
            backlog_root, product, product_root);
        expect(status.indexes.size() == 1 &&
                   status.indexes.front().status == "ready" &&
                   status.indexes.front().index_ref ==
                       "product-cache/index/backlog.db",
            "status must expose a bounded ready snapshot reference");
        }

        std::cout << "metadata_index_smoke_test: PASS"
                  << " exact_p95_ms=" << exact_p95_ms
                  << " metadata_p95_ms=" << metadata_p95_ms
                  << " token_p95_ms=" << token_p95_ms
                  << " revision_p95_ms=" << revision_p95_ms
                  << "\n";
        std::filesystem::remove_all(fixture_root);
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "metadata_index_smoke_test: FAIL: " << ex.what() << "\n";
        if (!fixture_root.empty()) {
            std::error_code cleanup_error;
            std::filesystem::remove_all(fixture_root, cleanup_error);
        }
        return 1;
    }
}
