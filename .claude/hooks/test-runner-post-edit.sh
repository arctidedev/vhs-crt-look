#!/bin/bash
# PostToolUse hook (Edit/Write): Auto-runs relevant tests after code edits.
# Only runs if a test file exists for the edited file.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Skip test files themselves, configs, docs, Swift (swift test is too slow for per-edit).
# Swift tests run via pre-commit + CI, not inline hooks.
case "$FILE_PATH" in
    *test*|*spec*|*.md|*.json|*.yml|*.yaml|*.toml|*.cfg|*.ini|*.swift) exit 0 ;;
esac

# Determine project root
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
FILENAME=$(basename "$FILE_PATH" | sed 's/\.[^.]*$//')

# Look for corresponding test file and run it
case "$FILE_PATH" in
    *.py)
        TEST_FILE=$(find . -name "test_${FILENAME}.py" -o -name "${FILENAME}_test.py" 2>/dev/null | head -1)
        if [[ -n "$TEST_FILE" ]]; then
            if [[ -f "pyproject.toml" ]] && command -v uv &>/dev/null; then
                echo "Running: uv run pytest $TEST_FILE -x -q"
                uv run pytest "$TEST_FILE" -x -q 2>&1 | tail -5
            elif command -v pytest &>/dev/null; then
                echo "Running: pytest $TEST_FILE -x -q"
                pytest "$TEST_FILE" -x -q 2>&1 | tail -5
            fi
        fi
        ;;
    *.ts|*.tsx|*.js|*.jsx)
        TEST_FILE=$(find . -name "${FILENAME}.test.*" -o -name "${FILENAME}.spec.*" 2>/dev/null | head -1)
        if [[ -n "$TEST_FILE" ]]; then
            if [[ -f "node_modules/.bin/jest" ]]; then
                echo "Running: npx jest $TEST_FILE"
                npx jest "$TEST_FILE" --no-coverage 2>&1 | tail -5
            elif [[ -f "node_modules/.bin/vitest" ]]; then
                echo "Running: npx vitest run $TEST_FILE"
                npx vitest run "$TEST_FILE" 2>&1 | tail -5
            fi
        fi
        ;;
esac

exit 0
