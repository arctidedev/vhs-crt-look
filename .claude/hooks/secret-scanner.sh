#!/bin/bash
# PreToolUse hook (Write): Scans for secrets in file content before writing.
# Reads tool input from stdin. Exit 2 = block. Exit 0 = allow.

set -euo pipefail

INPUT=$(cat)
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$CONTENT" ]]; then
    exit 0
fi

# Skip scanning certain file types
case "$FILE_PATH" in
    *.env.example|*.md|*.txt|*.tmpl) exit 0 ;;
esac

# Secret patterns to detect
SECRET_PATTERNS=(
    'sk-[a-zA-Z0-9]{20,}'           # OpenAI/Anthropic API keys
    'ghp_[a-zA-Z0-9]{36}'           # GitHub personal access tokens
    'gho_[a-zA-Z0-9]{36}'           # GitHub OAuth tokens
    'AKIA[0-9A-Z]{16}'              # AWS access key IDs
    'AIza[0-9A-Za-z_-]{35}'         # Google API keys
    'xox[bprs]-[0-9a-zA-Z]{10,}'    # Slack tokens
    'sk_live_[0-9a-zA-Z]{24,}'      # Stripe live keys
    'sq0[a-z]{3}-[0-9A-Za-z_-]{22,}' # Square tokens
    'SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}' # SendGrid
)

for pattern in "${SECRET_PATTERNS[@]}"; do
    if echo "$CONTENT" | grep -qE "$pattern"; then
        echo "BLOCKED: Potential secret/API key detected in file write to $FILE_PATH"
        echo "Pattern matched: $pattern"
        echo "Never commit secrets to code. Use environment variables instead."
        exit 2
    fi
done

exit 0
