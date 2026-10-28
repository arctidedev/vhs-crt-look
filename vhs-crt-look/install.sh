#!/usr/bin/env bash
# Installs the vhs-crt-look skill for Claude Code (macOS and Linux).
#   bash install.sh          copy the skill into ~/.claude/skills, set up its Python packages, check ffmpeg
#   bash install.sh --yes    the same, and install ffmpeg without asking if it is missing
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$HOME/.claude"
if [[ -n "${CLAUDE_CONFIG_DIR:-}" && -d "${CLAUDE_CONFIG_DIR}" ]]; then CONFIG="$CLAUDE_CONFIG_DIR"; fi
DEST="$CONFIG/skills/vhs-crt-look"

PY=""
for cand in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
	if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
		PY="$(command -v "$cand")"
		break
	fi
done
if [[ -z "$PY" ]]; then
	echo "Python 3.9 or newer is needed and was not found."
	if [[ "$(uname -s)" == "Darwin" ]]; then
		echo "Install it with:  xcode-select --install   (or from https://www.python.org/downloads/), then run this again."
	else
		echo "Install it with your package manager, for example:  sudo apt install python3 python3-venv"
	fi
	exit 1
fi

if [[ "$HERE" != "$DEST" ]]; then
	echo "Copying the skill to $DEST"
	mkdir -p "$DEST"
	for item in "$HERE"/* "$HERE"/.[!.]*; do
		[[ -e "$item" ]] || continue
		name="$(basename "$item")"
		case "$name" in .venv | __pycache__ | .DS_Store | vhslook_preview) continue ;; esac
		cp -R "$item" "$DEST/"
	done
fi

"$PY" "$DEST/scripts/vhslook.py" setup "$@"
