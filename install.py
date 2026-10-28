#!/usr/bin/env python3
"""Install the vhs-crt-look skill for Claude Code.

  python install.py                    into your user skills folder (all projects)
  python install.py --project DIR      into DIR/.claude/skills (one project)
  python install.py --force            replace an existing copy
  python install.py --deps             also pip-install numpy and opencv-python-headless

The user skills folder is $CLAUDE_CONFIG_DIR/skills when that variable is set, otherwise ~/.claude/skills.
"""

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "vhs-crt-look")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "vhslook_preview", ".ruff_cache", ".pytest_cache")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="install into this project's .claude/skills instead of the user folder")
    ap.add_argument("--force", action="store_true", help="replace an existing installation")
    ap.add_argument("--deps", action="store_true", help="pip-install the Python packages for this interpreter")
    a = ap.parse_args()
    if a.project:
        base = os.path.join(os.path.abspath(a.project), ".claude", "skills")
    else:
        root = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
        base = os.path.join(root, "skills")
    dest = os.path.join(base, "vhs-crt-look")
    if os.path.exists(dest):
        if not a.force:
            sys.exit(f"{dest} already exists. Run again with --force to replace it.")
        shutil.rmtree(dest)
    os.makedirs(base, exist_ok=True)
    shutil.copytree(SKILL, dest, ignore=IGNORE)
    print(f"Installed the skill to {dest}")
    if a.deps:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", os.path.join(dest, "requirements.txt")])
    print("Check the setup with:")
    print(f'  {os.path.basename(sys.executable)} "{os.path.join(dest, "scripts", "vhslook.py")}" doctor')


if __name__ == "__main__":
    main()
