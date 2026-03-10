#include "KanoBacklog.BacklogWebviewService.hpp"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <optional>
#include <regex>
#include <set>
#include <sstream>

import KanoBacklogWebview.Strings;

namespace kano::backlog::webview {

namespace {

std::string Trim(const std::string& value) {
  const auto first = value.find_first_not_of(" \t\r\n");
  if (first == std::string::npos) {
    return "";
  }
  const auto last = value.find_last_not_of(" \t\r\n");
  return value.substr(first, last - first + 1);
}

std::string Unquote(const std::string& value) {
  const auto trimmed = Trim(value);
  if (trimmed.size() >= 2) {
    const char first = trimmed.front();
    const char last = trimmed.back();
    if ((first == '"' && last == '"') || (first == '\'' && last == '\'')) {
      return trimmed.substr(1, trimmed.size() - 2);
    }
  }
  return trimmed;
}

std::string NormalizeNullToken(std::string value) {
  const auto lowered = text::ToLower(Trim(value));
  if (lowered == "null" || lowered == "none" || lowered == "~") {
    return "";
  }
  return value;
}

std::vector<std::string> SplitLines(const std::string& text) {
  std::vector<std::string> lines;
  std::stringstream stream(text);
  std::string line;
  while (std::getline(stream, line)) {
    lines.push_back(line);
  }
  return lines;
}

std::string ReadTextFile(const std::filesystem::path& path, bool& ok,
                         std::string& error) {
  ok = false;
  error.clear();
  std::ifstream input(path);
  if (!input.is_open()) {
    error = "Failed to open file";
    return "";
  }
  std::stringstream buffer;
  buffer << input.rdbuf();
  ok = true;
  return buffer.str();
}

bool StartsWith(const std::string& value, const std::string& prefix) {
  return value.rfind(prefix, 0) == 0;
}

}  // namespace

BacklogWebviewService::BacklogWebviewService(std::filesystem::path productsRootPath)
    : productsRoot(std::move(productsRootPath)) {}

std::filesystem::path BacklogWebviewService::GetProductsRoot() const {
  return productsRoot;
}

bool BacklogWebviewService::IsValidProductName(const std::string& product) const {
  static const std::regex productRegex("^[A-Za-z0-9._-]+$");
  return std::regex_match(product, productRegex);
}

std::filesystem::path BacklogWebviewService::ProductRoot(
    const std::string& product) const {
  return productsRoot / product;
}

std::filesystem::path BacklogWebviewService::ResolveProductsPathFromInput(
    const std::filesystem::path& inputPath) {
  if (inputPath.empty()) {
    return {};
  }

  const auto directProducts = inputPath / "products";
  if (std::filesystem::exists(directProducts) &&
      std::filesystem::is_directory(directProducts)) {
    return directProducts;
  }

  if (inputPath.filename() == "products" && std::filesystem::exists(inputPath) &&
      std::filesystem::is_directory(inputPath)) {
    return inputPath;
  }

  const auto nestedProducts = inputPath / "_kano" / "backlog" / "products";
  if (std::filesystem::exists(nestedProducts) &&
      std::filesystem::is_directory(nestedProducts)) {
    return nestedProducts;
  }

  return {};
}

std::filesystem::file_time_type BacklogWebviewService::ScanLatestMtime(
    const std::filesystem::path& productRoot) const {
  auto latest = std::filesystem::file_time_type::min();
  const auto backlogRoot = productsRoot.parent_path();
  const std::vector<std::filesystem::path> roots = {
      productRoot / "items", productRoot / "decisions", backlogRoot / "topics",
      backlogRoot / "worksets"};

  for (const auto& root : roots) {
    if (!std::filesystem::exists(root)) {
      continue;
    }
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
      if (!entry.is_regular_file()) {
        continue;
      }
      const auto path = entry.path();
      const auto name = path.filename().string();
      const bool tracked = IsMarkdownItemFile(path) || name == "manifest.json";
      if (!tracked) {
        continue;
      }
      if (ShouldSkipPath(path)) {
        continue;
      }
      const auto mtime = entry.last_write_time();
      if (mtime > latest) {
        latest = mtime;
      }
    }
  }
  return latest;
}

