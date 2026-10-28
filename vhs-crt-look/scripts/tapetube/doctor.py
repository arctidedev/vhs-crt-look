"""Environment check with install guidance for each platform."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile


def _line(ok, name, detail, fix=None):
    mark = "OK  " if ok else ("WARN" if ok is None else "FAIL")
    print(f"  [{mark}] {name}: {detail}")
    if fix and not ok:
        for f in fix:
            print(f"         {f}")


def run() -> bool:
    print("vhslook doctor")
    print(
        f"  platform: {platform.system()} {platform.release()} ({platform.machine()}), Python {platform.python_version()}"
    )
    ok_all = True
    py_ok = sys.version_info >= (3, 9)
    _line(
        py_ok,
        "Python >= 3.9",
        platform.python_version(),
        ["Install Python 3.9 or newer from python.org (or your package manager)."],
    )
    ok_all &= py_ok
    pip = f'{os.path.basename(sys.executable)} "{os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vhslook.py")}" setup'
    try:
        import numpy as np

        _line(True, "numpy", np.__version__)
    except ImportError:
        _line(False, "numpy", "missing", [pip])
        ok_all = False
    try:
        import cv2

        _line(True, "OpenCV (cv2)", cv2.__version__)
    except ImportError as e:
        hint = [pip]
        if "libGL" in str(e):
            hint = [
                "The non-headless OpenCV needs libGL. Use the headless build:",
                "pip uninstall -y opencv-python && " + pip,
            ]
        _line(False, "OpenCV (cv2)", f"missing ({e})", hint)
        ok_all = False
    from . import media

    ff, fp = media.ffmpeg_bin(), media.ffprobe_bin()
    fix = (
        ["easiest: run setup (it offers to install ffmpeg):  " + pip]
        + {
            "Darwin": ["brew install ffmpeg"],
            "Windows": ["winget install Gyan.FFmpeg   (then open a new terminal)", "or: choco install ffmpeg"],
            "Linux": ["sudo apt install ffmpeg   (Debian/Ubuntu)", "sudo dnf install ffmpeg   (Fedora, RPM Fusion)"],
        }.get(platform.system(), ["install ffmpeg from ffmpeg.org"])
        + [
            "conda: conda install -c conda-forge ffmpeg",
            "or set VHSLOOK_FFMPEG and VHSLOOK_FFPROBE to the binaries",
        ]
    )
    if ff:
        try:
            v = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
        except (OSError, IndexError):
            v = "unreadable"
        _line(True, "ffmpeg", f"{ff} ({v})")
    else:
        _line(None, "ffmpeg", "not found: images work, video needs it", fix)
    _line(bool(fp) if ff else None, "ffprobe", fp or "not found", fix if ff else None)
    if ff:
        enc = media.encoders()
        h264 = "libx264" in enc
        alt = next((e for e in ("libopenh264", "h264_videotoolbox") if e in enc), "mpeg4")
        _line(True if h264 else None, "H.264 encoder", "libx264" if h264 else f"libx264 missing, falling back to {alt}")
        _line(
            True if "aac" in enc else None,
            "AAC encoder",
            "aac" if "aac" in enc else "missing (audio is copied when possible)",
        )
    try:
        with tempfile.TemporaryDirectory() as td:
            open(os.path.join(td, "w"), "w").close()
        _line(True, "temporary folder", tempfile.gettempdir())
    except OSError as e:
        _line(False, "temporary folder", str(e))
        ok_all = False
    print(f"  CPU cores: {os.cpu_count()}")
    print("\n" + ("Ready." if ok_all else "Fix the FAIL lines above, then run doctor again."))
    if ok_all and not ff:
        print("Images are ready; install ffmpeg for video.")
    return ok_all
