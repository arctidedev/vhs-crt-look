#!/usr/bin/env bash
# design-precommit.sh
# Pre-commit hook: enforces design-taste guardrails on staged changes.
#
# Three checks (each opt-out via env var):
#   1. Banned vocabulary in staged diff (DESIGN_VOCAB=0 to skip)
#   2. Hardcoded hex outside design-system / token files (DESIGN_HEX=0 to skip)
#   3. WCAG AA contrast on the project's tokens-*.json (DESIGN_CONTRAST=0 to skip)
#
# Installation per project:
#   cp shared/common-hooks/design-precommit.sh <project>/.git/hooks/pre-commit-design
#   chmod +x <project>/.git/hooks/pre-commit-design
#   # Then call from the project's pre-commit hook OR invoke directly.
#
# To skip the entire hook on one commit: git commit --no-verify
#
# Latency note: contrast check uses jq + offline computation (no MCP/network call).
# Target overall latency: under 1s on a typical staged diff.

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
HUB_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SHARED_TOKENS="$HUB_ROOT/shared/design-tokens/tokens-shared.json"

# Detect which token file applies to this repo
detect_tokens_file() {
  local repo_name
  repo_name="$(basename "$REPO_ROOT")"
  case "$repo_name" in
    beacon|Beacon)        echo "$HUB_ROOT/shared/design-tokens/tokens-beacon.json" ;;
    hangar|Hangar)        echo "$HUB_ROOT/shared/design-tokens/tokens-hangar.json" ;;
    digital-products|arctide-website*)  echo "$HUB_ROOT/shared/design-tokens/tokens-arctide.json" ;;
    *)                    echo "" ;;
  esac
}

PROJECT_TOKENS="$(detect_tokens_file)"
violations=0

# ------------------------------------------------------------
# 1. Banned vocabulary in staged diff
# ------------------------------------------------------------
if [[ "${DESIGN_VOCAB:-1}" != "0" ]] && [[ -f "$SHARED_TOKENS" ]]; then
  forbidden=$(python3 -c "
import json
with open('$SHARED_TOKENS') as f:
    data = json.load(f)
words = data.get('voice', {}).get('forbidden', {}).get(r'\$value', [])
print('|'.join(w.replace(' ', r'\\s+') for w in words))
" 2>/dev/null)

  if [[ -z "$forbidden" ]]; then
    forbidden='unleash|supercharge|game-changer|revolutionize|10x|crush|empowering|journey|delighting|leverage|seamless|best-in-class|world-class|Welcome!|Hi\s+there|Hey\s+friend'
  fi

  staged_diff=$(git diff --cached --diff-filter=ACM -U0 -- '*.swift' '*.md' '*.html' '*.txt' '*.tsx' '*.jsx' 2>/dev/null || true)
  if [[ -n "$staged_diff" ]]; then
    vocab_hits=$(echo "$staged_diff" | grep -E '^\+' | grep -v '^\+\+\+' | grep -iE "($forbidden)" || true)
    if [[ -n "$vocab_hits" ]]; then
      echo "✗ design-precommit: banned vocabulary in staged diff:"
      echo "$vocab_hits" | head -10 | sed 's/^/    /'
      violations=$((violations + 1))
    fi
  fi
fi

# ------------------------------------------------------------
# 2. Hardcoded hex in staged Swift files outside design-system
# ------------------------------------------------------------
if [[ "${DESIGN_HEX:-1}" != "0" ]]; then
  staged_swift=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.swift$' \
    | grep -vE '/(DesignSystem|HangarDesign)/|BeaconColors\.swift|BeaconColorPalette\.swift|BeaconTheme\.swift|HangarColors\.swift|HangarTheme\.swift|HangarTokens\.swift' \
    || true)

  if [[ -n "$staged_swift" ]]; then
    while IFS= read -r f; do
      [[ -z "$f" || ! -f "$f" ]] && continue
      hits=$(git diff --cached -U0 -- "$f" \
        | grep -E '^\+' | grep -v '^\+\+\+' \
        | grep -E '#[0-9A-Fa-f]{6}\b|0x[0-9A-Fa-f]{2}\s*/\s*255' || true)
      if [[ -n "$hits" ]]; then
        echo "✗ design-precommit: hardcoded hex in $f (use $(basename "$PROJECT_TOKENS" 2>/dev/null) tokens):"
        echo "$hits" | head -5 | sed 's/^/    /'
        violations=$((violations + 1))
      fi
    done <<<"$staged_swift"
  fi
fi

# ------------------------------------------------------------
# 3. WCAG AA contrast check on the project's token color combinations
# ------------------------------------------------------------
# Only runs if (a) the project's tokens-*.json was staged, (b) jq is installed,
# (c) DESIGN_CONTRAST != 0. Failures only block on body-text combinations.
if [[ "${DESIGN_CONTRAST:-1}" != "0" ]] && command -v jq &>/dev/null && [[ -f "$PROJECT_TOKENS" ]]; then
  if git diff --cached --name-only | grep -qF "$(basename "$PROJECT_TOKENS")"; then
    # Compute relative luminance offline (no MCP needed for the gate path).
    fg=$(jq -r '.color.text.primary."$value" // empty' "$PROJECT_TOKENS" 2>/dev/null)
    bg=$(jq -r '.color.background.base."$value" // .color.background.surface."$value" // empty' "$PROJECT_TOKENS" 2>/dev/null)

    if [[ -n "$fg" && -n "$bg" && "$fg" =~ ^#[0-9A-Fa-f]{6}$ && "$bg" =~ ^#[0-9A-Fa-f]{6}$ ]]; then
      ratio=$(python3 - <<PY
def rel_lum(hex_color):
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    def c(x):
        x /= 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126*c(r) + 0.7152*c(g) + 0.0722*c(b)

l1, l2 = rel_lum("$fg"), rel_lum("$bg")
hi, lo = max(l1, l2), min(l1, l2)
print(round((hi + 0.05) / (lo + 0.05), 2))
PY
)
      # WCAG AA body text = 4.5:1
      ok=$(python3 -c "print(1 if float('$ratio') >= 4.5 else 0)")
      if [[ "$ok" != "1" ]]; then
        echo "✗ design-precommit: WCAG AA fail — text/bg contrast $ratio:1 (need ≥4.5:1)"
        echo "    fg=$fg bg=$bg in $(basename "$PROJECT_TOKENS")"
        violations=$((violations + 1))
      fi
    fi
  fi
fi

# ------------------------------------------------------------
# Exit
# ------------------------------------------------------------
if [[ $violations -eq 0 ]]; then
  exit 0
else
  echo ""
  echo "design-precommit: $violations violation(s). Fix or override with DESIGN_VOCAB=0 / DESIGN_HEX=0 / DESIGN_CONTRAST=0 / git commit --no-verify."
  exit 1
fi