bool BacklogWebviewService::ShouldLoad(const std::string& product,
                                       bool forceRefresh) {
  if (forceRefresh) {
    return true;
  }
  const auto it = cacheByProduct.find(product);
  if (it == cacheByProduct.end()) {
    return true;
  }

  const auto latest = ScanLatestMtime(ProductRoot(product));
  return latest > it->second.latestMtime;
}

bool BacklogWebviewService::IsMarkdownItemFile(const std::filesystem::path& path) {
  return path.extension() == ".md";
}

bool BacklogWebviewService::ShouldSkipPath(const std::filesystem::path& path) {
  const auto filename = path.filename().string();
  if (filename == "README.md") {
    return true;
  }
  if (filename.size() >= 9 &&
      filename.substr(filename.size() - 9) == ".index.md") {
    return true;
  }

  for (const auto& part : path) {
    if (part.string() == "_trash") {
      return true;
    }
  }

  return false;
}

std::string BacklogWebviewService::NormalizeTypeFromPath(
    const std::filesystem::path& itemPath, const std::string& declaredType) {
  if (!declaredType.empty()) {
    return declaredType;
  }

  const auto parent = itemPath.parent_path().parent_path().filename().string();
  if (parent == "story" || parent == "userstory") {
    return "UserStory";
  }
  if (parent == "epic") {
    return "Epic";
  }
  if (parent == "feature") {
    return "Feature";
  }
  if (parent == "task") {
    return "Task";
  }
  if (parent == "bug") {
    return "Bug";
  }
  return "Unknown";
}

std::unordered_map<std::string, std::string>
BacklogWebviewService::ParseFrontmatterMap(const std::string& content, bool& ok,
                                           std::string& error) {
  std::unordered_map<std::string, std::string> result;
  ok = false;
  error.clear();

  const auto lines = SplitLines(content);
  if (lines.empty() || Trim(lines.front()) != "---") {
    error = "Missing frontmatter start marker";
    return result;
  }

  bool foundEnd = false;
  std::string currentKey;
  for (size_t i = 1; i < lines.size(); ++i) {
    const auto raw = lines[i];
    const auto trimmed = Trim(raw);
    if (trimmed == "---") {
      foundEnd = true;
      break;
    }
    if (trimmed.empty()) {
      continue;
    }

    const auto keyPos = raw.find(':');
    const bool likelyKeyLine = keyPos != std::string::npos &&
                               !raw.empty() && raw[0] != ' ' && raw[0] != '\t';
    if (likelyKeyLine) {
      currentKey = Trim(raw.substr(0, keyPos));
      auto value = Trim(raw.substr(keyPos + 1));
      result[currentKey] = NormalizeNullToken(Unquote(value));
      continue;
    }

    if (!currentKey.empty() && (StartsWith(raw, "  -") || StartsWith(raw, "- "))) {
      auto itemValue = Trim(raw);
      if (StartsWith(itemValue, "- ")) {
        itemValue = Trim(itemValue.substr(2));
      } else if (StartsWith(itemValue, "-")) {
        itemValue = Trim(itemValue.substr(1));
      } else if (StartsWith(itemValue, "  -")) {
        itemValue = Trim(itemValue.substr(3));
      }
      if (!itemValue.empty()) {
        if (!result[currentKey].empty()) {
          result[currentKey] += ",";
        }
        result[currentKey] += NormalizeNullToken(Unquote(itemValue));
      }
    }
  }

  if (!foundEnd) {
    error = "Missing frontmatter end marker";
    return result;
  }

  ok = true;
  return result;
}

