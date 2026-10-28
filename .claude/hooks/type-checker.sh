#!/bin/bash
# PostToolUse hook (Edit/Write): Run pyright type checking on edited Python files.
set -euo pipefail
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" || "$FILE_PATH" != *.py ]] && exit 0
if command -v pyright &>/dev/null; then
    echo "Type checking: $FILE_PATH"
    pyright "$FILE_PATH" 2>&1 | tail -5 || true
fi
exit 0
