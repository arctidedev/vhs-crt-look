"""Self-test: builds synthetic media (test patterns, alpha, odd and portrait sizes, 16-bit, grayscale, CFR and VFR
video with audio, rotated, odd-size alpha video, a longer clip) and runs every look and every output type, checking
sizes, frame counts, frame rates, audio, alpha, determinism and that the page is fully offline."""

from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
import traceback

import cv2
import numpy as np

from . import media, osd, page, pipeline, presets, preview, rewind_cmd


# ------------------------------------------------------------------------------------------------ synthetic media
def pattern(w: int, h: int, t: float = 0.0) -> np.ndarray:
    """A test card: colour bars, a grey ramp, fine vertical lines, a skin patch, a hot highlight, lettering."""
    img = np.zeros((h, w, 3), np.float32)
    bars = [
        (0.75, 0.75, 0.75),
        (0.75, 0.75, 0),
        (0, 0.75, 0.75),
        (0, 0.75, 0),
        (0.75, 0, 0.75),
        (0.75, 0, 0),
        (0, 0, 0.75),
    ]
    bh = int(h * 0.5)
    for i, c in enumerate(bars):
        x0, x1 = int(i * w / 7), int((i + 1) * w / 7)
        img[:bh, x0:x1] = c
    ramp = np.linspace(0, 1, w, dtype=np.float32)
    img[bh : int(h * 0.62)] = ramp[None, :, None]
    y0, y1 = int(h * 0.62), int(h * 0.78)
    xs = np.arange(w)
    freq = 0.02 + 0.45 * xs / w  # cycles per pixel, rising across the frame
    lines = 0.5 + 0.5 * np.cos(2 * np.pi * np.cumsum(freq)).astype(np.float32)
    img[y0:y1] = lines[None, :, None]
    img[y1:] = (0.08, 0.07, 0.06)
    sx = int(w * (0.1 + 0.05 * math.sin(t * 2)))
    img[int(h * 0.82) : int(h * 0.95), sx : sx + int(w * 0.18)] = (0.87, 0.62, 0.5)  # skin
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = w * (0.55 + 0.25 * math.sin(t * 1.3)), h * 0.88
    ball = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (0.03 * h) ** 2))).astype(np.float32)
    img = np.maximum(img, ball[..., None] * 1.0)
    cell = max(1, h // 120)
    img = osd.draw_lines(img, [("TAPETUBE TEST", w * 0.62, h * 0.82, cell)], soft=0)
    return np.clip(img, 0, 1)


def _pipe(cmd, frames_fn, n):
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(n):
            p.stdin.write(frames_fn(i).tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode(errors="replace")
    p.wait()
    return p.returncode, err


def write_video(path, frames_fn, n, w, h, fps="24", audio=True, extra=None, pix_fmt="yuv420p", codec=None, vfr=False):
    ff = media.ffmpeg_bin()
    raw = "rgba" if pix_fmt.startswith(("rgba", "yuva")) else "rgb24"
    cmd = [ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", raw, "-s", f"{w}x{h}", "-r", fps, "-i", "-"]
    if audio:
        cmd += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={n / pipeline.eval_fps(fps) + 0.5:.3f}",
        ]
    if vfr:  # variable frame rate: the first half at 24 fps, the second at 12 fps
        h2 = n // 2
        cmd += ["-vf", f"setpts='if(lt(N,{h2}),N/24,{h2}/24+(N-{h2})/12)/TB'"]
    if codec is None:
        enc = media.encoders()
        codec = ["-c:v", "libx264", "-crf", "16"] if "libx264" in enc else ["-c:v", "mpeg4", "-q:v", "2"]
    cmd += codec + ["-pix_fmt", pix_fmt]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    tail = (extra or []) + [path]
    if vfr:
        rc, err = _pipe(cmd + ["-fps_mode", "passthrough"] + tail, frames_fn, n)
        if rc:  # ffmpeg older than 5.1
            rc, err = _pipe(cmd + ["-vsync", "vfr"] + tail, frames_fn, n)
    else:
        rc, err = _pipe(cmd + tail, frames_fn, n)
    if rc:
        raise RuntimeError(err[-400:])
    return path


def u8(rgb):
    return (np.clip(rgb, 0, 1) * 255).round().astype(np.uint8)


def decode_all(path, w=None, h=None):
    info = media.probe(path)
    w, h = w or info["width"], h or info["height"]
    return np.stack(list(media.VideoReader(path, info, w, h, "native", fps_str=info["fps_str"])))


# ------------------------------------------------------------------------------------------------ runner
class Runner:
    def __init__(self):
        self.rows = []

    def check(self, name, fn):
        t = time.time()
        try:
            detail = fn()
            self.rows.append({"test": name, "ok": True, "detail": detail or "", "s": round(time.time() - t, 2)})
            print(f"  PASS  {name}  {detail or ''}  ({time.time() - t:.1f} s)", flush=True)
        except Exception as e:  # noqa: BLE001
            self.rows.append(
                {
                    "test": name,
                    "ok": False,
                    "detail": f"{type(e).__name__}: {e}",
                    "s": round(time.time() - t, 2),
                    "trace": traceback.format_exc()[-1500:],
                }
            )
            print(f"  FAIL  {name}  {type(e).__name__}: {e}", flush=True)

    def skip(self, name, why):
        self.rows.append({"test": name, "ok": None, "detail": "skipped: " + why, "s": 0})
        print(f"  SKIP  {name}  {why}", flush=True)


def assert_img(path, w=None, h=None, channels=None, dtype=np.uint8):
    a = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
    assert a is not None, f"unreadable {path}"
    if w is not None:
        assert a.shape[1] == w and a.shape[0] == h, f"size {a.shape[1]}x{a.shape[0]}, expected {w}x{h}"
    if channels is not None:
        c = 1 if a.ndim == 2 else a.shape[2]
        assert c == channels, f"{c} channels, expected {channels}"
    assert a.dtype == dtype, f"dtype {a.dtype}, expected {dtype}"
    return a


def run(out=None, quick=False, jobs=None) -> bool:
    out = os.path.abspath(out or tempfile.mkdtemp(prefix="vhslook_selftest_"))
    src = os.path.join(out, "media")
    os.makedirs(src, exist_ok=True)
    R = Runner()
    print(
        f"vhslook selftest ({'quick' if quick else 'full'}) on {platform.system()} {platform.machine()}, Python "
        f"{platform.python_version()}, numpy {np.__version__}, OpenCV {cv2.__version__}"
    )
    print(f"  outputs: {out}")
    data = presets.load()
    q = "draft" if quick else "final"
    have_ff = bool(media.ffmpeg_bin() and media.ffprobe_bin())

    # ---- images
    W, H = (320, 240) if quick else (640, 480)
    img = os.path.join(src, "pattern.png")
    media.write_image(img, pattern(W, H))
    rgba = os.path.join(src, "alpha.png")
    a = np.zeros((300, 400), np.float32)
    yy, xx = np.mgrid[0:300, 0:400]
    a[((xx - 200) ** 2 + (yy - 150) ** 2) < 120**2] = 1.0
    media.write_image(rgba, pattern(400, 300), cv2.GaussianBlur(a, (0, 0), 3))
    odd = os.path.join(src, "odd_portrait.jpg")
    media.write_image(odd, pattern(333, 601))
    b16 = os.path.join(src, "deep16.png")
    media.write_image(b16, pattern(320, 240), bits=16)
    gray = os.path.join(src, "gray.png")
    cv2.imencode(".png", u8(pattern(300, 200).mean(2)))[1].tofile(gray)
    wide = os.path.join(src, "wide.png")
    media.write_image(wide, pattern(900, 260))
    tiny = os.path.join(src, "tiny.png")
    media.write_image(tiny, pattern(64, 48))

    io = os.path.join(out, "images")
    for look in data["looks"]:

        def f(look=look):
            cfg = presets.build(look=look)
            p, size = pipeline.render_image(cfg, img, os.path.join(io, f"look_{look}.png"), quality=q)
            x = assert_img(p, W, H, 3)
            diff = float(np.abs(x.astype(np.float32) - u8(pattern(W, H))[..., ::-1]).mean())
            assert diff > 2.0, "output is nearly identical to the input"
            return f"{size[0]}x{size[1]}, mean change {diff:.1f}/255"

        R.check(f"image look {look}", f)

    def alpha_case():
        p, _ = pipeline.render_image(
            presets.build(look="church-dub"), rgba, os.path.join(io, "alpha_tape.png"), quality=q
        )
        x = assert_img(p, 400, 300, 4)
        p2, _ = pipeline.render_image(
            presets.build(look="consumer-tv"), rgba, os.path.join(io, "alpha_tube.png"), quality=q
        )
        y = assert_img(p2, 400, 300, 4)
        assert x[150, 200, 3] > 240 and x[5, 5, 3] < 15, "tape alpha not preserved"
        assert y[150, 200, 3] > 200 and y[5, 5, 3] < 15, "tube alpha not carried"
        return "RGBA in, RGBA out (tape and tube)"

    R.check("image alpha", alpha_case)

    def odd_case():
        p, s = pipeline.render_image(
            presets.build(look="my-own-funeral"), odd, os.path.join(io, "odd_portrait.png"), quality=q
        )
        assert_img(p, 333, 601, 3)
        p2, _ = pipeline.render_image(
            presets.build(look="filmed-tv", frame="crop43"), odd, os.path.join(io, "odd_crop43.png"), quality=q
        )
        x = assert_img(p2)
        assert abs(x.shape[1] / x.shape[0] - 4 / 3) < 0.01
        p3, _ = pipeline.render_image(
            presets.build(look="church-dub", frame="pad43"), odd, os.path.join(io, "odd_pad43.png"), quality=q
        )
        y = assert_img(p3)
        assert abs(y.shape[1] / y.shape[0] - 4 / 3) < 0.01
        return "333x601 native, crop to 4:3, pad to 4:3"

    R.check("image odd portrait jpeg + frame modes", odd_case)

    def deep_case():
        p, _ = pipeline.render_image(
            presets.build(look="church-dub"), b16, os.path.join(io, "deep16_out.png"), quality=q
        )
        assert_img(p, 320, 240, 3, np.uint16)
        p, _ = pipeline.render_image(
            presets.build(look="consumer-tv"), gray, os.path.join(io, "gray_out.png"), quality=q
        )
        assert_img(p, 300, 200, 3)
        p, _ = pipeline.render_image(
            presets.build(look="home-camcorder"), wide, os.path.join(io, "wide_out.png"), quality=q
        )
        assert_img(p, 900, 260, 3)
        p, _ = pipeline.render_image(
            presets.build(look="my-own-funeral"), tiny, os.path.join(io, "tiny_out.jpg"), quality=q
        )
        assert_img(p, 64, 48, 3)
        p, _ = pipeline.render_image(
            presets.build(look="consumer-tv"), img, os.path.join(io, "resized.png"), height=360, quality=q
        )
        assert_img(p, 480, 360, 3)
        return "16-bit, grayscale, 900x260, 64x48, --height"

    R.check("image 16-bit, gray, wide, tiny, resize", deep_case)

    def determinism():
        c0 = presets.build(look="my-own-funeral")
        p1, _ = pipeline.render_image(c0, img, os.path.join(io, "det_a.png"), quality=q)
        p2, _ = pipeline.render_image(c0, img, os.path.join(io, "det_b.png"), quality=q)
        p3, _ = pipeline.render_image(
            presets.build(look="my-own-funeral", seed=7), img, os.path.join(io, "det_c.png"), quality=q
        )
        a1, a2, a3 = assert_img(p1), assert_img(p2), assert_img(p3)
        assert np.array_equal(a1, a2), "same seed gave different output"
        assert not np.array_equal(a1, a3), "different seeds gave the same output"
        return "seed 0 twice identical, seed 7 differs"

    R.check("determinism (images)", determinism)

    def options():
        n = 0
        base = dict(look="my-own-funeral")
        variants = [dict(mask=m) for m in presets.MASKS] + [dict(capture=c) for c in presets.CAPTURES]
        variants += [
            dict(curvature=1.0, fill=0.8),
            dict(fill=1.3),
            dict(date="JUL 4 1989", date_pos="tl"),
            dict(no_date=True),
            dict(gens=3),
            dict(tube="none"),
            dict(mix=0.5),
            dict(tape="V4"),
            dict(tape="V5"),
        ]
        variants += [dict(off=[s]) for s in presets.STAGES]
        variants += [dict(strengths={k: 0.0}) for k in presets.KNOBS] + [
            dict(strengths={k: 2.0}) for k in presets.KNOBS
        ]
        variants += [dict(sets=[("vhs.luma_tvl", "[180, 160]"), ("crt.triads_across", "420")])]
        small = os.path.join(src, "small.png")
        media.write_image(small, pattern(240, 180))
        for v in variants:
            kw = dict(base)
            kw.update(v)
            cfg = presets.build(**kw)
            p, _ = pipeline.render_image(cfg, small, os.path.join(io, "opt", f"v{n:03d}.png"), quality="draft")
            x = assert_img(p, 240, 180, 3)
            assert np.isfinite(x).all()
            n += 1
        return f"{n} option variants (masks, captures, curvature, fill, date, gens, stages off, every strength at 0 and 2, raw sets)"

    R.check("options and strengths", options)

    def previews_img():
        st = preview.load_still(img, "native")
        d = os.path.join(out, "previews_image")
        cfg = presets.build(look="my-own-funeral")
        c = preview.compare(cfg, st, os.path.join(d, "compare"), quality=q)
        lad = preview.ladder(cfg, st, os.path.join(d, "ladder"), quality=q)
        looks = None if not quick else ["my-own-funeral", "church-dub", "consumer-tv", "curved-80s-set"]
        sh = preview.sheet(st, os.path.join(d, "sheet"), looks, tile_h=180 if quick else 300, jobs=jobs)
        res = page.preview_all(img, os.path.join(d, "all"), cfg, looks=looks, jobs=jobs, clip=False)
        html = open(res["page"], encoding="utf-8").read()
        assert "http://" not in html and "https://" not in html, "page references the network"
        assert html.count("data:image/") >= 10, "page images missing"
        for k in ("split", "side_by_side", "zoom"):
            assert os.path.exists(c[k])
        for k in (
            "S0",
            "S1",
            "S2",
            "S3",
            "S4",
            "S5",
            "L0",
            "L1",
            "L2",
            "L3",
            "L4",
            "L5",
            "L6",
            "macro",
            "ladder_tape",
            "ladder_tube",
        ):
            assert os.path.exists(lad[k]), k
        assert os.path.exists(sh["sheet"])
        return f"compare, ladder (14 stages), sheet, page {os.path.getsize(res['page']) / 2**20:.1f} MiB"

    R.check("previews on an image (compare, ladder, sheet, page)", previews_img)

    # ---- video
    if not have_ff:
        R.skip("video", "ffmpeg not found")
    else:
        vw, vh = (320, 240) if quick else (480, 360)
        n = 24 if quick else 48
        cfr = os.path.join(src, "cfr_audio.mp4")
        write_video(cfr, lambda i: u8(pattern(vw, vh, i / 24)), n, vw, vh, "24", audio=True)
        vfr = os.path.join(src, "vfr.mkv")
        try:
            write_video(vfr, lambda i: u8(pattern(vw, vh, i / 24)), n, vw, vh, "24", audio=True, vfr=True)
        except RuntimeError as e:
            vfr = None
            R.skip("VFR source", str(e)[:120])
        noaud = os.path.join(src, "no_audio.mp4")
        write_video(noaud, lambda i: u8(pattern(vw, vh, i / 24)), 12, vw, vh, "30000/1001", audio=False)
        alpha_mov = os.path.join(src, "odd_alpha.mov")
        ow, oh = 181, 321

        def rgba_frame(i):
            x = u8(pattern(ow, oh, i / 24))
            al = np.full((oh, ow, 1), 255, np.uint8)
            al[: oh // 4] = 0
            return np.concatenate([x, al], -1)

        try:
            write_video(alpha_mov, rgba_frame, 12, ow, oh, "24", audio=False, pix_fmt="rgba", codec=["-c:v", "png"])
        except RuntimeError:
            alpha_mov = None
        rot = os.path.join(src, "rotated.mp4")
        rot_ok = False
        try:
            write_video(
                rot,
                lambda i: u8(pattern(320, 240, i / 24)),
                12,
                320,
                240,
                "24",
                audio=False,
                extra=["-metadata:s:v:0", "rotate=90"],
            )
            rot_ok = media.probe(rot)["rotation"] in (90, -90, 270, -270)
            if not rot_ok:
                r = subprocess.run(
                    [
                        media.ffmpeg_bin(),
                        "-v",
                        "error",
                        "-y",
                        "-display_rotation",
                        "90",
                        "-i",
                        rot,
                        "-c",
                        "copy",
                        rot + ".r.mp4",
                    ],
                    capture_output=True,
                )
                if r.returncode == 0:
                    os.replace(rot + ".r.mp4", rot)
                    rot_ok = media.probe(rot)["rotation"] in (90, -90, 270, -270)
        except RuntimeError:
            rot_ok = False
        long_n = 96 if quick else 144
        longv = os.path.join(src, "long.mp4")
        write_video(longv, lambda i: u8(pattern(256, 192, i / 24)), long_n, 256, 192, "24", audio=True)
        vo = os.path.join(out, "video")
        os.makedirs(vo, exist_ok=True)

        def v_cfr():
            r = pipeline.render_video(
                presets.build(look="my-own-funeral"), cfr, os.path.join(vo, "cfr_funeral.mp4"), quality=q, jobs=jobs
            )
            info = media.probe(r["path"])
            assert info["width"] == vw and info["height"] == vh
            assert abs(info["fps"] - 24) < 0.01 and r["frames"] == n, f"{r['frames']} frames"
            assert info["audio"], "audio missing"
            assert abs(info["duration"] - n / 24) < 0.1, f"duration {info['duration']}"
            return f"{r['frames']} frames, {info['fps']:.3f} fps, audio {r['audio']}, {r['frames'] / r['seconds']:.1f} fps render"

        R.check("video CFR + audio passthrough", v_cfr)

        if vfr:

            def v_vfr():
                si = media.probe(vfr)
                r = pipeline.render_video(
                    presets.build(look="church-dub"), vfr, os.path.join(vo, "vfr_out.mp4"), quality=q, jobs=jobs
                )
                info = media.probe(r["path"])
                assert not info["vfr"], "output is still variable frame rate"
                assert info["audio"], "audio missing"
                assert abs(info["duration"] - si["duration"]) < 3 / si["fps"] + 0.05, (
                    f"{info['duration']} vs {si['duration']}"
                )
                return f"source vfr={si['vfr']} avg {si['avg_frame_rate']} r {si['r_frame_rate']} -> constant {info['fps_str']}, {r['frames']} frames"

            R.check("video VFR source -> constant rate, audio kept", v_vfr)

        def v_noaudio():
            r = pipeline.render_video(
                presets.build(look="consumer-tv"), noaud, os.path.join(vo, "noaudio_out.mp4"), quality=q, jobs=jobs
            )
            info = media.probe(r["path"])
            assert not info["audio"] and r["frames"] == 12 and info["fps_str"] in ("30000/1001",), info["fps_str"]
            return f"no audio, 29.97 fps kept ({info['fps_str']})"

        R.check("video without audio, 29.97 fps", v_noaudio)

        if alpha_mov:

            def v_alpha():
                si = media.probe(alpha_mov)
                r = pipeline.render_video(
                    presets.build(look="filmed-tv"),
                    alpha_mov,
                    os.path.join(vo, "odd_alpha_out.mp4"),
                    quality=q,
                    jobs=jobs,
                )
                info = media.probe(r["path"])
                assert info["width"] % 2 == 0 and info["height"] % 2 == 0
                assert abs(info["width"] - ow) <= 1 and abs(info["height"] - oh) <= 1
                return f"{ow}x{oh} PNG-in-MOV with alpha={si['has_alpha']} -> {info['width']}x{info['height']} H.264"

            R.check("video odd-size portrait with alpha", v_alpha)

        if rot_ok:

            def v_rot():
                r = pipeline.render_video(
                    presets.build(look="home-camcorder"), rot, os.path.join(vo, "rotated_out.mp4"), quality=q, jobs=jobs
                )
                info = media.probe(r["path"])
                assert info["width"] == 240 and info["height"] == 320, f"{info['width']}x{info['height']}"
                return "rotation metadata honoured: 320x240 coded, 240x320 out"

            R.check("video with rotation metadata", v_rot)
        else:
            R.skip("video with rotation metadata", "this ffmpeg could not write rotation metadata")

        def v_long():
            # a 1280x720 clip whose decoded frames would need about 1.3 to 2.7 GB if held in memory, rendered in a
            # fresh process so its peak memory is its own
            secs = 10 if quick else 20
            big = os.path.join(src, "big_720p.mp4")
            enc = (
                ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
                if "libx264" in media.encoders()
                else ["-c:v", "mpeg4"]
            )
            r0 = subprocess.run(
                [
                    media.ffmpeg_bin(),
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc2=size=1280x720:rate=30:duration={secs}",
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency=330:sample_rate=48000:duration={secs}",
                ]
                + enc
                + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", big],
                capture_output=True,
            )
            assert r0.returncode == 0, r0.stderr.decode(errors="replace")[-300:]
            n_big = secs * 30
            code = (
                "import json, os, sys; sys.path.insert(0, sys.argv[1]);"
                "from tapetube import pipeline, presets;"
                "r = pipeline.render_video(presets.build(look='church-dub'), sys.argv[2], sys.argv[3], quality='draft',"
                " jobs=(int(sys.argv[4]) or None));"
                "m = {};\n"
                "try:\n import resource; m = {'self': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,"
                " 'children': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}\n"
                "except ImportError:\n pass\n"
                "print(json.dumps({'frames': r['frames'], 'mem': m}))"
            )
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            out_big = os.path.join(vo, "big_720p_out.mp4")
            r1 = subprocess.run(
                [sys.executable, "-c", code, here, big, out_big, str(jobs or 0)], capture_output=True, text=True
            )
            assert r1.returncode == 0, r1.stderr[-500:]
            res = json.loads(r1.stdout.strip().splitlines()[-1])
            assert res["frames"] == n_big, f"{res['frames']} of {n_big}"
            info = media.probe(out_big)
            assert info["audio"] and info["width"] == 1280 and info["height"] == 720
            decoded = n_big * 1280 * 720 * 3 / 2**30
            m = res["mem"]
            if m:
                unit = 2**20 if sys.platform == "darwin" else 2**10
                peak = max(m["self"], m["children"]) / unit
                assert peak < decoded * 1024 * 0.5, f"peak {peak:.0f} MiB looks like the clip is held in memory"
                return f"{n_big} frames of 1280x720 ({decoded:.1f} GiB decoded), peak process memory {peak:.0f} MiB"
            return f"{n_big} frames of 1280x720 ({decoded:.1f} GiB decoded) streamed"

        R.check("video long clip, streamed", v_long)

        def v_trim_audio_modes():
            outs = []
            for mode in ("vhs", "tv", "none", "aac"):
                r = pipeline.render_video(
                    presets.build(look="church-dub"),
                    longv,
                    os.path.join(vo, f"trim_{mode}.mp4"),
                    quality="draft",
                    start=1.0,
                    duration=1.5,
                    audio=mode,
                    jobs=jobs,
                )
                info = media.probe(r["path"])
                assert r["frames"] == 36, f"{r['frames']} frames"
                assert bool(info["audio"]) == (mode != "none")
                outs.append(f"{mode}:{r['audio']}")
            return "trim 1.0 s + 1.5 s = 36 frames; audio " + ", ".join(outs)

        R.check("video trim + audio modes", v_trim_audio_modes)

        if "prores_ks" in media.encoders():

            def v_prores():
                r = pipeline.render_video(
                    presets.build(look="church-dub"),
                    noaud,
                    os.path.join(vo, "prores.mov"),
                    quality="draft",
                    codec="prores",
                    jobs=jobs,
                )
                assert media.probe(r["path"])["codec"] == "prores"
                return "ProRes 422 HQ"

            R.check("video ProRes", v_prores)

        def v_det():
            c = presets.build(look="my-own-funeral")
            a1 = pipeline.render_video(c, noaud, os.path.join(vo, "det1.mp4"), quality="draft", jobs=jobs)
            a2 = pipeline.render_video(c, noaud, os.path.join(vo, "det2.mp4"), quality="draft", jobs=1)
            f1, f2 = decode_all(a1["path"]), decode_all(a2["path"])
            assert np.array_equal(f1, f2), f"max diff {np.abs(f1.astype(int) - f2.astype(int)).max()}"
            return "same frames with several workers and with one"

        R.check("determinism (video, any worker count)", v_det)

        def v_previews():
            d = os.path.join(out, "previews_video")
            cl = preview.clip(
                presets.build(look="filmed-tv"),
                longv,
                os.path.join(d, "clip_sbs.mp4"),
                start=0.5,
                duration=1.0,
                height=192,
                side_by_side=True,
                jobs=jobs,
            )
            info = media.probe(cl["path"])
            assert info["width"] == 512 and info["height"] == 192, f"{info['width']}x{info['height']}"
            looks = ["my-own-funeral", "church-dub", "consumer-tv"] if quick else None
            res = page.preview_all(
                longv, os.path.join(d, "all"), presets.build(look="my-own-funeral"), looks=looks, t=2.0, jobs=jobs
            )
            html = open(res["page"], encoding="utf-8").read()
            assert "data:video/mp4;base64," in html, "clip not embedded"
            assert "http://" not in html and "https://" not in html
            return f"side-by-side clip {info['width']}x{info['height']}, preview folder with embedded clip"

        R.check("previews on a video (clip, page with clip)", v_previews)

        def v_rewind():
            r = rewind_cmd.render(
                presets.build(look="my-own-funeral"),
                longv,
                os.path.join(vo, "rewind.mp4"),
                3.5,
                0.5,
                1.0,
                quality="draft",
                jobs=jobs,
            )
            assert r["frames"] == 24, r["frames"]
            return "1 s rewind search from 3.5 s back to 0.5 s"

        R.check("rewind effect", v_rewind)

    ok = all(r["ok"] is not False for r in R.rows)
    report = {
        "ok": ok,
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "opencv": cv2.__version__,
        "ffmpeg": subprocess.run([media.ffmpeg_bin(), "-version"], capture_output=True, text=True).stdout.splitlines()[
            0
        ]
        if have_ff
        else None,
        "quick": quick,
        "out": out,
        "results": R.rows,
    }
    with open(os.path.join(out, "selftest_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    n_ok = sum(1 for r in R.rows if r["ok"])
    n_fail = sum(1 for r in R.rows if r["ok"] is False)
    n_skip = sum(1 for r in R.rows if r["ok"] is None)
    print(f"\n{n_ok} passed, {n_fail} failed, {n_skip} skipped. Report: {os.path.join(out, 'selftest_report.json')}")
    return ok
