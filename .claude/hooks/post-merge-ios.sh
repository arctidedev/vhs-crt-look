#!/usr/bin/env bash
# post-merge (iOS) — regenerate Package.resolved after a merge=ours resolution.
#
# Git invokes post-merge with $1 = "squash" flag (0 for normal merge, 1 for squash).
# We regenerate only if Package.swift changed and Package.resolved did NOT change
# (meaning merge=ours took the local copy and skipped the incoming updates).

set -euo pipefail
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

changed() { git diff --name-only HEAD@{1} HEAD 2>/dev/null | /usr/bin/grep -qxF "$1"; }

if [ ! -f Package.swift ]; then
  exit 0  # not a SwiftPM repo, nothing to do
fi

if changed Package.swift && ! changed Package.resolved; then
  echo "[post-merge/ios] Package.swift changed; resolving dependencies"
  if command -v swift >/dev/null 2>&1; then
    swift package resolve || echo "[post-merge/ios] swift package resolve failed — hand-fix required" >&2
  else
    echo "[post-merge/ios] swift toolchain not in PATH; skipping" >&2
  fi
fi
