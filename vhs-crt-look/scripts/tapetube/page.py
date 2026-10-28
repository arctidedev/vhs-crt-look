"""The offline comparison page (one HTML file, everything inline, no network) and the one-shot preview that renders
every look once and reuses it for the contact sheet, the stills and the page."""

from __future__ import annotations

import base64
import json
import os
import webbrowser
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Optional

import cv2
import numpy as np

from . import media, osd, pipeline, presets, preview

SCRIPT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vhslook.py"))
MAX_CLIP_EMBED = 40 * 2**20


def data_uri(rgb: np.ndarray, max_w: Optional[int] = None, quality: int = 90) -> str:
    img = rgb
    if max_w and img.shape[1] > max_w:
        img = cv2.resize(img, (max_w, int(round(img.shape[0] * max_w / img.shape[1]))), interpolation=cv2.INTER_AREA)
    bgr = (np.clip(img, 0, 1)[..., ::-1] * 255).round().astype(np.uint8)
    ok, buf = cv2.imencode(".webp", bgr, [cv2.IMWRITE_WEBP_QUALITY, quality])
    mime = "image/webp"
    if not ok:
        ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _q(p: str) -> str:
    return '"' + str(p).replace('"', '\\"') + '"'


def command(input_path: str, look_flags: List[str], out_path: str) -> str:
    return " ".join(["python", _q(SCRIPT), "render", _q(os.path.abspath(input_path)), _q(out_path)] + list(look_flags))


def suggested_output(input_path: str, tag: str) -> str:
    stem, ext = os.path.splitext(os.path.abspath(input_path))
    if media.kind(input_path) == "image":
        ext = ".png" if ext.lower() not in (".png", ".tif", ".tiff") else ext
    else:
        ext = ".mp4" if ext.lower() not in (".mp4", ".mov", ".mkv") else ext
    return f"{stem}_{tag}{ext}"


# ------------------------------------------------------------------------------------------------ renders
def _look_job(args):
    look, kw, still, w, h, quality, reflection = args
    cfg = presets.build(look=look, **kw)
    rgb = preview.render_still(cfg, still, w, h, quality, reflection=pipeline.load_reflection(reflection))
    return look, cfg["title"], cfg, rgb


def render_looks(still, looks, kw, w, h, quality="final", jobs=None, reflection=None) -> Dict[str, tuple]:
    jobs = jobs or pipeline.default_jobs()
    args = [(lk, kw or {}, still, w, h, quality, reflection) for lk in looks]
    out = {}
    if jobs > 1 and len(args) > 1:
        with ProcessPoolExecutor(min(jobs, len(args))) as ex:
            for look, title, cfg, rgb in ex.map(_look_job, args):
                out[look] = (title, cfg, rgb)
    else:
        for a in args:
            look, title, cfg, rgb = _look_job(a)
            out[look] = (title, cfg, rgb)
    return out


