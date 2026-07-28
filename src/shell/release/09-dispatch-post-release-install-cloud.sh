#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

repo=""
tag=""
version=""
platform=""
output_root=""
correlation=""
use_cloud="true"
execute_install="true"
enable_homebrew="true"
enable_winget="false"
enable_apt="false"
enable_msi="true"
allow_tar_fallback="true"

usage() {
  cat >&2 <<'EOF'
Usage: 09-dispatch-post-release-install-cloud.sh --repo OWNER/REPO --tag TAG \
  --version VERSION --platform PLATFORM --output-dir DIR [options]

Options:
  --correlation ID
  --use-cloud true|false
  --execute-install true|false
  --enable-homebrew true|false
  --enable-winget true|false
  --enable-apt true|false
  --enable-msi true|false
  --allow-tar-fallback true|false
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) repo="${2:-}"; shift 2 ;;
    --tag) tag="${2:-}"; shift 2 ;;
    --version) version="${2:-}"; shift 2 ;;
    --platform) platform="${2:-}"; shift 2 ;;
    --output-dir) output_root="${2:-}"; shift 2 ;;
    --correlation) correlation="${2:-}"; shift 2 ;;
    --use-cloud) use_cloud="${2:-}"; shift 2 ;;
    --execute-install) execute_install="${2:-}"; shift 2 ;;
    --enable-homebrew) enable_homebrew="${2:-}"; shift 2 ;;
    --enable-winget) enable_winget="${2:-}"; shift 2 ;;
    --enable-apt) enable_apt="${2:-}"; shift 2 ;;
    --enable-msi) enable_msi="${2:-}"; shift 2 ;;
    --allow-tar-fallback) allow_tar_fallback="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

for required in repo tag version platform output_root; do
  if [[ -z "${!required}" ]]; then
    echo "Missing required --${required//_/-}" >&2
    exit 2
  fi
done

cloud_root="$output_root/cloud"
artifact_root="$cloud_root/artifacts"
mkdir -p "$artifact_root"
if [[ -d "$artifact_root" ]]; then
  find "$artifact_root" -depth -mindepth 1 -delete
fi
rm -f -- \
  "$cloud_root/backend-pass.txt" \
  "$cloud_root/backend-info.txt" \
  "$cloud_root/backend-warning.txt" \
  "$cloud_root/fallback-required.txt" \
  "$cloud_root/correlation.txt" \
  "$cloud_root/install-verification-backend-summary.json" \
  "$cloud_root/install-verification-backend-summary.md" \
  "$cloud_root/run-id.txt" \
  "$cloud_root/run.json"

require_fallback() {
  local reason="$1"
  printf '%s\n' "$reason" | tee "$cloud_root/backend-warning.txt"
  printf '%s\n' "$reason" >"$cloud_root/fallback-required.txt"
}

require_local_backend() {
  local reason="$1"
  printf '%s\n' "$reason" | tee "$cloud_root/backend-info.txt"
  printf '%s\n' "$reason" >"$cloud_root/fallback-required.txt"
}

if [[ "$use_cloud" != "true" ]]; then
  require_local_backend "GitHub Actions cloud backend disabled by configuration; local verification is selected."
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  require_fallback "gh is unavailable; cloud backend cannot be dispatched."
  exit 0
fi

if [[ -z "$correlation" ]]; then
  correlation="jenkins-${BUILD_NUMBER:-0}-${BUILD_ID:-manual}-$(date +%s)"
fi
correlation="$(printf '%s' "$correlation" | tr -cs 'A-Za-z0-9._-' '-')"
correlation="${correlation#-}"
correlation="${correlation%-}"
if [[ -z "$correlation" ]]; then
  require_fallback "Cloud backend correlation ID normalized to empty."
  exit 0
fi
printf '%s\n' "$correlation" >"$cloud_root/correlation.txt"

set +e
gh workflow run post-release-install-verify.yml \
  --repo "$repo" \
  -f release_tag="$tag" \
  -f release_version="$version" \
  -f platform="$platform" \
  -f correlation_id="$correlation" \
  -f execute_install="$execute_install" \
  -f enable_homebrew="$enable_homebrew" \
  -f enable_winget="$enable_winget" \
  -f enable_apt="$enable_apt" \
  -f enable_msi="$enable_msi" \
  -f allow_tar_fallback="$allow_tar_fallback"
