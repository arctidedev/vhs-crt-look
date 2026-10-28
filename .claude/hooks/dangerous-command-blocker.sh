#!/bin/bash
# PreToolUse hook (Bash): Blocks destructive shell commands before execution.
# Exit code 2 = block the command. Exit code 0 = allow.
# Receives JSON on stdin with tool_input.command.
#
# Merged version — combines:
#   - study-wall's JSON structured block() output (correct per Claude Code hook spec)
#   - video-maker's normalized matching and git patterns
#   - Original shared/ SQL/chmod/fork-bomb patterns
#
# To add project-specific directory protection, copy this to your project's
# .claude/hooks/ and add a "Protect critical directories" section after line ~30.

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [[ -z "$COMMAND" ]]; then
	exit 0
fi

# Normalize: collapse whitespace, lowercase for matching
NORMALIZED=$(echo "$COMMAND" | tr '[:upper:]' '[:lower:]' | tr -s ' ')

block() {
	echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}" >&2
	exit 2
}

# --- Destructive file operations ---
if echo "$NORMALIZED" | grep -qE 'rm[[:space:]]+(-[a-z]*r[a-z]*f|--recursive.*--force|-[a-z]*f[a-z]*r)'; then
	block "BLOCKED: rm -rf is destructive. Use targeted rm on specific files instead."
fi

if echo "$NORMALIZED" | grep -qE '(sudo[[:space:]]+rm|rm[[:space:]]+-[a-z]*[[:space:]]*/[[:space:]]*$)'; then
	block "BLOCKED: sudo rm or rm on root path is too destructive. Target specific files."
fi

if echo "$NORMALIZED" | grep -qE 'chmod[[:space:]]+-[a-z]*r[[:space:]].*777'; then
	block "BLOCKED: chmod -R 777 is a security risk. Use specific permissions instead."
fi

# Fork bomb
if echo "$COMMAND" | grep -qF ':(){:|:&};:'; then
	block "BLOCKED: Fork bomb detected."
fi

# Disk operations
if echo "$NORMALIZED" | grep -qE 'mkfs\.|dd[[:space:]]+if='; then
	block "BLOCKED: Disk formatting/writing command detected."
fi

# --- Destructive git operations ---
if echo "$NORMALIZED" | grep -qE 'git[[:space:]]+push[[:space:]]+(-[a-z]*f[[:space:]]|--force[[:space:]]|--force$|-f[[:space:]]|-f$)'; then
	block "BLOCKED: git push --force can destroy remote history. Use --force-with-lease if necessary."
fi

if echo "$NORMALIZED" | grep -qE 'git[[:space:]]+reset[[:space:]]+--hard'; then
	block "BLOCKED: git reset --hard discards all uncommitted changes. Use git stash instead."
fi

if echo "$NORMALIZED" | grep -qE 'git[[:space:]]+checkout[[:space:]]+\.[[:space:]]*$'; then
	block "BLOCKED: git checkout . discards all working tree changes. Use git stash or target specific files."
fi

if echo "$NORMALIZED" | grep -qE 'git[[:space:]]+restore[[:space:]]+\.[[:space:]]*$'; then
	block "BLOCKED: git restore . discards all working tree changes. Use git stash or target specific files."
fi

if echo "$NORMALIZED" | grep -qE 'git[[:space:]]+clean[[:space:]]+(-[a-z]*f|--force)'; then
	block "BLOCKED: git clean -f permanently deletes untracked files. List them first with git clean -n."
fi

if echo "$NORMALIZED" | grep -qE 'git[[:space:]]+branch[[:space:]]+-[a-z]*d[[:space:]]'; then
	# Only block uppercase -D (force delete); lowercase -d is safe
	if echo "$COMMAND" | grep -qE 'git[[:space:]]+branch[[:space:]]+-[a-zA-Z]*D'; then
		block "BLOCKED: git branch -D force-deletes without merge check. Use git branch -d (lowercase) for safe deletion."
	fi
fi

# --- Skipping safety checks ---
if echo "$NORMALIZED" | grep -qE -- '--no-verify'; then
	block "BLOCKED: --no-verify skips pre-commit hooks and safety checks. Fix the underlying issue instead."
fi

# --- Database destructive operations ---
if echo "$COMMAND" | grep -qiE 'DROP[[:space:]]+(TABLE|DATABASE|SCHEMA)|TRUNCATE[[:space:]]+TABLE'; then
	block "BLOCKED: Destructive SQL operation. Verify with user before dropping/truncating."
fi

# --- Hub meta-file protection (hub context only) ---
# Prevent accidental deletion of hub-level files that are tracked in the planning repo.
# Projects may extend this with their own critical dir list.
if echo "$NORMALIZED" | grep -qE "(^|[[:space:];&|(])(rm|rmdir)[[:space:]].*\b(\.claude|\.github|templates|scripts|shared)\b"; then
	block "BLOCKED: Attempting to delete a hub meta-directory. These are tracked in the planning repo."
fi

# --- Everything else: allow ---
exit 0
