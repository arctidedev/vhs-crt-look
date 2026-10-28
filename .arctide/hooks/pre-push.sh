#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -x "$REPO_ROOT/scripts/quality-guardian.sh" ]]; then
	HUB_ROOT="$REPO_ROOT"
elif [[ -x "$(dirname "$REPO_ROOT")/scripts/quality-guardian.sh" ]]; then
	HUB_ROOT="$(cd "$(dirname "$REPO_ROOT")" && pwd)"
elif MAIN_ROOT="$(dirname "$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")" &&
	[[ -x "$(dirname "$MAIN_ROOT")/scripts/quality-guardian.sh" ]]; then
	# a linked worktree outside the hub: find the hub through the main checkout that owns the .git dir
	HUB_ROOT="$(cd "$(dirname "$MAIN_ROOT")" && pwd)"
else
	echo "ERROR [quality-guardian] Could not locate hub scripts/quality-guardian.sh" >&2
	exit 1
fi

export QUALITY_GUARDIAN_BYPASS_CONTRACT=true
# --pre-push: the guardian reads the pushed refs git gives this hook on stdin (exec passes it on)
exec "$HUB_ROOT/scripts/quality-guardian.sh" --repo-path "$REPO_ROOT" --check --full --pre-push
