"""Finding ffmpeg and ffprobe (standard library only, so setup can use it before numpy is installed).

Looks in: VHSLOOK_FFMPEG / VHSLOOK_FFPROBE, the skill's own bin/ folder, PATH, then the places installers put them
that a fresh terminal or an app's PATH often misses (Homebrew, MacPorts, winget, Chocolatey, Scoop, conda)."""

from __future__ import annotations

import glob
import os
import shutil
import sys
from typing import List, Optional

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXE = ".exe" if os.name == "nt" else ""


def _candidates(name: str) -> List[str]:
    home = os.path.expanduser("~")
    c = [os.path.join(SKILL_DIR, "bin", name + EXE)]
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        c += [os.path.join(la, "Microsoft", "WinGet", "Links", name + EXE)]
        c += sorted(glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "*", "bin", name + EXE)))
        c += [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "chocolatey", "bin", name + EXE)]
        c += [os.path.join(home, "scoop", "shims", name + EXE), os.path.join("C:\\", "ffmpeg", "bin", name + EXE)]
    else:
        c += [
            "/opt/homebrew/bin/" + name,
            "/usr/local/bin/" + name,
            "/opt/local/bin/" + name,
            "/usr/bin/" + name,
            "/snap/bin/" + name,
            "/home/linuxbrew/.linuxbrew/bin/" + name,
        ]
    if os.environ.get("CONDA_PREFIX"):
        sub = "Library/bin" if os.name == "nt" else "bin"
        c.append(os.path.join(os.environ["CONDA_PREFIX"], sub, name + EXE))
    return c


def find(name: str) -> Optional[str]:
    env = os.environ.get("VHSLOOK_" + name.upper())
    if env and os.path.exists(env):
        return env
    local = os.path.join(SKILL_DIR, "bin", name + EXE)
    if os.path.exists(local):
        return local
    p = shutil.which(name)
    if p:
        return p
    for cand in _candidates(name):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def install_command() -> Optional[List[str]]:
    """The one command that installs ffmpeg on this machine, or None if no package manager is available."""
    if sys.platform == "darwin":
        brew = shutil.which("brew") or next(
            (b for b in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if os.path.exists(b)), None
        )
        if brew:
            return [brew, "install", "ffmpeg"]
        if shutil.which("port"):
            return ["sudo", "port", "install", "ffmpeg"]
    elif os.name == "nt":
        if shutil.which("winget"):
            return [
                "winget",
                "install",
                "--id",
                "Gyan.FFmpeg",
                "-e",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ]
        if shutil.which("choco"):
            return ["choco", "install", "ffmpeg", "-y"]
        if shutil.which("scoop"):
            return ["scoop", "install", "ffmpeg"]
    else:
        for pm, cmd in (
            ("apt-get", ["sudo", "apt-get", "install", "-y", "ffmpeg"]),
            ("dnf", ["sudo", "dnf", "install", "-y", "ffmpeg"]),
            ("pacman", ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"]),
            ("zypper", ["sudo", "zypper", "install", "-y", "ffmpeg"]),
            ("apk", ["sudo", "apk", "add", "ffmpeg"]),
        ):
            if shutil.which(pm):
                return cmd
    if os.environ.get("CONDA_PREFIX") and shutil.which("conda"):
        return ["conda", "install", "-y", "-c", "conda-forge", "ffmpeg"]
    return None


def manual_hint() -> str:
    if sys.platform == "darwin":
        return "Install Homebrew from https://brew.sh, then run: brew install ffmpeg"
    if os.name == "nt":
        return "Run: winget install Gyan.FFmpeg   (or download a build from https://www.gyan.dev/ffmpeg/builds/)"
    return "Install ffmpeg with your distribution's package manager, for example: sudo apt install ffmpeg"
