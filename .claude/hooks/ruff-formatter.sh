#!/bin/bash
# PostToolUse hook (Edit/Write): Auto-format Python files with ruff.
set -euo pipefail
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" || "$FILE_PATH" != *.py ]] && exit 0
command -v ruff &>/dev/null && ruff format "$FILE_PATH" 2>/dev/null || true
exit 0
