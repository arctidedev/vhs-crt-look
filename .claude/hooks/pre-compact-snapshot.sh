#!/bin/bash
# PreCompact hook: Saves working context before compaction for restoration.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../scripts/platform-resolver.sh"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

SNAPSHOT="/tmp/claude-compact-ai-hub-${SESSION_ID}.md"

cd "$AI_ROOT"

{
    echo "# AI Hub Context Snapshot"
    echo ""
    echo "## Parent Repo"
    git log --oneline -3 2>/dev/null || echo "(no commits)"
    echo ""
    echo "## Modified Meta-Files"
    git diff --name-only 2>/dev/null || echo "(none)"
    echo ""
    echo "## Child Projects With Changes"
    for dir in "$AI_ROOT"/*/; do
        [[ ! -d "$dir/.git" ]] && continue
        BASENAME=$(basename "$dir")
        case "$BASENAME" in templates|scripts|docs|shared|.claude|.git|.github) continue ;; esac
        cd "$dir"
        CHANGES=$(git diff --name-only 2>/dev/null | wc -l | tr -d ' ')
        if [[ "$CHANGES" -gt 0 ]]; then
            echo "- $BASENAME ($CHANGES files changed)"
        fi
    done
} > "$SNAPSHOT" 2>/dev/null

echo "Context snapshot saved to $SNAPSHOT"
exit 0