dispatch_rc=$?
set -e
if [[ "$dispatch_rc" -ne 0 ]]; then
  require_fallback "GitHub Actions dispatch failed with exit code $dispatch_rc."
  exit 0
fi

run_id=""
resolve_attempts="${KANO_INSTALL_VERIFY_RESOLVE_ATTEMPTS:-30}"
resolve_delay="${KANO_INSTALL_VERIFY_RESOLVE_DELAY_SECONDS:-2}"
for ((attempt = 1; attempt <= resolve_attempts; attempt += 1)); do
  while IFS=$'\t' read -r candidate_id display_title; do
    if [[ "$display_title" == *"_${correlation}" ]]; then
      run_id="$candidate_id"
      break
    fi
  done < <(
    gh run list \
      --repo "$repo" \
      --workflow post-release-install-verify.yml \
      --event workflow_dispatch \
      --limit 50 \
      --json databaseId,displayTitle \
      --jq '.[] | [.databaseId, .displayTitle] | @tsv' 2>/dev/null || true
  )
  [[ -n "$run_id" ]] && break
  sleep "$resolve_delay"
done

if [[ -z "$run_id" ]]; then
  require_fallback "Dispatched cloud verification but could not resolve its run ID within the bounded polling window."
  exit 0
fi
printf '%s\n' "$run_id" >"$cloud_root/run-id.txt"

run_status=""
run_conclusion=""
completion_attempts="${KANO_INSTALL_VERIFY_COMPLETION_ATTEMPTS:-300}"
completion_delay="${KANO_INSTALL_VERIFY_COMPLETION_DELAY_SECONDS:-10}"
for ((attempt = 1; attempt <= completion_attempts; attempt += 1)); do
  set +e
  run_state="$(
    gh run view "$run_id" \
      --repo "$repo" \
      --json status,conclusion,url \
      --jq '.status + "|" + (.conclusion // "") + "|" + .url'
  )"
  view_rc=$?
  set -e
  if [[ "$view_rc" -ne 0 ]]; then
    require_fallback "Cloud verification run $run_id could not be inspected."
    exit 0
  fi
  IFS='|' read -r run_status run_conclusion run_url <<<"$run_state"
  if [[ "$run_status" == "completed" ]]; then
    break
  fi
  sleep "$completion_delay"
done

if [[ "$run_status" != "completed" ]]; then
  require_fallback "Cloud verification run $run_id did not complete within the bounded polling window."
  exit 0
fi

set +e
gh run view "$run_id" --repo "$repo" --json databaseId,status,conclusion,url >"$cloud_root/run.json"
view_rc=$?
gh run download "$run_id" \
  --repo "$repo" \
  --name "post-release-install-verification-${platform}" \
  --dir "$artifact_root"
download_rc=$?
set -e

if [[ "$view_rc" -ne 0 ]]; then
  printf '{"databaseId":"%s","status":"completed","conclusion":"%s"}\n' \
    "$run_id" "$run_conclusion" >"$cloud_root/run.json"
fi
if [[ "$download_rc" -ne 0 ]]; then
  require_fallback "Cloud verification run $run_id completed but its evidence artifact could not be downloaded."
  exit 0
fi

set +e
bash "$SCRIPT_DIR/10-aggregate-post-release-install-backends.sh" \
  --input-root "$artifact_root" \
  --output-dir "$cloud_root" \
  --fail-if-no-pass
aggregate_rc=$?
set -e

conclusion_rc=1
if [[ "$run_conclusion" == "success" ]]; then
  conclusion_rc=0
fi
if [[ "$conclusion_rc" -eq 0 && "$aggregate_rc" -eq 0 ]]; then
  printf 'Cloud verification run %s completed with passing install evidence.\n' "$run_id" |
    tee "$cloud_root/backend-pass.txt"
  exit 0
fi

require_fallback "Cloud verification run $run_id did not complete successfully with passing evidence (conclusion=${run_conclusion:-unknown} aggregate=$aggregate_rc)."
exit 0
