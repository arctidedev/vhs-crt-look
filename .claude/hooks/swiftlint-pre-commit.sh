#!/usr/bin/env bash
# swiftlint-pre-commit.sh
# Pre-commit hook: lints only staged .swift files using SwiftLint.
#
# Installation per project:
#   cp shared/common-hooks/swiftlint-pre-commit.sh <project>/.git/hooks/pre-commit
#   chmod +x <project>/.git/hooks/pre-commit

set -euo pipefail

if ! command -v swiftlint &>/dev/null; then
  echo "swiftlint not found — skipping lint (install via: brew install swiftlint)"
  exit 0
fi

# Collect staged .swift files
STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep '\.swift$' || true)

if [ -z "$STAGED" ]; then
  exit 0
fi

echo "SwiftLint: linting $(echo "$STAGED" | wc -l | tr -d ' ') staged file(s)..."

# Safety suppressions must not enter commits. Style-level exceptions remain
# project policy, but force/concurrency safety rules must be fixed in code.
SAFETY_RULE_PATTERN='force_cast|force_try|force_unwrapping|nonisolated_unsafe|unchecked_sendable|process_info_hostname|dispatch_main_sync|thread_sleep'
if echo "$STAGED" | xargs grep -nE "swiftlint:disable.*(${SAFETY_RULE_PATTERN})" 2>/dev/null; then
  echo ""
  echo "Safety SwiftLint suppressions are not allowed. Fix the code instead."
  exit 1
fi

# Run swiftlint on each staged file individually so we respect the project config.
FAILED=0
while IFS= read -r file; do
  if [ -f "$file" ]; then
    swiftlint lint --strict --force-exclude --quiet "$file" || FAILED=1
  fi
done <<< "$STAGED"

if [ "$FAILED" -ne 0 ]; then
  echo ""
  echo "SwiftLint reported errors. Fix them or use 'git commit --no-verify' to bypass."
  exit 1
fi

exit 0
