#!/usr/bin/env python3
"""Fidelity check: the skill's VHS chain against the reference looktest.py, on the same input frames.

  python3 tools/fidelity_check.py <film project dir> [--video PATH] [--frames 96,97,120] [--preset V2]

Needs the reference project (looktest/, scripts/vhs_crt.py, comp/prep_tape.py) and SciPy; imports them read-only
(no bytecode written there). Feeds both chains the identical camcorder-raster frames (the reference 4:3 crop and
cubic resize) with seed 0 and reports the max absolute difference per stage, in video level (0..1).
"""

import argparse
import os
import subprocess
import sys

sys.dont_write_bytecode = True
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "vhs-crt-look", "scripts"))
from tapetube import presets, vhs  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("proj")
    ap.add_argument("--video", default=None)
    ap.add_argument("--frames", default="96,97,120")
    ap.add_argument("--preset", default="V2")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(a.proj, "looktest"))
    sys.path.insert(0, os.path.join(a.proj, "comp"))
    import cv2
    import looktest as lt  # pyright: ignore[reportMissingImports]
    import prep_tape as ptp  # pyright: ignore[reportMissingImports] # the reference stamp placement and V2 preset (module-level code reads look.json only)

    video = a.video or os.path.join(a.proj, "comp", "in", "tape.mp4")
    idx = [int(x) for x in a.frames.split(",")]
    need = sorted({j for i in idx for j in range(max(0, i - 3), i + 1)})
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            video,
            "-frames:v",
            str(max(need) + 1),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    probe = (
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                video,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.strip()
        .split(",")
    )
    w, h = int(probe[0]), int(probe[1])
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)

    def cam_raster(i):
        f = frames[int(np.clip(i, 0, len(frames) - 1))]
        nw = int(round(h * 4 / 3))
        f = f[:, (w - nw) // 2 : (w - nw) // 2 + nw]
        return cv2.resize(f, (960, 720), interpolation=cv2.INTER_CUBIC)[..., ::-1].astype(np.float32) / 255.0

    lt.FPS = 24
    lt.src_frame = cam_raster
    lt.draw_osd = ptp.draw_osd
    P_film = lt.vparams(a.preset)
    P_film["osd"] = ptp.TAPE["date"]
    data = presets.load()
    P = presets._merge(data["base_vhs"], data["vhs"][a.preset])
    P["osd"] = P_film["osd"]
    keys = sorted(set(P_film) - {"desc"})
    mism = [k for k in keys if k in P and P[k] != P_film[k] and k != "name"]
    print("parameter mismatches vs looktest:", mism or "none")
    worst = 0.0
    for i in idx:
        hist = [cam_raster(i - k) for k in range(4)]
        snaps = {}
        mine = vhs.vhs_signal(hist, P, i, 24, seed=0, snaps=snaps)
        ref = lt.vhs_signal(i, P_film)
        cam_ref = lt.camcorder(i, P_film)
        d_cam = float(np.abs(snaps["S1"] - cam_ref).max())
        d = float(np.abs(mine - ref).max())
        mean_d = float(np.abs(mine - ref).mean())
        worst = max(worst, d)
        print(f"frame {i}: camcorder max diff {d_cam:.2e}; final tape signal max diff {d:.2e}, mean {mean_d:.2e}")
    print(f"worst final-signal difference: {worst:.2e} (8-bit step = {1 / 255:.2e})")


if __name__ == "__main__":
    main()
