#!/bin/bash
# Stop/PreCompact hook: Auto-commit tracked-file changes as checkpoints.
# Iterates: hub repo, all git worktrees, all child project directories.
# Prevents work from being lost across session restarts or compactions.
#
# IN-PROGRESS-WORK SAFETY: auto-commits ONLY when the repo's dirty state is
# "tracked modifications, nothing pre-staged, no untracked SOURCE files" — the one
# state where `git add -u` captures the whole change. If the index is already
# staged, or untracked source files are present (a new module the tracked edits
# import), the repo is skipped: committing the tracked subset there splits an
# in-progress increment into a broken HEAD that references files not in the tree.
#
# Kill switches / overrides (shell env or .claude/settings.json env block):
#   CHECKPOINT_DISABLE=1               — skip entirely
#   CHECKPOINT_SKIP_REPOS="Beacon foo" — skip these basenames (space-separated)
#   CHECKPOINT_INCLUDE_UNTRACKED=1     — commit untracked too (disables the source guard)
#   CHECKPOINT_AI_ROOT=/path           — override the hub root (for testing)

set -uo pipefail

# Honor global kill switch.
if [[ "${CHECKPOINT_DISABLE:-0}" = "1" ]]; then
	exit 0
fi

AI_ROOT="${CHECKPOINT_AI_ROOT:-/Users/raulbrito/Projects/AI}"

# Tokenize the per-repo skip list once.
SKIP_LIST="${CHECKPOINT_SKIP_REPOS:-}"

