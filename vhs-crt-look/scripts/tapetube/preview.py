"""Previews on the user's own media before a final render: split and side-by-side stills, a stage ladder (each
stage added cumulatively), preset contact sheets and short preview clips. The HTML page lives in page.py."""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Optional, TypedDict

import cv2
import numpy as np

from . import media, osd, pipeline, presets, vhs

BG = np.array([0.055, 0.055, 0.052], np.float32)


class Still(TypedDict):
    """One source moment: the frame and the three before it (the camcorder's tube lag), already framed."""

    hist: List[np.ndarray]
    alpha: Optional[np.ndarray]
    w: int
    h: int
    kind: str
    t: float
    fps: float
    index: int
DIM = np.array([0.62, 0.62, 0.59], np.float32)


# ------------------------------------------------------------------------------------------------ sources
def load_still(path: str, frame: str, t: Optional[float] = None, max_h: int = 1440) -> Still:
    """The source still (framed for the tape) and the history the camcorder needs, as float RGB.
    Returns dict(hist=[frame t, t-1, t-2, t-3], alpha, w, h, kind, t, fps)."""
    k = media.kind(path)
    if k == "image":
        rgb, alpha, _ = media.read_image(path)
        if alpha is not None:
            rgb = rgb * alpha[..., None]
        rgb = pipeline.frame_transform(rgb, frame)
        if alpha is not None:
            alpha = pipeline.frame_transform(alpha, frame, 1.0)
        h, w = rgb.shape[:2]
        if h > max_h:
            nw = int(round(w * max_h / h))
            rgb = cv2.resize(rgb, (nw, max_h), interpolation=cv2.INTER_AREA)
            alpha = None if alpha is None else cv2.resize(alpha, (nw, max_h), interpolation=cv2.INTER_AREA)
        return Still(hist=[rgb] * 4, alpha=alpha, w=rgb.shape[1], h=rgb.shape[0], kind="image", t=0.0, fps=24.0, index=0)
    info = media.probe(path)
    fw, fh = (
        (info["width"], info["height"])
        if frame == "native"
        else pipeline.output_size(info["width"], info["height"], frame)
    )
    if fh > max_h:
        fw, fh = int(round(fw * max_h / fh)), max_h
    fw, fh = max(2, fw // 2 * 2), max(2, fh // 2 * 2)
    if t is None:
        t = (info.get("duration") or 0) * 0.4
    frames = media.extract_frames(path, info, t, 4, fw, fh, frame)
    hist = [pipeline.as_float(f) for f in frames[::-1]]
    return Still(
        hist=hist, alpha=None, w=fw, h=fh, kind="video", t=t, fps=info["fps"], index=int(round(t * info["fps"]))
    )


def preview_size(src_w: int, src_h: int, height: Optional[int], default_h: int = 1080):
    h = height or min(src_h, default_h)
    return pipeline.output_size(src_w, src_h, "native", height=h)


def render_still(cfg: dict, still: Still, w: int, h: int, quality="final", layer=6, snaps=None, reflection=None):
    R = pipeline.Renderer(cfg, w, h, still["fps"], quality, reflection)
    i = still["index"]
    if snaps is None and layer >= 6:
        rgb, _ = R.frame(still["hist"], i, alpha=still["alpha"])
        return rgb
    sig = R.signal(still["hist"], i, snaps=snaps)
    return R.show(sig, i, layer=layer)[0]


def src_at(still: Still, w: int, h: int) -> np.ndarray:
    return np.clip(pipeline.resize_to(still["hist"][0], w, h), 0, 1)


# ------------------------------------------------------------------------------------------------ labels
def cell_for(width: int) -> int:
    return max(2, int(round(width / 330)))


def band(width: int, rows: List[tuple], cell: int, pad: Optional[int] = None) -> np.ndarray:
    """A dark caption band: rows = [(text, 'title'|'dim')], OSD lettering."""
    pad = pad if pad is not None else cell * 4
    line_h = cell * 7 + cell * 4
    hgt = pad * 2 + line_h * len(rows) - cell * 4
    img = np.empty((hgt, width, 3), np.float32)
    img[:] = BG
    y = pad
    for text, style in rows:
        maxc = max(4, int((width - 2 * pad) / (6 * cell)))
        text = text.upper()
        if len(text) > maxc:
            text = text[: maxc - 1].rstrip() + "."
        ink = osd.INK if style == "title" else DIM
        img = osd.draw_lines(img, [(text, pad, y, cell)], ink=ink, edge_k=0.0, soft=0.0)
        y += line_h
    return img


def captioned(img: np.ndarray, rows: List[tuple], cell: Optional[int] = None) -> np.ndarray:
    cell = cell or cell_for(img.shape[1])
    return np.concatenate([img, band(img.shape[1], rows, cell)], 0)


def grid(tiles: List[np.ndarray], cols: int, gap: int = 6) -> np.ndarray:
    th = max(t.shape[0] for t in tiles)
    tw = max(t.shape[1] for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    out = np.empty((rows * th + (rows + 1) * gap, cols * tw + (cols + 1) * gap, 3), np.float32)
    out[:] = BG * 0.6
    for n, t in enumerate(tiles):
        r, c = divmod(n, cols)
        y, x = gap + r * (th + gap), gap + c * (tw + gap)
        out[y : y + t.shape[0], x : x + t.shape[1]] = t
    return out


def save(path: str, rgb: np.ndarray) -> str:
    return media.write_image(path, rgb, quality=92)


# ------------------------------------------------------------------------------------------------ compare
def compare(
    cfg: dict, still: Still, out_dir: str, height=None, quality="final", reflection=None, look_rgb=None
) -> Dict[str, str]:
    """split.png (original left, the look right), side_by_side.png, zoom.png (centre crops at 2x pixels)."""
    os.makedirs(out_dir, exist_ok=True)
    w, h = preview_size(still["w"], still["h"], height)
    after = look_rgb if look_rgb is not None else render_still(cfg, still, w, h, quality, reflection=reflection)
    before = src_at(still, w, h)
    cell = cell_for(w)
    name = cfg["title"]
    split = before.copy()
    split[:, w // 2 :] = after[:, w // 2 :]
    lw = max(1, w // 640)
    split[:, w // 2 - lw // 2 : w // 2 - lw // 2 + lw] = 0.92
    tag = cell * 3
    split = osd.draw_lines(split, [("ORIGINAL", tag, tag, cell)])
    split = osd.draw_lines(split, [(name.upper(), w - tag - osd.text_width(name, cell), tag, cell)])
    gapc = np.empty((before.shape[0] + band(w, [("x", "title")], cell).shape[0], max(4, w // 160), 3), np.float32)
    gapc[:] = BG * 0.6
    sbs = np.concatenate(
        [captioned(before, [("Original", "title")], cell), gapc, captioned(after, [(name, "title")], cell)], 1
    )
    cw, ch = max(16, w // 4), max(12, h // 4)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    zb = cv2.resize(before[y0 : y0 + ch, x0 : x0 + cw], (cw * 2, ch * 2), interpolation=cv2.INTER_NEAREST)
    za = cv2.resize(after[y0 : y0 + ch, x0 : x0 + cw], (cw * 2, ch * 2), interpolation=cv2.INTER_NEAREST)
    zc = cell_for(cw * 2)
    zoom = np.concatenate(
        [
            captioned(zb, [("Original, centre at 200 %", "title")], zc),
            captioned(za, [(f"{name}, centre at 200 %", "title")], zc),
        ],
        1,
    )
    out = {
        "split": save(os.path.join(out_dir, "split.png"), split),
        "side_by_side": save(os.path.join(out_dir, "side_by_side.png"), sbs),
        "zoom": save(os.path.join(out_dir, "zoom.png"), zoom),
        "after": save(os.path.join(out_dir, "after.png"), after),
        "before": save(os.path.join(out_dir, "before.png"), before),
    }
    return out


# ------------------------------------------------------------------------------------------------ ladder
def tape_labels(cfg: dict, sw: int) -> Dict[str, str]:
    V = cfg["vhs"]
    lt = V["luma_tvl"] if isinstance(V["luma_tvl"], list) else [V["luma_tvl"]]
    ct = V["chroma_tvl"] if isinstance(V["chroma_tvl"], list) else [V["chroma_tvl"]]
    speed = "EP" if cfg["tape"] == "V3" else "SP"
    labels = {
        "S0": "Source",
        "S1": "Camcorder: lens softness, AGC noise, date OSD",
        "S2": f"480 interlaced lines, {sw} samples per line",
        "S3": f"SP record: {lt[0]:g} TVL luma, FM noise, dropouts",
        "S4": "Playback: edge halos, head-switching noise",
    }
    if int(V["gens"]) >= 2:
        labels["S5"] = (
            f"2nd generation{' ' + speed if speed == 'EP' else ''}: {vhs.per_gen(lt, 1):g} TVL luma, {vhs.per_gen(ct, 1):g} TVL chroma"
        )
    else:
        labels["S5"] = "Output levels: lifted VHS black"
    return labels


def tube_labels(cfg: dict) -> Dict[str, str]:
    C, T = cfg["crt"], cfg["tube"]
    mask = {
        "slot": f"Slot mask, {C['triads_across']} triads across",
        "grille": f"Aperture grille, {C['triads_across']} stripes across",
        "dot": f"Dot triads, {C['triads_across']} across",
    }[C["mask"]]
    cam = "Camera: one 240-line field, 180 degree shutter" if T.get("fieldOnly") else "Camera: lens bloom, glare, grain"
    return {
        "L0": "Signal on the tube, no line structure",
        "L1": "480 Gaussian beams, width with beam current",
        "L2": mask,
        "L3": "Halation, faceplate bloom",
        "L4": "Front glass: tube black, reflection",
        "L5": "The tube's light on the bezel" + ("" if T.get("fill", 1.0) < 1.0 else " (not in frame at this fill)"),
        "L6": cam,
    }


def stage_names(cfg: dict, keys) -> Dict[str, tuple]:
    """(short OSD name, step counter) per stage id. Counters follow the breakdown's n/5 style; the film's OSD font
    draws S and 5 the same, so stage ids never appear in OSD lettering."""
    mask = {"slot": "Slot mask", "grille": "Aperture grille", "dot": "Dot triads"}[cfg["crt"]["mask"]]
    short = {
        "S0": "Source",
        "S1": "Camcorder",
        "S2": "480 lines",
        "S3": "SP record",
        "S4": "Playback",
        "S5": "2nd generation" if int(cfg["vhs"]["gens"]) >= 2 else "Output levels",
        "L0": "On the tube",
        "L1": "Beams",
        "L2": mask,
        "L3": "Bloom, halation",
        "L4": "Front glass",
        "L5": "Bezel light",
        "L6": "Camera",
        "macro": "Phosphors up close",
    }
    tape = [k for k in keys if k.startswith("S") and k != "S0"]
    tube = [k for k in keys if k.startswith("L") and k != "L0"]
    out = {}
    for k in keys:
        if k in tape:
            n = f"{tape.index(k) + 1}/{len(tape)}"
        elif k in tube:
            n = f"{tube.index(k) + 1}/{len(tube)}"
        else:
            n = ""
        out[k] = (short.get(k, k), n)
    return out


def ladder(cfg: dict, still: Still, out_dir: str, height=None, quality="final", reflection=None) -> Dict[str, Any]:
    """Every stage added cumulatively: S0..S5 (the tape, captured direct) and, for a tube look, L0..L6 (the tube,
    layer by layer) plus a macro of the phosphor mask. Writes each stage and ladder_tape.png / ladder_tube.png."""
    os.makedirs(out_dir, exist_ok=True)
    w, h = preview_size(still["w"], still["h"], height)
    R = pipeline.Renderer(cfg, w, h, still["fps"], quality, reflection)
    snaps: dict = {}
    sig = R.signal(still["hist"], still["index"], snaps=snaps)
    labels = tape_labels(cfg, sig.shape[1])
    out: Dict[str, Any] = {}
    imgs = {"S0": src_at(still, w, h)}
    for k in ("S1", "S2", "S3", "S4", "S5"):
        x = np.clip(snaps[k], 0, 1)
        imgs[k] = np.clip(cv2.resize(x, (w, h), interpolation=cv2.INTER_CUBIC), 0, 1)
    tiles = []
    tw = min(w, 720)
    th = int(round(h * tw / w))
    cell = cell_for(tw)
    for n, k in enumerate(["S0", "S1", "S2", "S3", "S4", "S5"]):
        out[k] = save(os.path.join(out_dir, f"{k}.png"), imgs[k])
        tiles.append(
            captioned(
                cv2.resize(imgs[k], (tw, th), interpolation=cv2.INTER_AREA),
                [(("" if k == "S0" else f"{n}/5  ") + labels[k], "title")],
                cell,
            )
        )
    head = band(
        tiles[0].shape[1] * 3 + 24,
        [
            ("1987, one line at a time", "title"),
            (f"VHS signal model, {presets.load()['vhs'][cfg['tape']]['title']}", "dim"),
        ],
        cell + 1,
    )
    sheet = grid(tiles, 3)
    out["ladder_tape"] = save(
        os.path.join(out_dir, "ladder_tape.png"), np.concatenate([_fit_w(head, sheet.shape[1]), sheet], 0)
    )
    out["labels"] = dict(labels)
    if cfg["capture"] != "direct":
        tl = tube_labels(cfg)
        out["labels"].update(tl)
        tiles = []
        for layer in range(7):
            on_cap = "filmed" if layer == 6 else "screen"
            if layer == 6 and cfg["capture"] == "screen":
                continue
            rgb = R.show(sig, still["index"], layer=layer, capture=on_cap)[0]
            k = f"L{layer}"
            out[k] = save(os.path.join(out_dir, f"{k}.png"), rgb)
            tiles.append(
                captioned(
                    cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_AREA),
                    [(("" if layer == 0 else f"{layer}/{6 if cfg['capture'] == 'filmed' else 5}  ") + tl[k], "title")],
                    cell,
                )
            )
        macro = macro_view(cfg, sig, still, tw, th)
        out["macro"] = save(os.path.join(out_dir, "macro.png"), macro)
        pitch = {"slot": "1 mm slot pitch", "grille": "aperture grille stripes", "dot": "dot triads"}[
            cfg["crt"]["mask"]
        ]
        tiles.append(captioned(macro, [(f"Phosphor triads, {pitch}", "title")], cell))
        sub = f"{cfg['crt']['mask'].capitalize()}-mask CRT model, numpy"
        head = band(tiles[0].shape[1] * 4 + 30, [("A real TV, in code", "title"), (sub, "dim")], cell + 1)
        sheet = grid(tiles, 4)
        out["ladder_tube"] = save(
            os.path.join(out_dir, "ladder_tube.png"), np.concatenate([_fit_w(head, sheet.shape[1]), sheet], 0)
        )
    return out


def macro_view(cfg: dict, sig: np.ndarray, still: Still, w: int, h: int, zoom: float = 6.0) -> np.ndarray:
    """The tube's face up close (the screen at `zoom` times the frame), where the mask resolves."""
    c2 = dict(cfg)
    c2["tube"] = dict(cfg["tube"], fill=zoom)
    R = pipeline.Renderer(c2, w, h, still["fps"], "high")
    rgb = R.show(sig, still["index"], layer=5, capture="screen")[0]
    return rgb


def _fit_w(img: np.ndarray, width: int) -> np.ndarray:
    if img.shape[1] == width:
        return img
    if img.shape[1] > width:
        return img[:, :width]
    pad = np.empty((img.shape[0], width - img.shape[1], 3), np.float32)
    pad[:] = BG
    return np.concatenate([img, pad], 1)


# ------------------------------------------------------------------------------------------------ sheet
def _sheet_job(args):
    look, kw, still, w, h, quality, reflection = args
    cfg = presets.build(look=look, **kw)
    return look, cfg["title"], render_still(cfg, still, w, h, quality, reflection=pipeline.load_reflection(reflection))


def sheet(
    still: Still,
    out_dir: str,
    looks: Optional[List[str]] = None,
    look_kw: Optional[dict] = None,
    tile_h: int = 600,
    cols: int = 4,
    quality="standard",
    jobs=None,
    reflection=None,
) -> Dict[str, str]:
    """Every look (or the chosen ones) on the user's frame, labelled; each full tile is also saved."""
    os.makedirs(out_dir, exist_ok=True)
    data = presets.load()
    looks = looks or list(data["looks"])
    w, h = preview_size(still["w"], still["h"], tile_h, tile_h)
    jobs = jobs or pipeline.default_jobs()
    args = [(lk, look_kw or {}, still, w, h, quality, reflection) for lk in looks]
    res = {}
    if jobs > 1 and len(looks) > 1:
        with ProcessPoolExecutor(min(jobs, len(looks))) as ex:
            for look, title, rgb in ex.map(_sheet_job, args):
                res[look] = (title, rgb)
    else:
        for a in args:
            look, title, rgb = _sheet_job(a)
            res[look] = (title, rgb)
    cell = cell_for(w)
    tiles = [captioned(src_at(still, w, h), [("Original", "title"), ("your frame", "dim")], cell)]
    out: Dict[str, str] = {}
    for look in looks:
        title, rgb = res[look]
        out[look] = save(os.path.join(out_dir, f"look_{look}.png"), rgb)
        tiles.append(captioned(rgb, [(title, "title"), (f"--look {look}", "dim")], cell))
    cols = min(cols, len(tiles))
    out["sheet"] = save(os.path.join(out_dir, "sheet.jpg"), grid(tiles, cols))
    out["original"] = save(os.path.join(out_dir, "original.png"), src_at(still, w, h))
    return out


# ------------------------------------------------------------------------------------------------ clips
def clip(
    cfg: dict,
    src: str,
    out_path: str,
    start=None,
    duration=3.0,
    height=540,
    quality="standard",
    side_by_side=False,
    jobs=None,
    audio="copy",
    reflection=None,
    progress=None,
) -> dict:
    """A short preview clip of the look (optionally original | look side by side)."""
    info = media.probe(src)
    if start is None:
        dur = info.get("duration") or 0
        start = max(0.0, min(dur * 0.4, dur - duration)) if dur else 0.0
    res = pipeline.render_video(
        cfg,
        src,
        out_path if not side_by_side else out_path + ".look.mp4",
        height=height,
        quality=quality,
        start=start,
        duration=duration,
        jobs=jobs,
        audio=audio,
        reflection=reflection,
        progress=progress,
    )
    if side_by_side:
        w, h = res["size"]
        fps = res["fps"]
        cmd = [
            media.ff(),
            "-v",
            "error",
            "-y",
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{duration:.6f}",
            "-i",
            src,
            "-i",
            out_path + ".look.mp4",
            "-filter_complex",
            f"[0:v]fps={fps},scale={w}:{h}:flags=area,setsar=1,format=yuv420p[a];[1:v]setsar=1,format=yuv420p[b];[a][b]hstack=inputs=2[v]",
            "-map",
            "[v]",
            "-map",
            "1:a?",
            "-c:v",
            "libx264" if "libx264" in media.encoders() else "mpeg4",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-shortest",
            out_path,
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode:
            raise media.MediaError("side-by-side assembly failed: " + r.stderr.decode(errors="replace")[-300:])
        os.remove(out_path + ".look.mp4")
        res["path"] = out_path
        res["size"] = (w * 2, h)
    return res
