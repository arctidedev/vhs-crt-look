#!/bin/bash
# PostToolUse hook (Edit/Write): Runs quality checks after code edits.
# Detects project type and runs appropriate linter/formatter.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Determine project root (find nearest .git dir)
DIR=$(dirname "$FILE_PATH")
PROJECT_ROOT=""
while [[ "$DIR" != "/" ]]; do
    if [[ -d "$DIR/.git" ]]; then
        PROJECT_ROOT="$DIR"
        break
    fi
    DIR=$(dirname "$DIR")
done

if [[ -z "$PROJECT_ROOT" ]]; then
    exit 0
fi

cd "$PROJECT_ROOT"

# Check file extension and run appropriate linter
case "$FILE_PATH" in
    *.py)
        if command -v ruff &>/dev/null; then
            ruff check --fix "$FILE_PATH" 2>/dev/null || true
            ruff format "$FILE_PATH" 2>/dev/null || true
        fi
        ;;
    *.ts|*.tsx|*.js|*.jsx)
        if [[ -f "node_modules/.bin/prettier" ]]; then
            npx prettier --write "$FILE_PATH" 2>/dev/null || true
        fi
        if [[ -f "node_modules/.bin/eslint" ]]; then
            npx eslint --fix "$FILE_PATH" 2>/dev/null || true
        fi
        ;;
    *.swift)
        if command -v swiftformat &>/dev/null; then
            swiftformat "$FILE_PATH" 2>/dev/null || true
        fi
        if command -v swiftlint &>/dev/null && [[ -f ".swiftlint.yml" ]]; then
            REL_PATH="${FILE_PATH#"$PROJECT_ROOT"/}"
            VIOLATIONS=$(swiftlint lint --strict --force-exclude --quiet "$REL_PATH" 2>/dev/null || true)
            if [[ -n "$VIOLATIONS" ]]; then
                echo "SwiftLint violations in $(basename "$FILE_PATH"):"
                echo "$VIOLATIONS" | head -15
            fi
        fi
        ;;
    *.json)
        python3 -c "
import json, sys
try:
    with open('$FILE_PATH') as f:
        json.load(f)
except json.JSONDecodeError as e:
    print(f'JSON validation failed: {e}')
    sys.exit(1)
" 2>/dev/null || true
        ;;
esac

exit 0