checkpoint_repo() {
	local REPO_PATH="$1"
	cd "$REPO_PATH" 2>/dev/null || return 0

	# Per-repo skip via CHECKPOINT_SKIP_REPOS.
	local BASENAME
	BASENAME=$(basename "$REPO_PATH")
	for skip in $SKIP_LIST; do
		if [[ "$BASENAME" == "$skip" ]]; then
			return 0
		fi
	done

	local DIRTY
	DIRTY=$(git status --porcelain 2>/dev/null)
	[[ -z "$DIRTY" ]] && return 0

	# Guard 0: a pre-populated index means the user (or another tool) is
	# hand-assembling a commit. Don't `git add` on top of it and commit their
	# partial staging — skip until the index is clean. (`--quiet` exits non-zero
	# when staged changes exist.)
	if ! git diff --cached --quiet 2>/dev/null; then
		echo "CHECKPOINT: skip $(basename "$REPO_PATH") — index already has staged changes"
		return 0
	fi

	# Guard 1: min-interval — if last commit was itself a checkpoint and it
	# happened < MIN_INTERVAL seconds ago, defer. Does NOT gate after a
	# user/feature commit (the checkpoint chain restarts each meaningful commit).
	local MIN_INTERVAL=${CHECKPOINT_MIN_INTERVAL_SECONDS:-1800}
	local LAST_COMMIT_TIME LAST_COMMIT_MSG NOW_EPOCH AGE_SECS
	LAST_COMMIT_TIME=$(git log -1 --format=%ct 2>/dev/null || echo 0)
	LAST_COMMIT_MSG=$(git log -1 --format=%s 2>/dev/null || echo "")
	NOW_EPOCH=$(date +%s)
	AGE_SECS=$((NOW_EPOCH - LAST_COMMIT_TIME))
	if [[ "$LAST_COMMIT_MSG" == "chore(checkpoint):"* && "$AGE_SECS" -lt "$MIN_INTERVAL" ]]; then
		return 0
	fi

	# Guard 2: min-lines — skip if the total insert+delete churn is trivial.
	# Prevents a checkpoint on a whitespace tweak or single-char edit.
	local MIN_LINES=${CHECKPOINT_MIN_LINES_CHANGED:-20}
	local LINES_CHANGED
	LINES_CHANGED=$(git diff HEAD --shortstat 2>/dev/null |
		grep -oE '[0-9]+ insertions?|[0-9]+ deletions?' |
		awk '{s+=$1} END {print s+0}')
	if [[ "$LINES_CHANGED" -lt "$MIN_LINES" ]]; then
		return 0
	fi

	# Guard 3: refuse to commit untracked-only state (no tracked-file edits at
	# all). New files frequently belong to a feature branch the user is
	# actively editing on a *different* session, and committing them onto
	# whatever HEAD happens to be checked out here loses them. Modifications
	# to already-tracked files are still safe — those originate from this
	# session by definition. Override with CHECKPOINT_INCLUDE_UNTRACKED=1.
	if [[ "${CHECKPOINT_INCLUDE_UNTRACKED:-0}" != "1" ]]; then
		# Guard 3a (the in-progress-increment fix): untracked SOURCE files present →
		# this is a multi-file change whose tracked siblings would be committed WITHOUT
		# them, leaving a broken HEAD (e.g. a committed `import` of a module not in the
		# tree). Skip the whole repo; the user commits the set deliberately. `--others
		# --exclude-standard` already drops gitignored build output, so this fires on
		# real new source, not on dist/ or node_modules/.
		local UNTRACKED_SRC
		UNTRACKED_SRC=$(git ls-files --others --exclude-standard 2>/dev/null |
			grep -iE '\.(ts|tsx|js|jsx|mjs|cjs|swift|m|mm|h|hpp|kt|kts|java|py|rb|go|rs|c|cc|cpp|sh|bash)$|(^|/)(src|sources|packages|lib|app)/' |
			head -1)
		if [[ -n "$UNTRACKED_SRC" ]]; then
			echo "CHECKPOINT: skip $(basename "$REPO_PATH") — untracked source present (in-progress change)"
			return 0
		fi

		# Guard 3b: untracked-only state (no tracked-file edits at all). New files
		# frequently belong to a feature branch the user is actively editing on a
		# *different* session; committing them onto whatever HEAD is checked out here
		# loses them. Tracked modifications are still safe — they originate from this
		# session by definition.
		local TRACKED_DIFF
		TRACKED_DIFF=$(git diff HEAD --name-only 2>/dev/null | head -1)
		if [[ -z "$TRACKED_DIFF" ]]; then
			return 0
		fi
	fi

	# Stage only modifications to tracked files (the safe set), unless the
	# caller opted into untracked.
	if [[ "${CHECKPOINT_INCLUDE_UNTRACKED:-0}" = "1" ]]; then
		git add -A 2>/dev/null
	else
		git add -u 2>/dev/null
	fi

	local TIMESTAMP FILES FILE_COUNT MSG
	TIMESTAMP=$(date +%Y-%m-%dT%H:%M)
	FILE_COUNT=$(git diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ')
	FILES=$(git diff --cached --name-only 2>/dev/null | head -5 | tr '\n' ',' | sed 's/,$//')

	[[ "$FILE_COUNT" -eq 0 ]] && return 0

	if [[ ${#FILES} -gt 60 ]]; then
		FILES="${FILES:0:57}..."
	fi

	MSG="chore(checkpoint): auto-save ${FILE_COUNT} file(s) at ${TIMESTAMP} — ${FILES}"
	git commit --no-verify -m "$MSG" 2>/dev/null || true
	echo "CHECKPOINT: committed ${FILE_COUNT} file(s) in $(basename "$REPO_PATH")"
}

# 1. Hub repo itself
checkpoint_repo "$AI_ROOT"

# 2. All git worktrees (skip the main worktree which IS AI_ROOT)
while IFS= read -r line; do
	WT_PATH=$(echo "$line" | awk '{print $1}')
	[[ "$WT_PATH" == "$AI_ROOT" ]] && continue
	[[ -d "$WT_PATH" ]] && checkpoint_repo "$WT_PATH"
done < <(git -C "$AI_ROOT" worktree list 2>/dev/null)

# 3. Child project directories (each has its own .git)
for dir in "$AI_ROOT"/*/; do
	[[ ! -d "${dir}.git" ]] && continue
	BASENAME=$(basename "$dir")
	# Skip hub-managed directories
	case "$BASENAME" in
	templates | scripts | docs | shared | .claude | .git | node_modules) continue ;;
	esac
	checkpoint_repo "$dir"
done
