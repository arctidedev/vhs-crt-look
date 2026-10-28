#!/usr/bin/env python3
"""Install the vhs-crt-look skill for Claude Code from a checkout of this repository (any OS).

  python install.py                    into your user skills folder, then run the skill's setup
  python install.py --project DIR      into DIR/.claude/skills (one project)
  python install.py --yes              also install ffmpeg without asking if it is missing

The user skills folder is $CLAUDE_CONFIG_DIR/skills when that variable is set, otherwise ~/.claude/skills.
An existing installation is updated in place (its Python environment is kept).
People who downloaded the zip use INSTALL-mac.command, INSTALL-windows.bat or install.sh inside it instead.
"""

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "vhs-crt-look")
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".DS_Store", "vhslook_preview", ".ruff_cache", ".pytest_cache", ".venv"
)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="install into this project's .claude/skills instead of the user folder")
    ap.add_argument("--yes", "-y", action="store_true", help="install ffmpeg without asking if it is missing")
    a = ap.parse_args()
    if a.project:
        base = os.path.join(os.path.abspath(a.project), ".claude", "skills")
    else:
        cfg = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
        root = cfg if cfg and os.path.isdir(cfg) else os.path.join(os.path.expanduser("~"), ".claude")
        base = os.path.join(root, "skills")
    dest = os.path.join(base, "vhs-crt-look")
    os.makedirs(dest, exist_ok=True)
    shutil.copytree(SKILL, dest, ignore=IGNORE, dirs_exist_ok=True)
    print(f"Installed the skill files to {dest}")
    cmd = [sys.executable, os.path.join(dest, "scripts", "vhslook.py"), "setup"] + (["--yes"] if a.yes else [])
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
