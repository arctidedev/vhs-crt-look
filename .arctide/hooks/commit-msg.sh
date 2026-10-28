#!/usr/bin/env bash
set -euo pipefail

MSG_FILE="${1:?Usage: commit-msg.sh <message-file>}"
MSG="$(head -1 "$MSG_FILE")"

if [[ "$MSG" =~ ^Merge ]]; then
  exit 0
fi

if [[ "$MSG" =~ ^WIP: ]]; then
  exit 0
fi

pattern='^(feat|fix|docs|chore|refactor|test|perf|ci|build|style|revert)(\([a-zA-Z0-9._/-]+\))?: .{3,72}$'

if [[ ! "$MSG" =~ $pattern ]]; then
  cat <<EOF

ERROR [commit-msg]
  rule: conventional-commits
  format: type(scope): subject
  types: feat fix docs chore refactor test perf ci build style revert
  subject: 3-72 chars, imperative mood
  got: $MSG
  examples:
    feat(auth): add biometric login support
    fix: resolve crash on empty product list
EOF
  exit 1
fi

exit 0
