#!/usr/bin/env python3
"""vhslook: the 1987 camcorder -> VHS tape -> CRT TV look from "My Own Funeral", for any image or video.

  python vhslook.py doctor                              check Python, numpy, OpenCV, ffmpeg
  python vhslook.py looks                               list the named looks
  python vhslook.py info IN                             what the input is (size, fps, VFR, audio, alpha)
  python vhslook.py preview IN [--out DIR]              everything to choose a look: sheet, compare, ladder, page, clip
  python vhslook.py render IN OUT [look options]        the final render (image or video)
  python vhslook.py compare IN DIR | ladder IN DIR | sheet IN DIR | clip IN OUT | page IN OUT.html
  python vhslook.py rewind IN OUT --from 6 --to 2       a VCR rewind-search shot
  python vhslook.py params [look options]               the resolved parameters as JSON
  python vhslook.py selftest                            synthetic media through every look and output type

Look options: --look NAME, --tape V1..V7, --tube C1..C5|none, --treatment T0..T6, --capture direct|screen|filmed,
--mask slot|grille|dot|none, --curvature 0..1, --fill X, --date TEXT | --no-date, --date-pos br|bl|tr|tl,
--gens N, --off STAGES, --strength NAME=X (repeatable), --set KEY=VALUE, --seed N, --frame native|crop43|pad43,
--mix 0..1, --reflection IMAGE. Run any command with -h for details.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if sys.version_info < (3, 9):
    sys.exit("vhslook needs Python 3.9 or newer (this is %d.%d)." % sys.version_info[:2])

try:
    import cv2  # noqa: F401
    import numpy  # noqa: F401
except ImportError as e:  # pragma: no cover
    missing = "opencv-python-headless" if "cv2" in str(e) else "numpy"
    sys.exit(
        f"Missing Python package: {missing}.\n"
        f"Install both with:  {os.path.basename(sys.executable)} -m pip install numpy opencv-python-headless\n"
        "(or: pip install -r requirements.txt from the skill folder). Then run: python vhslook.py doctor"
    )

from tapetube import media, pipeline, presets  # noqa: E402


# ------------------------------------------------------------------------------------------------ options
def look_args(p: argparse.ArgumentParser, default_look="my-own-funeral"):
    g = p.add_argument_group("look")
    g.add_argument("--look", default=default_look, help="named look (see: vhslook.py looks)")
    g.add_argument("--tape", help="tape preset V1..V7 (overrides the look's)")
    g.add_argument("--tube", help="tube preset C1..C5, or none for no TV")
    g.add_argument("--treatment", help="tube treatment T0..T6")
    g.add_argument(
        "--capture",
        choices=presets.CAPTURES,
        help="direct (deck to capture card), screen (the CRT face, captured cleanly), filmed (a camera filming the TV)",
    )
    g.add_argument("--mask", choices=presets.MASKS, help="phosphor mask type")
    g.add_argument("--curvature", type=float, help="0 flat-face tube .. 1 strongly curved set")
    g.add_argument(
        "--fill", type=float, help="raster size in frame: 1 edge to edge, below 1 shows the bezel, above 1 zooms in"
    )
    g.add_argument("--date", help="date stamp text (camcorder OSD), e.g. 'JUL 4 1989'")
    g.add_argument("--no-date", action="store_true", help="no date stamp")
    g.add_argument("--date-pos", choices=["br", "bl", "tr", "tl"], help="date stamp corner")
    g.add_argument("--gens", type=int, help="tape generations: 1 original, 2 a dub, 3 a dub of a dub")
    g.add_argument("--off", default="", help=f"stages to switch off, comma separated: {', '.join(presets.STAGES)}")
    g.add_argument(
        "--strength",
        "-s",
        action="append",
        default=[],
        metavar="NAME=X",
        help=f"scale a part of the look (1 = preset, 0 = off, 2 = double): {', '.join(presets.KNOBS)}",
    )
    g.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="set any raw parameter, e.g. vhs.luma_tvl=[200,180]",
    )
    g.add_argument("--seed", type=int, default=0, help="noise seed (0 = the film's own noise); same seed, same output")
    g.add_argument(
        "--frame", choices=presets.FRAMES, default="native", help="native aspect (default), crop to 4:3, or pad to 4:3"
    )
    g.add_argument("--mix", type=float, default=1.0, help="blend with the original (1 = full look)")
    g.add_argument("--reflection", help="an image the TV glass mirrors (the room behind the camera)")


def build_cfg(a) -> dict:
    strengths = {k: float(v) for k, v in presets.parse_kv(a.strength)}
    return presets.build(
        look=a.look,
        tape=a.tape,
        tube=a.tube,
        treatment=a.treatment,
        capture=a.capture,
        mask=a.mask,
        curvature=a.curvature,
        fill=a.fill,
        date=a.date,
        no_date=a.no_date,
        date_pos=a.date_pos,
        gens=a.gens,
        off=[s for s in a.off.split(",") if s.strip()],
        strengths=strengths,
        sets=presets.parse_kv(a.set),
        seed=a.seed,
        frame=a.frame,
        mix=a.mix,
    )


def _q(s) -> str:
    s = str(s)
    return s if s and all(c.isalnum() or c in "-_.=,/:[]+" for c in s) else '"' + s.replace('"', '\\"') + '"'


def look_flags(a, structural=True) -> list:
    """The command-line flags that reproduce these look options (for the page's render commands)."""
    f = []
    if structural:
        if a.look:
            f += ["--look", a.look]
        for name in ("tape", "tube", "treatment", "capture", "mask"):
            if getattr(a, name):
                f += [f"--{name}", getattr(a, name)]
        for name in ("curvature", "fill"):
            if getattr(a, name) is not None:
                f += [f"--{name}", f"{getattr(a, name):g}"]
        if a.gens:
            f += ["--gens", str(a.gens)]
    if a.date is not None:
        f += ["--date", _q(a.date)]
    if a.no_date:
        f += ["--no-date"]
    if a.date_pos:
        f += ["--date-pos", a.date_pos]
    if a.off:
        f += ["--off", _q(a.off)]
    for s in a.strength:
        f += ["-s", _q(s)]
    for s in a.set:
        f += ["--set", _q(s)]
    if a.seed:
        f += ["--seed", str(a.seed)]
    if a.frame != "native":
        f += ["--frame", a.frame]
    if a.mix != 1.0:
        f += ["--mix", f"{a.mix:g}"]
    if a.reflection:
        f += ["--reflection", _q(os.path.abspath(a.reflection))]
    return f


def look_kw(a) -> dict:
    """The look options that apply on top of any named look (for sheets of several looks)."""
    return dict(
        date=a.date,
        no_date=a.no_date,
        date_pos=a.date_pos,
        off=[s for s in a.off.split(",") if s.strip()],
        strengths={k: float(v) for k, v in presets.parse_kv(a.strength)},
        sets=presets.parse_kv(a.set),
        seed=a.seed,
        frame=a.frame,
        mix=a.mix,
    )


def render_args(p):
    g = p.add_argument_group("output")
    g.add_argument("--width", type=int, help="output width (keeps the aspect ratio)")
    g.add_argument("--height", type=int, help="output height (keeps the aspect ratio)")
    g.add_argument(
        "--quality",
        choices=["standard", "high", "draft", "final"],
        default=None,
        help="standard (default for video) or high: the tube at 2x then downsampled, about 4x slower, the default for stills",
    )
    g.add_argument("--jobs", type=int, help="worker processes for video (default: CPU count - 1, max 8)")


def video_args(p):
    g = p.add_argument_group("video")
    g.add_argument("--start", type=float, help="start time in seconds")
    g.add_argument("--duration", type=float, help="length in seconds")
    g.add_argument("--fps", help="output frame rate (default: the source's average rate; VFR sources become constant)")
    g.add_argument(
        "--audio",
        choices=["copy", "aac", "vhs", "tv", "none"],
        default="copy",
        help="copy the source audio (default), re-encode it, give it the VHS linear track or a TV speaker, or drop it",
    )
    g.add_argument("--codec", choices=["h264", "prores"], default="h264")
    g.add_argument("--crf", type=int, default=16, help="H.264 quality (lower = better, larger)")


def progress_printer(label):
    last = [0.0]

    def cb(n, total, el):
        now = time.time()
        if now - last[0] < 2.0 and not (total and n >= total):
            return
        last[0] = now
        fps = n / el if el > 0 else 0
        if total:
            eta = (total - n) / fps if fps > 0 else 0
            print(f"  {label}: frame {n}/{total}, {fps:.2f} fps, about {eta:.0f} s left", file=sys.stderr, flush=True)
        else:
            print(f"  {label}: frame {n}, {fps:.2f} fps", file=sys.stderr, flush=True)

    return cb


def absp(p):
    return os.path.abspath(p)


def say(obj):
    print(json.dumps(obj, indent=1, default=str))


# ------------------------------------------------------------------------------------------------ commands
def cmd_doctor(a):
    from tapetube import doctor

    ok = doctor.run()
    sys.exit(0 if ok else 1)


def cmd_looks(a):
    data = presets.load()
    if a.json:
        say(
            {
                k: {
                    "title": v["title"],
                    "desc": v["desc"],
                    "tape": v.get("tape"),
                    "tube": v.get("tube"),
                    "treatment": v.get("treatment"),
                    "capture": v.get("capture"),
                }
                for k, v in data["looks"].items()
            }
        )
        return
    print("Named looks (--look NAME):\n")
    for k, v in data["looks"].items():
        parts = [v.get("tape")] + ([v["tube"], v.get("treatment", "T0")] if v.get("tube") else []) + [v.get("capture")]
        print(f"  {k:18s} {v['title']}  [{' '.join(p for p in parts if p)}]\n  {'':18s} {v['desc']}\n")
    print("Tape presets (--tape):")
    for k, v in data["vhs"].items():
        print(f"  {k}  {v['title']}")
    print("\nTube presets (--tube):")
    for k, v in data["crt"].items():
        print(f"  {k}  {v['title']}")
    print("\nTube treatments (--treatment):")
    for k, v in data["treatments"].items():
        print(f"  {k}  {v['title']}")
    print("\nStrengths (--strength NAME=X, 1 = preset):")
    for k, v in presets.KNOBS.items():
        print(f"  {k:11s} {v}")
    print(f"\nStages (--off a,b): {', '.join(presets.STAGES)}")


def cmd_info(a):
    k = media.kind(a.input)
    if k == "image":
        rgb, alpha, bits = media.read_image(a.input)
        say(
            {
                "path": absp(a.input),
                "kind": "image",
                "width": rgb.shape[1],
                "height": rgb.shape[0],
                "alpha": alpha is not None,
                "bits": bits,
            }
        )
    else:
        info = media.probe(a.input)
        info["kind"] = "video"
        info["path"] = absp(a.input)
        say(info)


def cmd_params(a):
    cfg = build_cfg(a)
    say({"describe": presets.describe(cfg), **cfg})


VIDEO_OUT = (".mp4", ".mov", ".mkv", ".m4v")


def check_paths(src, out, video=True):
    if not os.path.exists(src):
        sys.exit(f"error: input not found: {src}")
    if os.path.abspath(src) == os.path.abspath(out):
        sys.exit("error: the output would overwrite the input; choose another output path")
    if video and media.kind(src) == "video" and os.path.splitext(out)[1].lower() not in VIDEO_OUT:
        sys.exit(f"error: write video as {', '.join(VIDEO_OUT)} (got {os.path.splitext(out)[1] or 'no extension'})")


def cmd_render(a):
    check_paths(a.input, a.output, video=media.kind(a.output) != "image")
    cfg = build_cfg(a)
    print(f"look: {cfg['title']} ({presets.describe(cfg)})", file=sys.stderr)
    k = media.kind(a.input)
    if k == "image" and media.kind(a.output) == "video":
        sys.exit("An image renders to an image (png, jpg, tif). For video, give a video input.")
    if k == "image":
        path, size = pipeline.render_image(
            cfg, a.input, a.output, a.width, a.height, a.quality or "high", reflection=a.reflection
        )
        say({"output": absp(path), "size": size, "look": cfg["look"]})
        return
    if media.kind(a.output) == "image":
        sys.exit("A video renders to a video (mp4, mov, mkv). To grab one frame, use: compare IN DIR --time T")
    res = pipeline.render_video(
        cfg,
        a.input,
        a.output,
        a.width,
        a.height,
        a.quality or "standard",
        a.start,
        a.duration,
        a.fps,
        a.jobs,
        a.audio,
        a.codec,
        a.crf,
        a.reflection,
        progress_printer("render"),
    )
    res["path"] = absp(res["path"])
    say(res)


def _still(a):
    from tapetube import preview

    return preview.load_still(a.input, a.frame, a.time)


def cmd_compare(a):
    from tapetube import preview

    cfg = build_cfg(a)
    res = preview.compare(
        cfg, _still(a), a.out_dir, a.height, a.quality or "high", pipeline.load_reflection(a.reflection)
    )
    say({k: absp(v) for k, v in res.items()})


def cmd_ladder(a):
    from tapetube import preview

    cfg = build_cfg(a)
    res = preview.ladder(
        cfg, _still(a), a.out_dir, a.height, a.quality or "high", pipeline.load_reflection(a.reflection)
    )
    res.pop("labels", None)
    say({k: absp(v) for k, v in res.items()})


def cmd_sheet(a):
    from tapetube import preview

    looks = [x for x in (a.looks or "").split(",") if x] or None
    res = preview.sheet(_still(a), a.out_dir, looks, look_kw(a), a.tile_height, a.cols, a.quality, a.jobs, a.reflection)
    say({k: absp(v) for k, v in res.items()})


def cmd_clip(a):
    from tapetube import preview

    check_paths(a.input, a.output)
    cfg = build_cfg(a)
    res = preview.clip(
        cfg,
        a.input,
        a.output,
        a.start,
        a.duration or 3.0,
        a.height or 540,
        a.quality,
        a.side_by_side,
        a.jobs,
        a.audio,
        a.reflection,
        progress_printer("clip"),
    )
    res["path"] = absp(res["path"])
    say(res)


def cmd_page(a):
    from tapetube import page

    looks = [x for x in (a.looks or "").split(",") if x] or None
    cfg = build_cfg(a)
    path = page.build(
        a.input,
        a.output,
        cfg,
        looks=looks,
        look_kw=look_kw(a),
        t=a.time,
        height=a.height,
        clip=a.clip,
        jobs=a.jobs,
        reflection=a.reflection,
        primary_flags=look_flags(a),
        common_flags=look_flags(a, structural=False),
    )
    say({"page": absp(path)})


def cmd_preview(a):
    from tapetube import page

    cfg = build_cfg(a)
    looks = [x for x in (a.looks or "").split(",") if x] or None
    stem = os.path.splitext(os.path.basename(a.input))[0]
    out = a.out or os.path.join("vhslook_preview", stem)
    res = page.preview_all(
        a.input,
        out,
        cfg,
        looks=looks,
        look_kw=look_kw(a),
        t=a.time,
        height=a.height,
        clip=not a.no_clip,
        jobs=a.jobs,
        reflection=a.reflection,
        primary_flags=look_flags(a),
        common_flags=look_flags(a, structural=False),
        open_page=a.open,
        progress=progress_printer("preview clip"),
    )
    say(res)


def cmd_rewind(a):
    from tapetube import rewind_cmd

    check_paths(a.input, a.output)
    cfg = build_cfg(a)
    res = rewind_cmd.render(
        cfg,
        a.input,
        a.output,
        a.from_t,
        a.to_t,
        a.duration,
        a.width,
        a.height,
        a.quality or "standard",
        a.jobs,
        a.fps,
        a.reflection,
        progress_printer("rewind"),
    )
    res["path"] = absp(res["path"])
    say(res)


def cmd_selftest(a):
    from tapetube import selftest

    ok = selftest.run(a.out, quick=a.quick, jobs=a.jobs, only=a.only)
    sys.exit(0 if ok else 1)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="vhslook", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True

    p = sub.add_parser("doctor", help="check the environment")
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("looks", help="list looks, presets, strengths and stages")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_looks)
    p = sub.add_parser("info", help="describe an input")
    p.add_argument("input")
    p.set_defaults(fn=cmd_info)
    p = sub.add_parser("params", help="print the resolved parameters")
    look_args(p)
    p.set_defaults(fn=cmd_params)

    p = sub.add_parser("render", help="final render of an image or video")
    p.add_argument("input")
    p.add_argument("output")
    look_args(p)
    render_args(p)
    video_args(p)
    p.set_defaults(fn=cmd_render)

    for name, fn, hlp in (
        ("compare", cmd_compare, "split and side-by-side stills"),
        ("ladder", cmd_ladder, "stage ladder"),
    ):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("input")
        p.add_argument("out_dir")
        p.add_argument("--time", type=float, help="video: the moment to show (seconds)")
        look_args(p)
        render_args(p)
        p.set_defaults(fn=fn)

    p = sub.add_parser("sheet", help="contact sheet of looks on your frame")
    p.add_argument("input")
    p.add_argument("out_dir")
    p.add_argument("--looks", help="comma-separated looks (default: all)")
    p.add_argument("--time", type=float)
    p.add_argument("--tile-height", type=int, default=600)
    p.add_argument("--cols", type=int, default=4)
    look_args(p)
    render_args(p)
    p.set_defaults(fn=cmd_sheet, quality="standard")

    p = sub.add_parser("clip", help="short preview clip")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--side-by-side", action="store_true", help="original and look side by side")
    look_args(p)
    render_args(p)
    video_args(p)
    p.set_defaults(fn=cmd_clip, quality="standard")

    p = sub.add_parser("page", help="offline HTML comparison page with a before/after slider")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--looks", help="comma-separated looks to include (default: all)")
    p.add_argument("--time", type=float)
    p.add_argument("--clip", help="a preview clip to embed")
    look_args(p)
    render_args(p)
    p.set_defaults(fn=cmd_page)

    p = sub.add_parser("preview", help="sheet + compare + ladder + page (+ clip for video) in one folder")
    p.add_argument("input")
    p.add_argument("--out", help="folder (default: ./vhslook_preview/<input name>)")
    p.add_argument("--looks", help="comma-separated looks for the sheet and page (default: all)")
    p.add_argument("--time", type=float, help="video: the moment to show (seconds)")
    p.add_argument("--no-clip", action="store_true", help="video: skip the preview clip")
    p.add_argument("--open", action="store_true", help="open the page in the default browser")
    look_args(p)
    render_args(p)
    p.set_defaults(fn=cmd_preview)

    p = sub.add_parser("rewind", help="a VCR rewind-search shot")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--from", dest="from_t", type=float, required=True, help="source time where the rewind starts")
    p.add_argument("--to", dest="to_t", type=float, required=True, help="source time where it lands (earlier)")
    p.add_argument("--duration", type=float, default=2.0, help="length of the rewind shot in seconds")
    p.add_argument("--fps")
    look_args(p)
    render_args(p)
    p.set_defaults(fn=cmd_rewind)

    p = sub.add_parser("selftest", help="build synthetic media and run every look and output type")
    p.add_argument("--out", help="folder for the test outputs (default: a temporary folder)")
    p.add_argument("--quick", action="store_true", help="fewer frames and smaller sizes")
    p.add_argument("--jobs", type=int)
    p.add_argument("--only", help="run only the checks whose name contains this text, e.g. 'video'")
    p.set_defaults(fn=cmd_selftest)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (ValueError, media.MediaError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