ItemRecord BacklogWebviewService::ParseItem(const std::filesystem::path& itemPath,
                                            const std::filesystem::path& productRoot) {
  ItemRecord item;
  item.valid = false;
  item.sourceKind = "Item";
  item.relativePath =
      std::filesystem::relative(itemPath, productRoot).generic_string();

  bool fileOk = false;
  std::string readError;
  const auto content = ReadTextFile(itemPath, fileOk, readError);
  if (!fileOk) {
    item.parseError = readError;
    return item;
  }
  item.rawContent = content;

  bool ok = false;
  std::string error;
  auto map = ParseFrontmatterMap(content, ok, error);
  if (!ok) {
    item.parseError = error;
    return item;
  }

  item.id = map["id"];
  item.type = NormalizeTypeFromPath(itemPath, map["type"]);
  item.title = map["title"];
  item.state = map["state"];
  item.parent = map["parent"];
  item.created = map["created"];
  item.updated = map["updated"];

  if (item.id.empty()) {
    item.parseError = "Missing id";
    return item;
  }

  if (text::ToLower(item.id) == "null") {
    item.parseError = "Invalid id";
    return item;
  }

  if (item.title.empty()) {
    item.title = "(untitled)";
  }

  if (item.state.empty()) {
    item.state = "Proposed";
  }

  item.valid = true;
  return item;
}

ItemRecord BacklogWebviewService::ParseDecision(
    const std::filesystem::path& decisionPath,
    const std::filesystem::path& productRoot) {
  ItemRecord item;
  item.valid = false;
  item.sourceKind = "Decision";
  item.type = "ADR";
  item.relativePath =
      std::filesystem::relative(decisionPath, productRoot).generic_string();

  bool fileOk = false;
  std::string readError;
  const auto content = ReadTextFile(decisionPath, fileOk, readError);
  if (!fileOk) {
    item.parseError = readError;
    return item;
  }
  item.rawContent = content;

  bool ok = false;
  std::string error;
  auto map = ParseFrontmatterMap(content, ok, error);
  if (!ok) {
    item.parseError = error;
    return item;
  }

  item.id = map["id"];
  if (item.id.empty()) {
    item.id = decisionPath.stem().string();
  }
  item.title = map["title"];
  if (item.title.empty()) {
    item.title = decisionPath.stem().string();
  }
  item.state = map["status"];
  if (item.state.empty()) {
    item.state = "Proposed";
  }
  item.created = map["date"];
  item.updated = map["date"];
  item.valid = true;
  return item;
}

Json::Value BacklogWebviewService::ParseJsonFile(const std::filesystem::path& jsonPath,
                                                 bool& ok,
                                                 std::string& error) {
  ok = false;
  error.clear();
  bool readOk = false;
  std::string readError;
  const auto text = ReadTextFile(jsonPath, readOk, readError);
  if (!readOk) {
    error = readError;
    return Json::Value(Json::nullValue);
  }

  Json::CharReaderBuilder builder;
  std::string parseErrors;
  std::istringstream input(text);
  Json::Value root;
  if (!Json::parseFromStream(builder, input, &root, &parseErrors)) {
    error = parseErrors;
    return Json::Value(Json::nullValue);
  }
  ok = true;
  return root;
}

ItemRecord BacklogWebviewService::ParseTopicManifest(
    const std::filesystem::path& topicManifestPath,
    const std::filesystem::path& backlogRoot) {
  ItemRecord item;
  item.valid = false;
  item.sourceKind = "Topic";
  item.type = "Topic";
  item.relativePath =
      std::filesystem::relative(topicManifestPath, backlogRoot).generic_string();

  bool ok = false;
  std::string error;
  const auto manifest = ParseJsonFile(topicManifestPath, ok, error);
  if (!ok) {
    item.parseError = error;
    return item;
  }

  const auto slug = manifest.get("topic", topicManifestPath.parent_path().filename().string())
                        .asString();
  item.id = "TOPIC-" + slug;
  item.title = slug;
  item.state = manifest.get("status", "open").asString();
  item.created = manifest.get("created_at", "").asString();
  item.updated = manifest.get("updated_at", "").asString();

  bool readOk = false;
  std::string readError;
  const auto briefPath = topicManifestPath.parent_path() / "brief.md";
  if (std::filesystem::exists(briefPath)) {
    item.rawContent = ReadTextFile(briefPath, readOk, readError);
  }
  if (!readOk) {
    item.rawContent = ReadTextFile(topicManifestPath, readOk, readError);
  }
  item.valid = true;
  return item;
}

