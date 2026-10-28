#!/usr/bin/env bash
# post-merge (python) — regenerate lockfiles after a merge=ours resolution.
# Detects uv > poetry > pdm > pip-tools order.

set -euo pipefail
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Users/raulbrito/Library/Python/3.9/bin

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

changed() { git diff --name-only HEAD@{1} HEAD 2>/dev/null | /usr/bin/grep -qxF "$1"; }

manifest_changed=false
[ -f pyproject.toml ]    && changed pyproject.toml    && manifest_changed=true
[ -f requirements.in ]   && changed requirements.in   && manifest_changed=true
[ -f Pipfile ]           && changed Pipfile           && manifest_changed=true

if ! $manifest_changed; then
  exit 0
fi

if [ -f uv.lock ] && ! changed uv.lock && command -v uv >/dev/null 2>&1; then
  echo "[post-merge/python] regenerating uv.lock"; uv sync --frozen 2>/dev/null || uv lock
  exit 0
fi
if [ -f poetry.lock ] && ! changed poetry.lock && command -v poetry >/dev/null 2>&1; then
  echo "[post-merge/python] regenerating poetry.lock"; poetry lock --no-update
  exit 0
fi
if [ -f pdm.lock ] && ! changed pdm.lock && command -v pdm >/dev/null 2>&1; then
  echo "[post-merge/python] regenerating pdm.lock"; pdm lock --no-update
  exit 0
fi
if [ -f requirements.txt ] && ! changed requirements.txt && command -v pip-compile >/dev/null 2>&1; then
  echo "[post-merge/python] regenerating requirements.txt"; pip-compile --quiet
  exit 0
fi
