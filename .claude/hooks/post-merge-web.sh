#!/usr/bin/env bash
# post-merge (web) — regenerate lockfile after a merge=ours resolution.
# Detects pnpm > bun > yarn > npm in that order.

set -euo pipefail
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Users/raulbrito/.volta/bin

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

changed() { git diff --name-only HEAD@{1} HEAD 2>/dev/null | /usr/bin/grep -qxF "$1"; }

if [ ! -f package.json ]; then
  exit 0
fi

if ! changed package.json; then
  exit 0
fi

regen_with() {
  local tool="$1"
  echo "[post-merge/web] package.json changed; regenerating with $tool"
  case "$tool" in
    pnpm) pnpm install --prefer-offline || echo "[post-merge/web] pnpm install failed — hand-fix required" >&2 ;;
    bun)  bun install || echo "[post-merge/web] bun install failed — hand-fix required" >&2 ;;
    yarn) yarn install --no-audit || echo "[post-merge/web] yarn install failed — hand-fix required" >&2 ;;
    npm)  npm install --no-audit --no-fund || echo "[post-merge/web] npm install failed — hand-fix required" >&2 ;;
  esac
}

if [ -f pnpm-lock.yaml ] && ! changed pnpm-lock.yaml; then regen_with pnpm; exit 0; fi
if [ -f bun.lockb ]      && ! changed bun.lockb;      then regen_with bun;  exit 0; fi
if [ -f bun.lock ]       && ! changed bun.lock;       then regen_with bun;  exit 0; fi
if [ -f yarn.lock ]      && ! changed yarn.lock;      then regen_with yarn; exit 0; fi
if [ -f package-lock.json ] && ! changed package-lock.json; then regen_with npm; exit 0; fi