ItemRecord BacklogWebviewService::ParseWorksetManifest(
    const std::filesystem::path& worksetManifestPath,
    const std::filesystem::path& backlogRoot) {
  ItemRecord item;
  item.valid = false;
  item.sourceKind = "Workset";
  item.type = "Workset";
  item.relativePath =
      std::filesystem::relative(worksetManifestPath, backlogRoot).generic_string();

  bool ok = false;
  std::string error;
  const auto manifest = ParseJsonFile(worksetManifestPath, ok, error);
  if (!ok) {
    item.parseError = error;
    return item;
  }

  const auto name = manifest.get("name", worksetManifestPath.parent_path().filename().string())
                        .asString();
  item.id = "WORKSET-" + name;
  item.title = name;
  item.state = manifest.get("status", "open").asString();
  item.created = manifest.get("created_at", "").asString();
  item.updated = manifest.get("updated_at", "").asString();

  bool readOk = false;
  std::string readError;
  item.rawContent = ReadTextFile(worksetManifestPath, readOk, readError);
  item.valid = true;
  return item;
}

Json::Value BacklogWebviewService::ItemToJson(const ItemRecord& item,
                                              const bool includeContent) {
  Json::Value value(Json::objectValue);
  value["id"] = item.id;
  value["type"] = item.type;
  value["source_kind"] = item.sourceKind;
  value["title"] = item.title;
  value["state"] = item.state;
  value["parent"] = item.parent;
  value["created"] = item.created;
  value["updated"] = item.updated;
  value["path"] = item.relativePath;
  value["valid"] = item.valid;
  if (!item.parseError.empty()) {
    value["parse_error"] = item.parseError;
  }
  if (includeContent) {
    value["content"] = item.rawContent;
  }
  return value;
}

std::string BacklogWebviewService::ToIsoString(
    const std::filesystem::file_time_type& value) {
  if (value == std::filesystem::file_time_type::min()) {
    return "";
  }
  const auto nowFile = std::filesystem::file_time_type::clock::now();
  const auto nowSys = std::chrono::system_clock::now();
  const auto converted = nowSys + (value - nowFile);
  const std::time_t time = std::chrono::system_clock::to_time_t(converted);
  std::tm tm{};
#if defined(_WIN32)
  gmtime_s(&tm, &time);
#else
  gmtime_r(&time, &tm);
#endif
  char buffer[32] = {0};
  std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &tm);
  return buffer;
}

