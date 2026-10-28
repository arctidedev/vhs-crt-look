#!/usr/bin/env python3
"""Zip the skill folder for sharing or uploading: dist/vhs-crt-look-skill.zip with vhs-crt-look/ at its top level.

python tools/package_skill.py [--out DIR]
"""

import argparse
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "vhs-crt-look")
SKIP_DIRS = {"__pycache__", "vhslook_preview", ".ruff_cache", ".pytest_cache", ".venv"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "vhs-crt-look-skill.zip")
    n = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(SKILL):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            for f in sorted(files):
                if f.endswith(".pyc") or f == ".DS_Store":
                    continue
                full = os.path.join(d, f)
                z.write(full, os.path.join("vhs-crt-look", os.path.relpath(full, SKILL)))
                n += 1
    print(f"{path} ({n} files, {os.path.getsize(path) / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
