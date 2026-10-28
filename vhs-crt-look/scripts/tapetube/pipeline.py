"""From a render config to finished frames: geometry, the tape, the tube, and parallel streaming for video."""

from __future__ import annotations

import math
import os
import sys
import tempfile
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

from . import crt, media, vhs

# standard renders the tube at the output size; high renders it at 2x and downsamples (as the reference renders did). draft and
# final are accepted as aliases.
QUALITY_SS = {"standard": 1, "draft": 1, "high": 2, "final": 2}


# --------------------------------------------------------------------------------------------- geometry
def output_size(src_w: int, src_h: int, frame: str, width=None, height=None, even=False) -> Tuple[int, int]:
    aspect = src_w / src_h if frame == "native" else 4.0 / 3.0
    if width and height:
        w, h = int(width), int(height)
    elif width:
        w = int(width)
        h = int(round(w / aspect))
    elif height:
        h = int(height)
        w = int(round(h * aspect))
    else:
        h = src_h
        w = src_w if frame == "native" else int(round(h * aspect))
    if even:
        w, h = max(2, w // 2 * 2), max(2, h // 2 * 2)
    return max(1, w), max(1, h)


def frame_transform(img: np.ndarray, frame: str, fill_value=0.0) -> np.ndarray:
    """The source framed as the tape will see it: native aspect, centre crop to 4:3, or padded to 4:3."""
    h, w = img.shape[:2]
    if frame == "native" or abs(w / h - 4 / 3) < 1e-3:
        return img
    if frame == "crop43":
        if w / h > 4 / 3:
            nw = int(round(h * 4 / 3))
            return img[:, (w - nw) // 2 : (w - nw) // 2 + nw]
        nh = int(round(w * 3 / 4))
        return img[(h - nh) // 2 : (h - nh) // 2 + nh]
    if w / h > 4 / 3:
        nh = int(round(w * 3 / 4))
        pad = ((nh - h) // 2, nh - h - (nh - h) // 2)
        return np.pad(img, (pad, (0, 0)) + ((0, 0),) * (img.ndim - 2), constant_values=fill_value)
    nw = int(round(h * 4 / 3))
    pad = ((nw - w) // 2, nw - w - (nw - w) // 2)
    return np.pad(img, ((0, 0), pad) + ((0, 0),) * (img.ndim - 2), constant_values=fill_value)


def resize_to(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ih, iw = img.shape[:2]
    if (iw, ih) == (w, h):
        return img
    interp = cv2.INTER_AREA if (w < iw and h < ih) else cv2.INTER_CUBIC
    return cv2.resize(img, (w, h), interpolation=interp)


def as_float(img: np.ndarray) -> np.ndarray:
    return img.astype(np.float32) / 255.0 if img.dtype == np.uint8 else img.astype(np.float32)


def to_u8(rgb: np.ndarray) -> np.ndarray:
    return (np.clip(rgb, 0, 1) * 255).round().astype(np.uint8)


# --------------------------------------------------------------------------------------------- renderer
class Renderer:
    """Renders frames for one config at one output size. Source frames come already framed (native / crop / pad)."""

    def __init__(self, cfg: dict, out_w: int, out_h: int, fps: float = 24.0, quality: str = "final", reflection=None):
        self.cfg, self.out_w, self.out_h, self.fps = cfg, out_w, out_h, float(fps)
        self.ss = QUALITY_SS.get(quality, 1) if isinstance(quality, str) else int(quality)
        self.cw = vhs.raster_width(out_w / out_h)
        self.reflection = reflection

    def cam_raster(self, img: np.ndarray) -> np.ndarray:
        return np.clip(resize_to(as_float(img), self.cw, vhs.CH), 0, 1)

    def signal(self, hist: List[np.ndarray], i: int, snaps=None, post=None, stages=None) -> np.ndarray:
        cam = [self.cam_raster(h) for h in hist]
        st = stages if stages is not None else self.cfg["stages"]
        return vhs.vhs_signal(cam, self.cfg["vhs"], i, self.fps, self.cfg["seed"], st, snaps, post)

    def tube_on(self, layer: int = 6) -> dict:
        st = self.cfg["stages"]
        return {name: bool(st.get(name, True)) and layer >= k for k, name in enumerate(crt.LAYER_NAMES) if k > 0}

    def show(self, sig: np.ndarray, i: int, alpha_tape=None, layer: int = 6, capture: Optional[str] = None):
        """The tape signal as the chosen capture shows it: (rgb float, alpha or None) at the output size."""
        capture = capture or self.cfg["capture"]
        if capture == "direct":
            rgb = np.clip(cv2.resize(sig, (self.out_w, self.out_h), interpolation=cv2.INTER_CUBIC), 0, 1)
            a = None
            if alpha_tape is not None:
                a = np.clip(cv2.resize(alpha_tape, (self.out_w, self.out_h), interpolation=cv2.INTER_LINEAR), 0, 1)
            return rgb, a
        seed = self.cfg["seed"]
        grain = np.random.default_rng([seed, 40_000 + i])
        on = self.tube_on(layer)
        if capture == "screen":
            on["camera"] = False
        return crt.render(
            sig,
            self.cfg["crt"],
            self.cfg["tube"],
            self.cfg["camera"],
            self.out_w,
            self.out_h,
            t=i / self.fps,
            parity=i % 2,
            on=on,
            ss=self.ss,
            alpha=alpha_tape,
            reflection=self.reflection,
            grain_rng=grain,
        )

    def frame(self, hist: List[np.ndarray], i: int, alpha=None, src_for_mix=None, post=None):
        """hist: [frame i, i-1, i-2, i-3] (any size, already framed). Returns (rgb float, alpha or None)."""
        sig = self.signal(hist, i, post=post)
        a_t = None
        if alpha is not None:
            a_t = cv2.resize(alpha.astype(np.float32), (sig.shape[1], sig.shape[0]), interpolation=cv2.INTER_AREA)
        rgb, a = self.show(sig, i, a_t)
        mix = self.cfg.get("mix", 1.0)
        if mix < 1.0:
            src = resize_to(as_float(src_for_mix if src_for_mix is not None else hist[0]), self.out_w, self.out_h)
            rgb = mix * rgb + (1 - mix) * np.clip(src, 0, 1)
        return rgb, a


def history_needed(cfg: dict) -> int:
    return 4 if cfg["vhs"].get("tube_lag", 0) > 0 and cfg["stages"].get("camcorder", True) else 1


def load_reflection(path: Optional[str]):
    if not path:
        return None
    rgb, _, _ = media.read_image(path)
    return np.clip(rgb, 0, 1) ** 2.2


# --------------------------------------------------------------------------------------------- images
def render_image(
    cfg: dict,
    src_path: str,
    out_path: str,
    width=None,
    height=None,
    quality="final",
    frame_index=0,
    reflection=None,
    alpha_bg=(0, 0, 0),
):
    rgb, alpha, bits = media.read_image(src_path)
    if alpha is not None:  # transparent pixels carry no picture: composite over a background before the tape
        rgb = rgb * alpha[..., None] + np.array(alpha_bg, np.float32) * (1 - alpha[..., None])
    rgb = frame_transform(rgb, cfg["frame"])
    if alpha is not None:
        alpha = frame_transform(alpha, cfg["frame"], fill_value=1.0)
    ow, oh = output_size(rgb.shape[1], rgb.shape[0], "native", width, height)
    R = Renderer(cfg, ow, oh, quality=quality, reflection=load_reflection(reflection))
    hist = [rgb] * history_needed(cfg)
    out, a = R.frame(hist, frame_index, alpha=alpha)
    media.write_image(out_path, out, a, bits=bits)
    return out_path, (ow, oh)


# --------------------------------------------------------------------------------------------- video
_W = {}


def _init_worker(cfg, out_w, out_h, fps, quality, reflection_path, post_kind, post_args):
    sys.dont_write_bytecode = True
    _W["R"] = Renderer(cfg, out_w, out_h, fps, quality, load_reflection(reflection_path))
    _W["post"] = (post_kind, post_args)


def _post_fn(i):
    kind, args = _W.get("post", (None, None))
    if kind == "rewind":
        from . import rewind

        return rewind.search_post(args["speed"][i])
    return None


def _work(job):
    i, hist, mix_src = job
    R = _W["R"]
    rgb, _ = R.frame(hist, i, src_for_mix=mix_src, post=_post_fn(i))
    return i, to_u8(rgb)


def default_jobs() -> int:
    n = os.cpu_count() or 2
    return max(1, min(n - 1 if n > 2 else n, 8))


def render_video(
    cfg: dict,
    src_path: str,
    out_path: str,
    width=None,
    height=None,
    quality="standard",
    start=None,
    duration=None,
    fps=None,
    jobs=None,
    audio="copy",
    codec="h264",
    crf=16,
    reflection=None,
    progress: Optional[Callable[[int, Optional[int], float], None]] = None,
    frame_source=None,
    post=None,
    total=None,
):
    """Stream the video through the look: ffmpeg decode -> worker processes -> ffmpeg encode, in order, with at most
    a few frames in flight; then the source audio is put back under it (same trim).
    frame_source/post/total: used by the rewind effect (a precomputed frame order and the search effect)."""
    media.need_ffmpeg()
    info = media.probe(src_path)
    fps_str = info["fps_str"]
    if fps:
        from fractions import Fraction

        f = Fraction(str(fps)).limit_denominator(1001)
        fps_str = f"{f.numerator}/{f.denominator}"
    fps_f = eval_fps(fps_str)
    dw, dh = info["width"], info["height"]
    fw, fh = (dw, dh) if cfg["frame"] == "native" else output_size(dw, dh, cfg["frame"])
    ow, oh = output_size(fw, fh, "native", width, height, even=True)
    mix = cfg.get("mix", 1.0) < 1.0
    cw = vhs.raster_width(ow / oh)
    dec_w, dec_h = (ow, oh) if mix else (cw, vhs.CH)
    hist_n = history_needed(cfg)
    if total is None and info.get("duration"):
        d = duration if duration else max(0.0, info["duration"] - (start or 0))
        total = int(math.floor(d * fps_f + 1e-6))
    jobs = jobs or default_jobs()
    tmp_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(tmp_dir, exist_ok=True)
    ext = os.path.splitext(out_path)[1] or ".mp4"
    fd, tmp = tempfile.mkstemp(prefix=".vhslook_", suffix=ext, dir=tmp_dir)
    os.close(fd)
    writer = media.VideoWriter(tmp, ow, oh, fps_str, codec=codec, crf=crf)
    if frame_source is None:
        reader = media.VideoReader(src_path, info, dec_w, dec_h, cfg["frame"], start, duration, fps_str)
        i0 = int(round((start or 0) * fps_f))  # absolute frame numbers: a trimmed preview has the full render's noise
        frame_source = ((i0 + i, fr) for i, fr in enumerate(reader))
    t0 = time.time()
    n_done = 0
    hist: deque = deque(maxlen=hist_n)
    post_args = post or {}
    try:
        with ProcessPoolExecutor(
            jobs,
            initializer=_init_worker,
            initargs=(cfg, ow, oh, fps_f, quality, reflection, "rewind" if post else None, post_args),
        ) as ex:
            pending: deque = deque()
            for i, fr in frame_source:
                hist.appendleft(fr if not mix else resize_to(fr, cw, vhs.CH))
                h = list(hist) + [hist[-1]] * (hist_n - len(hist))
                pending.append(ex.submit(_work, (i, h, fr if mix else None)))
                while len(pending) >= jobs * 2:
                    _, u8 = pending.popleft().result()
                    writer.write(u8)
                    n_done += 1
                    if progress:
                        progress(n_done, total, time.time() - t0)
            while pending:
                _, u8 = pending.popleft().result()
                writer.write(u8)
                n_done += 1
                if progress:
                    progress(n_done, total, time.time() - t0)
        writer.close()
    except BaseException:
        try:
            writer.proc.kill()
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        raise
    if n_done == 0:
        os.remove(tmp)
        raise media.MediaError("no frames were decoded (check --start / --duration)")
    length = n_done / fps_f
    a_mode = media.mux_audio(
        tmp,
        src_path,
        out_path,
        start if not post else None,
        duration if not post else None,
        "none" if post else audio,
        length=length,
    )
    return {
        "path": out_path,
        "size": (ow, oh),
        "frames": n_done,
        "fps": fps_str,
        "seconds": time.time() - t0,
        "audio": a_mode,
        "vfr_source": info["vfr"],
    }


def eval_fps(s: str) -> float:
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b)
    return float(s)