void BacklogWebviewService::LoadProduct(const std::string& product,
                                        bool forceRefresh) {
  if (!ShouldLoad(product, forceRefresh)) {
    return;
  }

  ProductCache productCache;
  const auto productRoot = ProductRoot(product);
  const auto itemsRoot = productRoot / "items";
  productCache.latestMtime = ScanLatestMtime(productRoot);

  if (!std::filesystem::exists(itemsRoot)) {
    productCache.warnings.push_back("Missing items directory");
    cacheByProduct[product] = std::move(productCache);
    return;
  }

  for (const auto& entry : std::filesystem::recursive_directory_iterator(itemsRoot)) {
    if (!entry.is_regular_file()) {
      continue;
    }
    if (!IsMarkdownItemFile(entry.path()) || ShouldSkipPath(entry.path())) {
      continue;
    }

    auto item = ParseItem(entry.path(), productRoot);
    const auto index = productCache.allItems.size();
    if (!item.valid) {
      productCache.warnings.push_back("Invalid item: " + item.relativePath +
                                      " - " + item.parseError);
    }
    productCache.allItems.push_back(std::move(item));
  }

  const auto decisionsRoot = productRoot / "decisions";
  if (std::filesystem::exists(decisionsRoot)) {
    for (const auto& entry : std::filesystem::recursive_directory_iterator(decisionsRoot)) {
      if (!entry.is_regular_file()) {
        continue;
      }
      if (!IsMarkdownItemFile(entry.path()) || ShouldSkipPath(entry.path())) {
        continue;
      }
      auto item = ParseDecision(entry.path(), productRoot);
      if (!item.valid) {
        productCache.warnings.push_back("Invalid decision: " + item.relativePath +
                                        " - " + item.parseError);
      }
      productCache.allItems.push_back(std::move(item));
    }
  }

  const auto backlogRoot = productsRoot.parent_path();
  const auto topicsRoot = backlogRoot / "topics";
  if (std::filesystem::exists(topicsRoot)) {
    for (const auto& entry : std::filesystem::directory_iterator(topicsRoot)) {
      if (!entry.is_directory()) {
        continue;
      }
      const auto manifestPath = entry.path() / "manifest.json";
      if (!std::filesystem::exists(manifestPath)) {
        continue;
      }
      auto item = ParseTopicManifest(manifestPath, backlogRoot);
      if (!item.valid) {
        productCache.warnings.push_back("Invalid topic: " + item.relativePath +
                                        " - " + item.parseError);
      }
      productCache.allItems.push_back(std::move(item));
    }
  }

  const auto worksetsRoot = backlogRoot / "worksets";
  if (std::filesystem::exists(worksetsRoot)) {
    for (const auto& entry : std::filesystem::directory_iterator(worksetsRoot)) {
      if (!entry.is_directory()) {
        continue;
      }
      const auto manifestPath = entry.path() / "manifest.json";
      if (!std::filesystem::exists(manifestPath)) {
        continue;
      }
      auto item = ParseWorksetManifest(manifestPath, backlogRoot);
      if (!item.valid) {
        productCache.warnings.push_back("Invalid workset: " + item.relativePath +
                                        " - " + item.parseError);
      }
      productCache.allItems.push_back(std::move(item));
    }
  }

  for (size_t i = 0; i < productCache.allItems.size(); ++i) {
    const auto& item = productCache.allItems[i];
    if (!item.id.empty()) {
      productCache.idIndexes[item.id].push_back(i);
    }
  }

  for (const auto& [id, indexes] : productCache.idIndexes) {
    if (indexes.empty()) {
      continue;
    }
    auto primary = indexes.front();
    for (const auto index : indexes) {
      const auto& candidate = productCache.allItems[index];
      const auto& current = productCache.allItems[primary];
      if (candidate.updated > current.updated) {
        primary = index;
      }
      if (candidate.updated == current.updated && candidate.relativePath < current.relativePath) {
        primary = index;
      }
    }
    productCache.primaryById[id] = primary;
  }

  cacheByProduct[product] = std::move(productCache);
}

Json::Value BacklogWebviewService::ListProducts() {
  Json::Value data(Json::arrayValue);
  if (!std::filesystem::exists(productsRoot)) {
    return data;
  }

  std::vector<std::string> products;
  for (const auto& entry : std::filesystem::directory_iterator(productsRoot)) {
    if (!entry.is_directory()) {
      continue;
    }
    const auto candidate = entry.path() / "items";
    if (std::filesystem::exists(candidate) && std::filesystem::is_directory(candidate)) {
      products.push_back(entry.path().filename().string());
    }
  }
  std::sort(products.begin(), products.end());
  for (const auto& product : products) {
    data.append(product);
  }
  return data;
}

Json::Value BacklogWebviewService::ListItems(const std::string& product,
                                             bool forceRefresh) {
  Json::Value response(Json::objectValue);
  response["items"] = Json::arrayValue;
  response["warnings"] = Json::arrayValue;
  if (!IsValidProductName(product)) {
    response["error"] = "Invalid product name";
    return response;
  }

  LoadProduct(product, forceRefresh);
  const auto cacheIt = cacheByProduct.find(product);
  if (cacheIt == cacheByProduct.end()) {
    response["error"] = "Product not found";
    return response;
  }

  const auto& productCache = cacheIt->second;
  for (const auto& warning : productCache.warnings) {
    response["warnings"].append(warning);
  }

  for (const auto& [id, primaryIndex] : productCache.primaryById) {
    const auto& item = productCache.allItems[primaryIndex];
    auto value = ItemToJson(item);
    const auto duplicateIt = productCache.idIndexes.find(id);
    if (duplicateIt != productCache.idIndexes.end()) {
      value["duplicate_count"] =
          static_cast<Json::UInt64>(duplicateIt->second.size());
    }
    response["items"].append(value);
  }

  response["cached_at"] = ToIsoString(productCache.latestMtime);
  return response;
}

