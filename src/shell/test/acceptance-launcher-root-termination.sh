#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LAUNCHER="$SKILL_ROOT/src/shell/core/kano-backlog"
RESULT_FILE="$(mktemp "${TMPDIR:-/tmp}/kob-root-termination.XXXXXX")"
resolver_pid=""

cleanup() {
  if [[ -n "$resolver_pid" ]] && kill -0 "$resolver_pid" 2>/dev/null; then
    kill "$resolver_pid" 2>/dev/null || true
    wait "$resolver_pid" 2>/dev/null || true
  fi
  rm -f "$RESULT_FILE"
}
trap cleanup EXIT

resolver_source="$(awk '
  /^resolve_workspace_root\(\) \{/ { capture = 1 }
  capture { print }
  capture && /^}$/ { exit }
' "$LAUNCHER")"
[[ -n "$resolver_source" ]] || { echo "FAIL: launcher resolver was not found" >&2; exit 1; }
eval "$resolver_source"

# GNU dirname builds on Windows may collapse a drive-root parent to '.'.
# The resolver must stop instead of repeatedly spawning dirname forever.
dirname() {
  printf '.\n'
}

PWD='D:/'
resolve_workspace_root >"$RESULT_FILE" &
resolver_pid=$!

for _ in {1..100}; do
  if ! kill -0 "$resolver_pid" 2>/dev/null; then
    wait "$resolver_pid"
    resolver_pid=""
    break
  fi
  sleep 0.01
done

if [[ -n "$resolver_pid" ]]; then
  echo "FAIL: launcher workspace-root resolution did not terminate" >&2
  exit 1
fi

[[ "$(cat "$RESULT_FILE")" == 'D:/' ]] || {
  echo "FAIL: launcher did not preserve the invocation directory fallback" >&2
  exit 1
}

echo "PASS: launcher workspace-root resolution stops at a stable parent"
