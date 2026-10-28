#!/bin/bash
# PostToolUse hook (Write): Checks for known vulnerabilities when dependency files change.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Only trigger on dependency files
case "$(basename "$FILE_PATH")" in
    pyproject.toml|requirements.txt|setup.py|setup.cfg) ;;
    package.json|package-lock.json) ;;
    Gemfile|Gemfile.lock) ;;
    *) exit 0 ;;
esac

PROJECT_ROOT=$(dirname "$FILE_PATH")
cd "$PROJECT_ROOT"

case "$(basename "$FILE_PATH")" in
    pyproject.toml|requirements.txt|setup.py|setup.cfg)
        if command -v pip-audit &>/dev/null; then
            echo "Running pip-audit..."
            pip-audit 2>&1 | tail -10 || true
        elif command -v uv &>/dev/null; then
            echo "Checking Python dependencies..."
            uv pip audit 2>&1 | tail -10 || true
        fi
        ;;
    package.json|package-lock.json)
        if [[ -f "package-lock.json" ]]; then
            echo "Running npm audit..."
            npm audit --omit=dev 2>&1 | tail -10 || true
        fi
        ;;
esac

exit 0