Json::Value BacklogWebviewService::GetItem(const std::string& product,
                                           const std::string& id,
                                           bool forceRefresh) {
  Json::Value response(Json::objectValue);
  if (!IsValidProductName(product)) {
    response["error"] = "Invalid product name";
    return response;
  }

  LoadProduct(product, forceRefresh);
  const auto cacheIt = cacheByProduct.find(product);
  if (cacheIt == cacheByProduct.end()) {
    response["error"] = "Product not found";
    return response;
  }

  const auto& productCache = cacheIt->second;
  const auto primaryIt = productCache.primaryById.find(id);
  if (primaryIt == productCache.primaryById.end()) {
    response["error"] = "Item not found";
    return response;
  }

  response["item"] = ItemToJson(productCache.allItems[primaryIt->second], true);
  response["duplicates"] = Json::arrayValue;
  const auto allIt = productCache.idIndexes.find(id);
  if (allIt != productCache.idIndexes.end()) {
    for (const auto index : allIt->second) {
      response["duplicates"].append(ItemToJson(productCache.allItems[index]));
    }
  }
  return response;
}

Json::Value BacklogWebviewService::BuildTree(const std::string& product,
                                             bool forceRefresh) {
  Json::Value response(Json::objectValue);
  response["roots"] = Json::arrayValue;
  response["warnings"] = Json::arrayValue;

  auto itemsResponse = ListItems(product, forceRefresh);
  if (itemsResponse.isMember("error")) {
    response["error"] = itemsResponse["error"];
    return response;
  }

  std::unordered_map<std::string, Json::Value> byId;
  std::unordered_map<std::string, std::vector<std::string>> childIds;
  std::set<std::string> allIds;

  for (const auto& item : itemsResponse["items"]) {
    const auto type = item["type"].asString();
    if (type != "Epic" && type != "Feature" && type != "UserStory" &&
        type != "Task" && type != "Bug" && type != "Theme") {
      continue;
    }
    const auto id = item["id"].asString();
    if (id.empty()) {
      continue;
    }
    allIds.insert(id);
    Json::Value node(Json::objectValue);
    node["id"] = id;
    node["title"] = item["title"].asString();
    node["type"] = item["type"].asString();
    node["state"] = item["state"].asString();
    node["parent"] = item["parent"].asString();
    node["children"] = Json::arrayValue;
    byId[id] = node;
  }

  for (const auto& item : itemsResponse["items"]) {
    const auto type = item["type"].asString();
    if (type != "Epic" && type != "Feature" && type != "UserStory" &&
        type != "Task" && type != "Bug" && type != "Theme") {
      continue;
    }
    const auto id = item["id"].asString();
    if (id.empty()) {
      continue;
    }
    const auto parent = item["parent"].asString();
    if (!parent.empty()) {
      childIds[parent].push_back(id);
      if (!allIds.count(parent)) {
        response["warnings"].append("Orphan parent missing for item " + id +
                                     ": " + parent);
      }
    }
  }

  std::set<std::string> visiting;
  std::set<std::string> visited;
  std::function<void(Json::Value&, const std::string&)> attachChildren;
  attachChildren = [&](Json::Value& node, const std::string& nodeId) {
    visiting.insert(nodeId);
    visited.insert(nodeId);

    for (const auto& childId : childIds[nodeId]) {
      if (!byId.count(childId)) {
        continue;
      }
      if (visiting.count(childId)) {
        response["warnings"].append("Cycle detected at " + childId);
        continue;
      }
      auto child = byId[childId];
      attachChildren(child, childId);
      node["children"].append(child);
    }

    visiting.erase(nodeId);
  };

  for (const auto& item : itemsResponse["items"]) {
    const auto type = item["type"].asString();
    if (type != "Epic" && type != "Feature" && type != "UserStory" &&
        type != "Task" && type != "Bug" && type != "Theme") {
      continue;
    }
    const auto id = item["id"].asString();
    if (id.empty()) {
      continue;
    }
    const auto parent = item["parent"].asString();
    const bool isRoot = parent.empty() || !allIds.count(parent);
    if (!isRoot || visited.count(id)) {
      continue;
    }
    auto root = byId[id];
    attachChildren(root, id);
    response["roots"].append(root);
  }

  for (const auto& warning : itemsResponse["warnings"]) {
    response["warnings"].append(warning.asString());
  }

  return response;
}

