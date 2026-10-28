#!/usr/bin/env bash
# PostToolUse hook: apply safe per-file autofixes immediately after edits.
#
# This is intentionally narrow. It fixes formatting and autocorrectable lint
# issues, then lets quality-checker / quality-guardian report anything that
# still needs a semantic change.

set -uo pipefail

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" || ! -f "$FILE_PATH" ]] && exit 0

case "$FILE_PATH" in
  *"/.git/"*|*"/.build/"*|*"/DerivedData/"*|*"/node_modules/"*|*"/.swiftpm/"*) exit 0 ;;
esac

DIR=$(dirname "$FILE_PATH")
PROJECT_ROOT=""
while [[ "$DIR" != "/" ]]; do
  if [[ -d "$DIR/.git" ]]; then
    PROJECT_ROOT="$DIR"
    break
  fi
  DIR=$(dirname "$DIR")
done

[[ -z "$PROJECT_ROOT" ]] && exit 0

case "$FILE_PATH" in
  *.swift)
    if command -v swiftformat >/dev/null 2>&1; then
      swiftformat "$FILE_PATH" >/dev/null 2>&1 || true
    fi
    if command -v swiftlint >/dev/null 2>&1 && [[ -f "$PROJECT_ROOT/.swiftlint.yml" ]]; then
      rel="${FILE_PATH#"$PROJECT_ROOT"/}"
      (cd "$PROJECT_ROOT" && swiftlint lint --fix --format --force-exclude --quiet "$rel" >/dev/null 2>&1) || true
    fi
    ;;
  *.py)
    if command -v ruff >/dev/null 2>&1; then
      ruff check --fix "$FILE_PATH" >/dev/null 2>&1 || true
      ruff format "$FILE_PATH" >/dev/null 2>&1 || true
    fi
    ;;
  *.ts|*.tsx|*.js|*.jsx|*.css|*.astro)
    if [[ -x "$PROJECT_ROOT/node_modules/.bin/prettier" ]]; then
      (cd "$PROJECT_ROOT" && npx prettier --write "$FILE_PATH" >/dev/null 2>&1) || true
    fi
    if [[ "$FILE_PATH" == *.ts || "$FILE_PATH" == *.tsx || "$FILE_PATH" == *.js || "$FILE_PATH" == *.jsx ]] && \
       [[ -x "$PROJECT_ROOT/node_modules/.bin/eslint" ]]; then
      (cd "$PROJECT_ROOT" && npx eslint --fix "$FILE_PATH" >/dev/null 2>&1) || true
    fi
    ;;
  *.sh)
    if command -v shfmt >/dev/null 2>&1; then
      shfmt -w "$FILE_PATH" >/dev/null 2>&1 || true
    fi
    ;;
esac

exit 0