def _same(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


# ------------------------------------------------------------------------------------------------ one shot
def preview_all(
    input_path,
    out_dir,
    cfg,
    looks=None,
    look_kw=None,
    t=None,
    height=None,
    clip=True,
    jobs=None,
    reflection=None,
    open_page=False,
    progress=None,
    primary_flags=None,
    common_flags=None,
) -> dict:
    """Everything needed to choose a look, in one folder: sheet.jpg (all looks), compare/ (split, side by side,
    zoom), ladder/ (each stage added cumulatively), clip_side_by_side.mp4 (video), page.html (all of it)."""
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    data = presets.load()
    looks = looks or list(data["looks"])
    look_kw = look_kw or {}
    still = preview.load_still(input_path, cfg["frame"], t)
    w, h = preview.preview_size(still["w"], still["h"], height, 720)
    renders = render_looks(still, looks, look_kw, w, h, "final", jobs, reflection)
    named = presets.build(look=cfg["look"], **look_kw) if cfg.get("look") else None
    if named is not None and _same(named, cfg) and cfg["look"] in renders:
        primary_id = cfg["look"]
        primary_rgb = renders[primary_id][2]
    else:
        primary_id = "custom"
        primary_rgb = preview.render_still(cfg, still, w, h, "final", reflection=pipeline.load_reflection(reflection))
    res: Dict[str, object] = {"folder": out_dir}
    # contact sheet from the same renders
    tile_w = min(w, 480)
    tile_h = int(round(h * tile_w / w))
    cell = preview.cell_for(tile_w)
    tiles = [
        preview.captioned(
            cv2.resize(preview.src_at(still, w, h), (tile_w, tile_h), interpolation=cv2.INTER_AREA),
            [("Original", "title"), ("your frame", "dim")],
            cell,
        )
    ]
    os.makedirs(os.path.join(out_dir, "looks"), exist_ok=True)
    for lk in looks:
        title, _, rgb = renders[lk]
        preview.save(os.path.join(out_dir, "looks", f"{lk}.png"), rgb)
        tiles.append(
            preview.captioned(
                cv2.resize(rgb, (tile_w, tile_h), interpolation=cv2.INTER_AREA),
                [(title, "title"), (f"--look {lk}", "dim")],
                cell,
            )
        )
    res["sheet"] = preview.save(os.path.join(out_dir, "sheet.jpg"), preview.grid(tiles, min(4, len(tiles))))
    res["looks"] = os.path.join(out_dir, "looks")
    comp = preview.compare(cfg, still, os.path.join(out_dir, "compare"), h, "final", look_rgb=primary_rgb)
    res["compare"] = {k: v for k, v in comp.items() if k in ("split", "side_by_side", "zoom")}
    lad = preview.ladder(cfg, still, os.path.join(out_dir, "ladder"), h, "final", pipeline.load_reflection(reflection))
    labels = lad.pop("labels")
    res["ladder"] = {k: v for k, v in lad.items() if k.startswith("ladder_")}
    clip_path = None
    if clip and still["kind"] == "video":
        clip_path = os.path.join(out_dir, "clip_side_by_side.mp4")
        ch = min(540, h)
        preview.clip(
            cfg,
            input_path,
            clip_path,
            start=max(0.0, still["t"] - 1.5),
            duration=3.0,
            height=ch,
            quality="standard",
            side_by_side=True,
            jobs=jobs,
            reflection=reflection,
            progress=progress,
        )
        res["clip"] = clip_path
    page_path = os.path.join(out_dir, "page.html")
    write_page(
        page_path,
        input_path,
        still,
        w,
        h,
        cfg,
        primary_id,
        primary_rgb,
        renders,
        looks,
        lad,
        labels,
        clip_path,
        primary_flags,
        common_flags,
    )
    res["page"] = page_path
    res["primary"] = primary_id
    res["describe"] = presets.describe(cfg, data)
    if open_page:
        webbrowser.open("file://" + page_path if os.name != "nt" else page_path)
    return res


def build(
    input_path,
    out_html,
    cfg,
    looks=None,
    look_kw=None,
    t=None,
    height=None,
    clip=None,
    jobs=None,
    reflection=None,
    primary_flags=None,
    common_flags=None,
) -> str:
    """The page alone (renders what it needs; stage images go to a folder next to the page)."""
    data = presets.load()
    looks = looks or list(data["looks"])
    look_kw = look_kw or {}
    still = preview.load_still(input_path, cfg["frame"], t)
    w, h = preview.preview_size(still["w"], still["h"], height, 720)
    renders = render_looks(still, looks, look_kw, w, h, "final", jobs, reflection)
    primary_rgb = preview.render_still(cfg, still, w, h, "final", reflection=pipeline.load_reflection(reflection))
    side = os.path.splitext(os.path.abspath(out_html))[0] + "_stages"
    lad = preview.ladder(cfg, still, side, h, "final", pipeline.load_reflection(reflection))
    labels = lad.pop("labels")
    write_page(
        out_html,
        input_path,
        still,
        w,
        h,
        cfg,
        "custom",
        primary_rgb,
        renders,
        looks,
        lad,
        labels,
        clip,
        primary_flags,
        common_flags,
    )
    return out_html


# ------------------------------------------------------------------------------------------------ page
def write_page(
    path,
    input_path,
    still,
    w,
    h,
    cfg,
    primary_id,
    primary_rgb,
    renders,
    looks,
    lad,
    labels,
    clip_path,
    primary_flags=None,
    common_flags=None,
):
    data = presets.load()
    common_flags = list(common_flags or [])
    if primary_flags is None:
        primary_flags = ["--look", cfg["look"]] + common_flags if cfg.get("look") else common_flags
    original = preview.src_at(still, w, h)
    items = []
    if primary_id == "custom":
        items.append(
            {
                "id": "custom",
                "title": f"{cfg['title']} (your settings)",
                "desc": presets.describe(cfg, data),
                "cmd": command(input_path, primary_flags, suggested_output(input_path, "vhslook")),
                "img": data_uri(primary_rgb),
                "thumb": data_uri(primary_rgb, 360, 82),
            }
        )
    for lk in looks:
        title, lcfg, rgb = renders[lk]
        items.append(
            {
                "id": lk,
                "title": title,
                "desc": data["looks"][lk]["desc"],
                "spec": presets.describe(lcfg, data),
                "cmd": command(input_path, ["--look", lk] + common_flags, suggested_output(input_path, lk)),
                "img": data_uri(rgb),
                "thumb": data_uri(rgb, 360, 82),
            }
        )
    stages = []
    order = ["S0", "S1", "S2", "S3", "S4", "S5", "L0", "L1", "L2", "L3", "L4", "L5", "L6", "macro"]
    names = preview.stage_names(cfg, [k for k in order if k in lad])
    for k in order:
        if k not in lad:
            continue
        rgb, _, _ = media.read_image(lad[k])
        if rgb.shape[:2] != (h, w) and k != "macro":
            rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
        label = labels.get(k, "Phosphor mask up close, the screen at 6x")
        stages.append(
            {
                "id": "MACRO" if k == "macro" else k,
                "group": "tape" if k.startswith("S") else "tube",
                "label": label,
                "short": names[k][0],
                "counter": names[k][1],
                "img": data_uri(rgb),
                "thumb": data_uri(rgb, 360, 82),
            }
        )
    clip_uri = None
    clip_rel = None
    if clip_path and os.path.exists(clip_path):
        if os.path.getsize(clip_path) <= MAX_CLIP_EMBED:
            with open(clip_path, "rb") as f:
                clip_uri = "data:video/mp4;base64," + base64.b64encode(f.read()).decode("ascii")
        else:
            clip_rel = os.path.relpath(clip_path, os.path.dirname(os.path.abspath(path)))
    when = f"frame at {still['t']:.2f} s, " if still["kind"] == "video" else ""
    payload = {
        "glyphs": osd.GLYPHS,
        "original": data_uri(original),
        "looks": items,
        "primary": items[0]["id"] if primary_id == "custom" else primary_id,
        "stages": stages,
        "clip": clip_uri or clip_rel,
        "meta": {
            "file": os.path.basename(input_path),
            "w": w,
            "h": h,
            "when": when,
            "tapeHead": "1987, one line at a time",
            "tubeHead": "A real TV, in code",
        },
    }
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html_text = (
        _template()
        .replace("__DATA__", blob)
        .replace("__AR__", f"{w} / {h}")
        .replace("__TITLE__", _esc(f"{os.path.basename(input_path)}: VHS and CRT looks"))
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return path


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


TEMPLATE_PATH = os.path.join(os.path.dirname(SCRIPT), "page-template.html")


def _template() -> str:
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        return f.read()