Json::Value BacklogWebviewService::BuildKanban(const std::string& product,
                                               bool forceRefresh) {
  Json::Value response(Json::objectValue);
  response["lanes"] = Json::objectValue;
  response["lanes"]["Backlog"] = Json::arrayValue;
  response["lanes"]["Doing"] = Json::arrayValue;
  response["lanes"]["Blocked"] = Json::arrayValue;
  response["lanes"]["Review"] = Json::arrayValue;
  response["lanes"]["Done"] = Json::arrayValue;
  response["warnings"] = Json::arrayValue;

  auto itemsResponse = ListItems(product, forceRefresh);
  if (itemsResponse.isMember("error")) {
    response["error"] = itemsResponse["error"];
    return response;
  }

  for (const auto& item : itemsResponse["items"]) {
    const auto state = item["state"].asString();
    std::string lane = "Backlog";
    if (state == "InProgress") {
      lane = "Doing";
    } else if (state == "Blocked" || text::ToLower(state) == "blocked") {
      lane = "Blocked";
    } else if (state == "Review" || text::ToLower(state) == "review") {
      lane = "Review";
    } else if (state == "Done" || text::ToLower(state) == "done" ||
               text::ToLower(state) == "closed") {
      lane = "Done";
    } else if (text::ToLower(state) == "inprogress" ||
               text::ToLower(state) == "active") {
      lane = "Doing";
    }

    response["lanes"][lane].append(item);
  }

  for (const auto& warning : itemsResponse["warnings"]) {
    response["warnings"].append(warning.asString());
  }
  return response;
}

Json::Value BacklogWebviewService::Refresh(const std::string& product) {
  Json::Value response(Json::objectValue);
  if (product.empty()) {
    cacheByProduct.clear();
    response["refreshed"] = "all";
    return response;
  }
  if (!IsValidProductName(product)) {
    response["error"] = "Invalid product name";
    return response;
  }
  cacheByProduct.erase(product);
  response["refreshed"] = product;
  return response;
}

Json::Value BacklogWebviewService::GetWorkspaceInfo() const {
  Json::Value response(Json::objectValue);
  response["products_root"] = productsRoot.generic_string();
  response["workspace_root"] = productsRoot.parent_path().generic_string();
  return response;
}

Json::Value BacklogWebviewService::SwitchWorkspace(const std::string& inputPath) {
  Json::Value response(Json::objectValue);
  const auto trimmed = Trim(inputPath);
  if (trimmed.empty()) {
    response["error"] = "Missing workspace path";
    return response;
  }

  std::error_code ec;
  std::filesystem::path requested(trimmed);
  auto resolved = ResolveProductsPathFromInput(requested);
  if (resolved.empty()) {
    response["error"] =
        "Path does not contain a backlog products directory (expected products/ or _kano/backlog/products/)";
    return response;
  }

  const auto canonical = std::filesystem::weakly_canonical(resolved, ec);
  if (!ec && !canonical.empty()) {
    resolved = canonical;
  }

  productsRoot = resolved;
  cacheByProduct.clear();
  response["products_root"] = productsRoot.generic_string();
  response["workspace_root"] = productsRoot.parent_path().generic_string();
  response["switched"] = true;
  return response;
}

