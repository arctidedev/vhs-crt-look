#!/usr/bin/env bash
set -euo pipefail

HOOK_NAME="${1:?Usage: run-hook.sh <hook-name> [args...]}"
shift || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if command -v lefthook >/dev/null 2>&1 && [[ -f "$REPO_ROOT/lefthook.yml" ]]; then
  exec lefthook run "$HOOK_NAME" "$@"
fi

case "$HOOK_NAME" in
  pre-commit)
    bash "$REPO_ROOT/.arctide/hooks/pre-commit.sh" --fix
    exec bash "$REPO_ROOT/.arctide/hooks/pre-commit.sh" --check
    ;;
  commit-msg)
    exec bash "$REPO_ROOT/.arctide/hooks/commit-msg.sh" "$@"
    ;;
  pre-push)
    exec bash "$REPO_ROOT/.arctide/hooks/pre-push.sh" "$@"
    ;;
  *)
    exit 0
    ;;
esac
