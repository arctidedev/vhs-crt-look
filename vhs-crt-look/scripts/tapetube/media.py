"""Media in and out: images through OpenCV, video and audio through ffmpeg pipes (streamed, never all in memory)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from fractions import Fraction
from typing import Iterator, Optional, Tuple

import cv2
import numpy as np

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".exr", ".jp2", ".pgm", ".ppm"}
VIDEO_EXT = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".mts",
    ".m2ts",
    ".wmv",
    ".flv",
    ".gif",
    ".3gp",
    ".ogv",
}


class MediaError(RuntimeError):
    pass


def ffmpeg_bin() -> Optional[str]:
    return os.environ.get("VHSLOOK_FFMPEG") or shutil.which("ffmpeg")


def ffprobe_bin() -> Optional[str]:
    if os.environ.get("VHSLOOK_FFPROBE"):
        return os.environ["VHSLOOK_FFPROBE"]
    p = shutil.which("ffprobe")
    if p:
        return p
    f = ffmpeg_bin()
    if f:
        cand = os.path.join(os.path.dirname(f), "ffprobe" + (".exe" if f.lower().endswith(".exe") else ""))
        if os.path.exists(cand):
            return cand
    return None


def ff() -> str:
    need_ffmpeg()
    return ffmpeg_bin() or "ffmpeg"


def fp() -> str:
    need_ffmpeg()
    return ffprobe_bin() or "ffprobe"


def need_ffmpeg():
    if not ffmpeg_bin() or not ffprobe_bin():
        raise MediaError(
            "ffmpeg and ffprobe are needed for video. Install: macOS 'brew install ffmpeg'; Windows 'winget install "
            "Gyan.FFmpeg'; Debian/Ubuntu 'sudo apt install ffmpeg'; conda 'conda install -c conda-forge ffmpeg'. "
            "Or point VHSLOOK_FFMPEG / VHSLOOK_FFPROBE at the binaries. Images work without it."
        )


def kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    return "unknown"


# ------------------------------------------------------------------------------------------------- images
def read_image(path: str) -> Tuple[np.ndarray, Optional[np.ndarray], int]:
    """RGB float32 0..1, alpha float32 0..1 (or None) and the source bit depth (8 or 16)."""
    if not os.path.exists(path):
        raise MediaError(f"file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    data = np.fromfile(path, np.uint8)  # works with non-ASCII paths on Windows
    flag = cv2.IMREAD_COLOR if ext in (".jpg", ".jpeg") else cv2.IMREAD_UNCHANGED  # JPEG: honour EXIF rotation
    img = cv2.imdecode(data, flag)
    if img is None:
        img = _ffmpeg_decode_image(path)
    bits = 16 if img.dtype == np.uint16 else 8
    scale = 65535.0 if img.dtype == np.uint16 else (1.0 if img.dtype.kind == "f" else 255.0)
    img = img.astype(np.float32) / scale
    if img.ndim == 2:
        img = img[..., None]
    alpha = None
    c = img.shape[2]
    if c == 1:
        rgb = np.repeat(img, 3, axis=2)
    elif c == 2:
        rgb, alpha = np.repeat(img[..., :1], 3, axis=2), img[..., 1]
    elif c == 3:
        rgb = img[..., ::-1]
    else:
        rgb, alpha = img[..., 2::-1], img[..., 3]
    return np.ascontiguousarray(np.clip(rgb, 0, 1)), alpha, bits


def _ffmpeg_decode_image(path: str) -> np.ndarray:
    ff = ffmpeg_bin()
    if not ff:
        raise MediaError(f"OpenCV cannot read {path} and ffmpeg is not installed to try instead")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "x.png")
        r = subprocess.run([ff, "-v", "error", "-y", "-i", path, "-frames:v", "1", out], capture_output=True)
        if r.returncode or not os.path.exists(out):
            raise MediaError(f"cannot read image {path}: {r.stderr.decode(errors='replace').strip()[-300:]}")
        img = cv2.imdecode(np.fromfile(out, np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise MediaError(f"cannot read image {path}")
        return img


def write_image(path: str, rgb: np.ndarray, alpha: Optional[np.ndarray] = None, bits: int = 8, quality: int = 95):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    ext = os.path.splitext(path)[1].lower() or ".png"
    if ext in (".jpg", ".jpeg", ".bmp"):
        alpha, bits = None, 8
    if ext not in (".png", ".tif", ".tiff"):
        bits = 8
    mx = 65535.0 if bits == 16 else 255.0
    dt = np.uint16 if bits == 16 else np.uint8
    bgr = np.clip(rgb, 0, 1)[..., ::-1]
    if alpha is not None:
        bgr = np.concatenate([bgr, np.clip(alpha, 0, 1)[..., None]], -1)
    arr = (bgr * mx).round().astype(dt)
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext in (".jpg", ".jpeg") else []
    if ext == ".png":
        params = [cv2.IMWRITE_PNG_COMPRESSION, 6]
    ok, buf = cv2.imencode(ext, arr, params)
    if not ok:
        raise MediaError(f"cannot write {path}")
    buf.tofile(path)
    return path


# ------------------------------------------------------------------------------------------------- probing
def _run_json(cmd):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise MediaError(r.stderr.decode(errors="replace").strip()[-400:] or "ffprobe failed")
    return json.loads(r.stdout.decode("utf-8", errors="replace") or "{}")


def _frac(s) -> Optional[Fraction]:
    try:
        f = Fraction(str(s))
        return f if f > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def probe(path: str) -> dict:
    """Video facts: display size (rotation and pixel aspect applied), frame rates, VFR, duration, audio, alpha."""
    need_ffmpeg()
    if not os.path.exists(path):
        raise MediaError(f"file not found: {path}")
    j = _run_json([fp(), "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    vs = [
        s
        for s in j.get("streams", [])
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
    ]
    if not vs:
        raise MediaError(f"no video stream in {path}")
    v = vs[0]
    w, h = int(v["width"]), int(v["height"])
    sar = _frac(v.get("sample_aspect_ratio", "1:1").replace(":", "/")) or Fraction(1)
    rot = 0
    try:
        rot = int(float(v.get("tags", {}).get("rotate", 0)))
    except ValueError:
        pass
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    dw = int(round(w * sar)) if sar != 1 else w
    dh = h
    if abs(rot) % 180 == 90:
        dw, dh = dh, dw
    avg = _frac(v.get("avg_frame_rate"))
    rr = _frac(v.get("r_frame_rate"))
    fps = avg or rr or Fraction(24)
    if fps > 240:  # bogus timebase-derived rates
        fps = rr if rr and rr <= 240 else Fraction(30)
    vfr = bool(avg and rr and abs(float(avg) - float(rr)) / float(rr) > 0.01)
    dur = None
    for src in (v.get("duration"), j.get("format", {}).get("duration")):
        try:
            dur = float(src)
            break
        except (TypeError, ValueError):
            continue
    aud = [s for s in j.get("streams", []) if s.get("codec_type") == "audio"]
    pix = v.get("pix_fmt", "")
    return {
        "path": path,
        "width": dw,
        "height": dh,
        "coded_width": w,
        "coded_height": h,
        "rotation": rot,
        "sar": str(sar),
        "fps": float(fps),
        "fps_str": f"{fps.numerator}/{fps.denominator}",
        "r_frame_rate": v.get("r_frame_rate"),
        "avg_frame_rate": v.get("avg_frame_rate"),
        "vfr": vfr,
        "duration": dur,
        "frames": int(round(dur * float(fps))) if dur else None,
        "codec": v.get("codec_name"),
        "pix_fmt": pix,
        "has_alpha": any(x in pix for x in ("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya")),
        "color_space": v.get("color_space"),
        "audio": [
            {"codec": a.get("codec_name"), "channels": a.get("channels"), "rate": a.get("sample_rate")} for a in aud
        ],
    }


# ------------------------------------------------------------------------------------------------- video io
def decode_filter(info: dict, out_w: int, out_h: int, frame: str, fps_str: str) -> str:
    """ffmpeg filter chain: constant frame rate, square pixels, the frame mode (native / crop to 4:3 / pad to 4:3),
    then the working size."""
    dw, dh = info["width"], info["height"]
    f = [f"fps={fps_str}"]
    cm = ""
    if not info.get("color_space") or info.get("color_space") in ("unknown", "reserved"):
        cm = ":in_color_matrix=" + ("bt709" if max(dw, dh) >= 720 else "bt601")
    f.append(f"scale={dw}:{dh}:flags=bicubic{cm}")
    if frame == "crop43" and abs(dw / dh - 4 / 3) > 1e-3:
        if dw / dh > 4 / 3:
            nw = int(round(dh * 4 / 3))
            f.append(f"crop={nw}:{dh}:{(dw - nw) // 2}:0")
        else:
            nh = int(round(dw * 3 / 4))
            f.append(f"crop={dw}:{nh}:0:{(dh - nh) // 2}")
    elif frame == "pad43" and abs(dw / dh - 4 / 3) > 1e-3:
        if dw / dh > 4 / 3:
            nh = int(round(dw * 3 / 4))
            f.append(f"pad={dw}:{nh}:0:{(nh - dh) // 2}:black")
        else:
            nw = int(round(dh * 4 / 3))
            f.append(f"pad={nw}:{dh}:{(nw - dw) // 2}:0:black")
    f.append(f"scale={out_w}:{out_h}:flags=area")
    f.append("format=rgb24")
    return ",".join(f)


class VideoReader:
    """Frames as uint8 RGB (h, w, 3), streamed from ffmpeg at a constant frame rate."""

    def __init__(self, path, info, out_w, out_h, frame="native", start=None, duration=None, fps_str=None):
        need_ffmpeg()
        self.w, self.h = out_w, out_h
        cmd = [ff(), "-v", "error", "-nostdin"]
        if start:
            cmd += ["-ss", f"{float(start):.6f}"]
        if duration:
            cmd += ["-t", f"{float(duration):.6f}"]
        cmd += [
            "-i",
            path,
            "-map",
            "0:v:0",
            "-vf",
            decode_filter(info, out_w, out_h, frame, fps_str or info["fps_str"]),
        ]
        cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.err = tempfile.TemporaryFile()  # a file, not a pipe: a chatty ffmpeg can never block on stderr
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=self.err, bufsize=out_w * out_h * 3 * 2)
        assert self.proc.stdout is not None
        self.out = self.proc.stdout

    def __iter__(self) -> Iterator[np.ndarray]:
        n = self.w * self.h * 3
        complete = False
        try:
            while True:
                buf = self.out.read(n)
                if len(buf) < n:
                    complete = True
                    break
                yield np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        finally:
            self.close(check=complete)

    def close(self, check: bool = True):
        """Stop ffmpeg (killed if the caller stopped reading early) and report a decode error if it failed."""
        if self.proc.poll() is None and not check:
            self.proc.kill()
        self.out.close()
        self.proc.wait()
        self.err.seek(0)
        err = self.err.read().decode(errors="replace")
        self.err.close()
        if check and self.proc.returncode not in (0, None) and err.strip():
            raise MediaError("ffmpeg decode failed: " + err.strip()[-400:])


def encoders() -> set:
    ff = ffmpeg_bin()
    if not ff:
        return set()
    r = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True)
    names = set()
    for line in r.stdout.decode(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6:
            names.add(parts[1])
    return names


def video_codec_args(codec: str, crf: int, enc: Optional[set] = None) -> list:
    enc = encoders() if enc is None else enc
    if codec == "prores":
        if "prores_ks" not in enc:
            raise MediaError("this ffmpeg has no ProRes encoder (prores_ks)")
        return ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-vendor", "apl0"]
    if "libx264" in enc:
        return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-tune", "film"]
    if "libopenh264" in enc:
        return ["-c:v", "libopenh264", "-b:v", "12M", "-pix_fmt", "yuv420p"]
    if "h264_videotoolbox" in enc:
        return ["-c:v", "h264_videotoolbox", "-b:v", "16M", "-pix_fmt", "yuv420p"]
    return ["-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p"]


class VideoWriter:
    def __init__(self, path, w, h, fps_str, codec="h264", crf=16):
        need_ffmpeg()
        self.path = path
        args = video_codec_args(codec, crf)
        vf = "scale=out_color_matrix=bt709:out_range=tv"
        cmd = [
            ff(),
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            fps_str,
        ]
        cmd += ["-i", "-", "-vf", vf] + args
        cmd += ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
        if path.lower().endswith((".mp4", ".mov", ".m4v")):
            cmd += ["-movflags", "+faststart"]
        cmd += [path]
        self.err = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self.err)
        assert self.proc.stdin is not None
        self.inp = self.proc.stdin
        self.n = 0

    def write(self, rgb_u8: np.ndarray):
        try:
            self.inp.write(np.ascontiguousarray(rgb_u8).tobytes())
        except OSError:  # ffmpeg stopped (BrokenPipeError on POSIX, EINVAL on Windows): report its own message
            self.close()
            raise MediaError("ffmpeg stopped accepting frames")
        self.n += 1

    def close(self):
        try:
            self.inp.close()
        except OSError:
            pass
        self.proc.wait()
        self.err.seek(0)
        err = self.err.read().decode(errors="replace")
        self.err.close()
        if self.proc.returncode:
            raise MediaError("ffmpeg encode failed: " + err.strip()[-400:])


AUDIO_FILTERS = {
    # the camcorder's linear audio track: 100 Hz to 8 kHz, its AGC, a little wow and flutter and tape hiss
    "vhs": "highpass=f=100:poles=2,highpass=f=100:poles=2,lowpass=f=8000:poles=2,lowpass=f=8000:poles=2,"
    "acompressor=threshold=0.125:ratio=3:attack=20:release=300:makeup=1.6,vibrato=f=0.7:d=0.004",
    # the same, then out of a TV's small speaker
    "tv": "highpass=f=100:poles=2,lowpass=f=8000:poles=2,acompressor=threshold=0.125:ratio=3:attack=20:release=300:makeup=1.6,"
    "vibrato=f=0.7:d=0.004,highpass=f=180:poles=2,lowpass=f=5500:poles=2,equalizer=f=1200:t=q:w=1.2:g=4",
}


def mux_audio(video_only: str, src: str, out: str, start=None, duration=None, mode: str = "copy", length=None) -> str:
    """Put the source's audio (same trim) under the rendered picture. mode: copy (untouched when the container
    allows it), aac, vhs, tv, none."""
    need_ffmpeg()
    info = probe(src)
    if mode == "none" or not info["audio"]:
        shutil.move(video_only, out)
        return "none" if mode == "none" else "no audio in source"
    trim = []
    if start:
        trim += ["-ss", f"{float(start):.6f}"]
    if duration:
        trim += ["-t", f"{float(duration):.6f}"]
    base = [ff(), "-v", "error", "-y", "-i", video_only] + trim + ["-i", src, "-map", "0:v:0", "-map", "1:a:0?"]
    base += ["-c:v", "copy"]
    if length:
        base += ["-t", f"{float(length):.6f}"]
    if out.lower().endswith((".mp4", ".mov", ".m4v")):
        base += ["-movflags", "+faststart"]
    attempts = []
    if mode == "copy" and not trim:
        attempts.append(("copy", ["-c:a", "copy"]))
    if mode in ("vhs", "tv"):
        attempts.append((mode, ["-af", AUDIO_FILTERS[mode], "-c:a", "aac", "-b:a", "192k"]))
    attempts.append(("aac", ["-c:a", "aac", "-b:a", "256k"]))
    last = ""
    for label, a in attempts:
        r = subprocess.run(base + a + [out], capture_output=True)
        if r.returncode == 0:
            os.remove(video_only)
            return label
        last = r.stderr.decode(errors="replace").strip()[-300:]
    raise MediaError("audio mux failed: " + last)


def extract_frames(path: str, info: dict, t: float, count: int, out_w: int, out_h: int, frame: str = "native"):
    """`count` consecutive frames ending at time t (earliest first), uint8 RGB at out_w x out_h."""
    fps = info["fps"]
    t0 = max(0.0, t - (count - 1) / fps)
    dur = info.get("duration") or 0
    if dur:
        t0 = min(t0, max(0.0, dur - count / fps - 0.05))
    frames = list(VideoReader(path, info, out_w, out_h, frame, start=t0, duration=(count + 1) / fps))
    if not frames:
        frames = list(VideoReader(path, info, out_w, out_h, frame, start=0, duration=(count + 1) / fps))
    if not frames:
        raise MediaError(f"could not decode a frame at {t:.2f} s from {path}")
    frames = frames[:count]
    while len(frames) < count:
        frames.insert(0, frames[0])
    return frames