void RegisterBacklogWebviewRoutes(
    BacklogWebviewService& service,
    const std::function<void(const drogon::HttpRequestPtr&, Json::Value&)>&
        appendCommonMeta) {
  using namespace drogon;
  const auto metaAppender = appendCommonMeta;

  app().registerHandler(
      "/healthz",
      [metaAppender](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback) {
        Json::Value body(Json::objectValue);
        body["ok"] = true;
        body["status"] = "healthy";
        metaAppender(request, body);
        callback(HttpResponse::newHttpJsonResponse(body));
      },
      {Get});

  app().registerHandler(
      "/api/workspace/info",
      [metaAppender, &service](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback) {
        auto data = service.GetWorkspaceInfo();
        Json::Value body(Json::objectValue);
        body["ok"] = true;
        body["data"] = data;
        metaAppender(request, body);
        callback(HttpResponse::newHttpJsonResponse(body));
      },
      {Get});

  app().registerHandler(
      "/api/workspace/switch",
      [metaAppender, &service](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback) {
        const auto path = request->getParameter("path");
        auto data = service.SwitchWorkspace(path);
        Json::Value body(Json::objectValue);
        body["ok"] = !data.isMember("error");
        body["data"] = data;
        metaAppender(request, body);
        auto response = HttpResponse::newHttpJsonResponse(body);
        if (!body["ok"].asBool()) {
          response->setStatusCode(k400BadRequest);
        }
        callback(response);
      },
      {Get});

  app().registerHandler(
      "/api/products",
      [metaAppender, &service](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback) {
        Json::Value body(Json::objectValue);
        body["ok"] = true;
        body["data"] = service.ListProducts();
        metaAppender(request, body);
        callback(HttpResponse::newHttpJsonResponse(body));
      },
      {Get});

  app().registerHandler(
      "/api/refresh",
      [metaAppender, &service](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback) {
        const auto product = request->getParameter("product");
        Json::Value data = service.Refresh(product);
        Json::Value body(Json::objectValue);
        body["ok"] = !data.isMember("error");
        body["data"] = data;
        metaAppender(request, body);
        callback(HttpResponse::newHttpJsonResponse(body));
      },
      {Get});

  app().registerHandler(
      "/api/items",
      [metaAppender, &service](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback) {
        const auto product = request->getParameter("product");
        const auto q = request->getParameter("q");
        auto data = service.ListItems(product);

        if (data.isMember("items") && !q.empty()) {
          Json::Value filtered(Json::arrayValue);
          for (const auto& item : data["items"]) {
            if (text::ContainsCaseInsensitive(item["title"].asString(), q) ||
                text::ContainsCaseInsensitive(item["id"].asString(), q)) {
              filtered.append(item);
            }
          }
          data["items"] = filtered;
        }

        Json::Value body(Json::objectValue);
        body["ok"] = !data.isMember("error");
        body["data"] = data;
        metaAppender(request, body);

        auto response = HttpResponse::newHttpJsonResponse(body);
        if (!body["ok"].asBool()) {
          response->setStatusCode(k400BadRequest);
        }
        callback(response);
      },
      {Get});

  app().registerHandler(
      "/api/items/{1}",
      [metaAppender, &service](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback,
          const std::string& itemId) {
        const auto product = request->getParameter("product");
        auto data = service.GetItem(product, itemId);
        Json::Value body(Json::objectValue);
        body["ok"] = !data.isMember("error");
        body["data"] = data;
        metaAppender(request, body);

        auto response = HttpResponse::newHttpJsonResponse(body);
        if (!body["ok"].asBool()) {
          response->setStatusCode(k404NotFound);
        }
        callback(response);
      },
      {Get});

  app().registerHandler(
      "/api/tree",
      [metaAppender, &service](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback) {
        const auto product = request->getParameter("product");
        auto data = service.BuildTree(product);
        Json::Value body(Json::objectValue);
        body["ok"] = !data.isMember("error");
        body["data"] = data;
        metaAppender(request, body);

        auto response = HttpResponse::newHttpJsonResponse(body);
        if (!body["ok"].asBool()) {
          response->setStatusCode(k400BadRequest);
        }
        callback(response);
      },
      {Get});

  app().registerHandler(
      "/api/kanban",
      [metaAppender, &service](const HttpRequestPtr& request,
          std::function<void(const HttpResponsePtr&)>&& callback) {
        const auto product = request->getParameter("product");
        auto data = service.BuildKanban(product);
        Json::Value body(Json::objectValue);
        body["ok"] = !data.isMember("error");
        body["data"] = data;
        metaAppender(request, body);

        auto response = HttpResponse::newHttpJsonResponse(body);
        if (!body["ok"].asBool()) {
          response->setStatusCode(k400BadRequest);
        }
        callback(response);
      },
      {Get});
}

}  // namespace kano::backlog::webview
