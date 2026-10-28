"""Looks, stage toggles and strength knobs: everything that turns presets/looks.json into one render config."""

from __future__ import annotations

import copy
import json
import os
from typing import Dict, Iterable, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.normpath(os.path.join(HERE, "..", "..", "presets", "looks.json"))

CAPTURES = ("direct", "screen", "filmed")
MASKS = ("slot", "grille", "dot", "none")
FRAMES = ("native", "crop43", "pad43")
TAPE_STAGES = ("camcorder", "date", "record", "playback", "dub")
TUBE_STAGES = ("beams", "mask", "glow", "glass", "light", "camera")
STAGES = TAPE_STAGES + TUBE_STAGES

# name -> (help, where it acts)
KNOBS = {
    "noise": "tape and camera noise (AGC gain, FM luma, colour-under chroma)",
    "dropouts": "dropouts per frame",
    "wobble": "time-base error: line jitter, tape-stretch wobble, top flagging, head-switching skew, tracking band",
    "halos": "playback edge-enhancement halos and their ghost",
    "softness": "bandwidth loss: luma and chroma TVL divided by the strength, lens softness scaled (0 = full bandwidth)",
    "bleed": "colour bleed: chroma bandwidth divided by the strength, chroma delay scaled",
    "fade": "colour fade and lifted blacks (0 = full colour and clean levels)",
    "warmth": "camcorder white balance away from neutral",
    "bloom": "camcorder highlight bloom",
    "scanlines": "visibility of the beam lines on the tube (0 = no line structure)",
    "mask": "contrast of the phosphor mask",
    "glow": "faceplate bloom, halation and blooming whites",
    "reflection": "the room's reflection and the lamp's specular on the glass",
    "roll": "the refresh roll bar of the filming camera",
    "lens": "the filming camera's lens bloom and glare",
    "grain": "the filming camera's grain",
    "lift": "milky faceplate scatter and the raster's lifted black",
}


def load(path: Optional[str] = None) -> dict:
    with open(path or PRESETS, encoding="utf-8") as f:
        return json.load(f)


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k.startswith("_"):
            continue
        out[k] = copy.deepcopy(v)
    return out


def _scale(d: dict, key: str, s: float):
    v = d[key]
    d[key] = [x * s for x in v] if isinstance(v, list) else v * s


def _toward(d: dict, key: str, s: float, neutral: float):
    v = d[key]
    d[key] = [neutral + s * (x - neutral) for x in v] if isinstance(v, list) else neutral + s * (v - neutral)


def _div_tvl(d: dict, key: str, s: float):
    v = d[key]
    f = lambda x: 0 if s <= 0 else x / s
    d[key] = [f(x) for x in v] if isinstance(v, list) else f(v)


def apply_knob(cfg: dict, name: str, s: float):
    V, C, T, K = cfg["vhs"], cfg["crt"], cfg["tube"], cfg["camera"]
    s = max(0.0, float(s))
    if name == "noise":
        for k in ("gain_noise", "luma_noise", "chroma_noise", "chroma_line_noise"):
            _scale(V, k, s)
    elif name == "dropouts":
        _scale(V, "dropouts", s)
    elif name == "wobble":
        for k in ("jitter", "wobble", "flag_amp", "hs_skew", "tracking_band"):
            _scale(V, k, s)
    elif name == "halos":
        _scale(V, "ee_amt", s)
        _scale(V, "ring_amt", s)
    elif name == "softness":
        _div_tvl(V, "luma_tvl", s)
        _div_tvl(V, "chroma_tvl", s)
        _scale(V, "cam_soft", s)
    elif name == "bleed":
        _div_tvl(V, "chroma_tvl", s)
        _scale(V, "chroma_delay", s)
    elif name == "fade":
        _toward(V, "chroma_sat", s, 1.0)
        _scale(V, "black_lift", s)
        _toward(V, "white", s, 1.0)
    elif name == "warmth":
        _toward(V, "wb", s, 1.0)
    elif name == "bloom":
        _scale(V, "bloom_amt", s)
    elif name == "scanlines":
        if s <= 0:
            cfg["stages"]["beams"] = False
        else:
            T["beamK"] = T.get("beamK", 1.0) * s**-0.5
    elif name == "mask":
        T["maskK"] = T.get("maskK", 1.0) * s
    elif name == "glow":
        _scale(C, "bloom_amt", s)
        _scale(C, "halation_amt", s)
        _scale(T, "hiBloom", s)
    elif name == "reflection":
        for k in ("reflection", "specular", "sheen"):
            _scale(T, k, s)
    elif name == "roll":
        _scale(T, "roll", s)
    elif name == "lens":
        _scale(K, "bloom", s)
        _scale(K, "glare", s)
    elif name == "grain":
        _scale(K, "grainLuma", s)
        _scale(K, "grainChroma", s)
    elif name == "lift":
        _scale(T, "scatter", s)
        _scale(T, "picLift", s)
    else:
        raise ValueError(f"unknown strength '{name}'. Known: {', '.join(KNOBS)}")


def parse_kv(items: Iterable[str]) -> List[tuple]:
    out = []
    for item in items or []:
        for part in _split_top(item):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise ValueError(f"expected key=value, got '{part}'")
            k, v = part.split("=", 1)
            out.append((k.strip(), v.strip()))
    return out


def _split_top(s: str) -> List[str]:
    """Split on commas that are not inside brackets (so 'a=[1,2],b=3' is two items)."""
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _value(v: str):
    try:
        return json.loads(v)
    except ValueError:
        return v


def apply_set(cfg: dict, key: str, raw: str):
    sections = {"vhs": cfg["vhs"], "crt": cfg["crt"], "tube": cfg["tube"], "camera": cfg["camera"]}
    if "." in key:
        sec, k = key.split(".", 1)
        if sec not in sections:
            raise ValueError(f"unknown section '{sec}' in '{key}' (vhs, crt, tube, camera)")
        if k not in sections[sec]:
            raise ValueError(f"unknown parameter '{k}' in {sec}")
        sections[sec][k] = _value(raw)
        return
    hits = [s for s, d in sections.items() if key in d]
    if not hits:
        raise ValueError(f"unknown parameter '{key}'")
    if len(hits) > 1:
        raise ValueError(f"'{key}' exists in {', '.join(hits)}: write it as section.{key}")
    sections[hits[0]][key] = _value(raw)


def build(
    data: Optional[dict] = None,
    look: Optional[str] = "vhs-on-tv",
    tape: Optional[str] = None,
    tube: Optional[str] = None,
    treatment: Optional[str] = None,
    capture: Optional[str] = None,
    mask: Optional[str] = None,
    curvature: Optional[float] = None,
    fill: Optional[float] = None,
    date: Optional[str] = None,
    no_date: bool = False,
    date_pos: Optional[str] = None,
    gens: Optional[int] = None,
    off: Iterable[str] = (),
    strengths: Optional[Dict[str, float]] = None,
    sets: Iterable[tuple] = (),
    seed: int = 0,
    frame: str = "native",
    mix: float = 1.0,
) -> dict:
    """One render config: {look, title, vhs, crt, tube, camera, capture, stages, seed, frame, mix}."""
    data = data or load()
    L = {}
    if look:
        if look not in data["looks"]:
            raise ValueError(f"unknown look '{look}'. Known: {', '.join(data['looks'])}")
        L = data["looks"][look]
    tape = tape or L.get("tape", "V1")
    tube_key = tube if tube is not None else L.get("tube")
    if tube_key in ("none", "off", ""):
        tube_key = None
    treatment = treatment or L.get("treatment", "T0")
    capture = capture or L.get("capture", "direct")
    if tube is not None and tube_key and capture == "direct" and not L.get("tube"):
        capture = "screen"
    if capture not in CAPTURES:
        raise ValueError(f"unknown capture '{capture}' ({', '.join(CAPTURES)})")
    if capture != "direct" and not tube_key:
        tube_key = "C2"
    if tape not in data["vhs"]:
        raise ValueError(f"unknown tape '{tape}'. Known: {', '.join(data['vhs'])}")
    if tube_key and tube_key not in data["crt"]:
        raise ValueError(f"unknown tube '{tube_key}'. Known: {', '.join(data['crt'])}")
    if treatment not in data["treatments"]:
        raise ValueError(f"unknown treatment '{treatment}'. Known: {', '.join(data['treatments'])}")
    if frame not in FRAMES:
        raise ValueError(f"unknown frame mode '{frame}' ({', '.join(FRAMES)})")

    V = _merge(data["base_vhs"], data["vhs"][tape])
    C = _merge(data["base_crt"], data["crt"][tube_key or "C2"])
    T = _merge(data["tube"], {})
    K = _merge(data["camera"], {})
    tr = data["treatments"][treatment]
    C.update(copy.deepcopy(tr.get("crt", {})))
    T.update(copy.deepcopy(tr.get("tube", {})))
    K.update(copy.deepcopy(tr.get("camera", {})))
    T.update(copy.deepcopy(L.get("tube_overrides", {})))
    stages = {s: True for s in STAGES}
    if capture == "direct":
        for s in TUBE_STAGES:
            stages[s] = False
    elif capture == "screen":
        stages["camera"] = False
    cfg = {
        "look": look,
        "title": L.get("title", look or "custom"),
        "tape": tape,
        "tube_preset": tube_key if capture != "direct" else None,
        "treatment": treatment if capture != "direct" else None,
        "vhs": V,
        "crt": C,
        "tube": T,
        "camera": K,
        "capture": capture,
        "stages": stages,
        "seed": int(seed),
        "frame": frame,
        "mix": float(mix),
        "strengths": {},
    }
    if mask:
        cfg["mask_set"] = True
        if mask not in MASKS:
            raise ValueError(f"unknown mask '{mask}' ({', '.join(MASKS)})")
        if mask == "none":
            stages["mask"] = False
        else:
            if mask == "grille" and C["mask"] != "grille":
                C["damper_wires"] = [0.335, 0.665]
                C["triads_across"] = 700
            if mask != "grille":
                C["damper_wires"] = []
            if mask == "dot" and C["mask"] != "dot":
                C["triads_across"] = 620
            C["mask"] = mask
    if curvature is not None:
        T["curvature"] = float(curvature)
    if fill is not None:
        T["fill"] = float(fill)
    if date is not None:
        V["osd"] = date
    if no_date:
        stages["date"] = False
    if date_pos:
        if date_pos not in ("br", "bl", "tr", "tl"):
            raise ValueError("date position must be br, bl, tr or tl")
        V["osd_pos"] = date_pos
    if gens is not None:
        V["gens"] = max(1, int(gens))
    for s in off or ():
        s = s.strip()
        if not s:
            continue
        if s not in STAGES:
            raise ValueError(f"unknown stage '{s}'. Stages: {', '.join(STAGES)}")
        stages[s] = False
    if not stages["dub"]:
        V["gens"] = 1
    for k, v in (strengths or {}).items():
        apply_knob(cfg, k, float(v))
        cfg["strengths"][k] = float(v)
    for k, v in sets or ():
        apply_set(cfg, k, v)
    return cfg


def describe(cfg: dict, data: Optional[dict] = None) -> str:
    data = data or load()
    parts = [f"tape {cfg['tape']} ({data['vhs'][cfg['tape']]['title']})"]
    if cfg["capture"] != "direct":
        parts.append(
            f"tube {cfg['tube_preset']} ({data['crt'][cfg['tube_preset']]['title']}"
            + (f", {cfg['crt']['mask']} mask)" if cfg.get("mask_set") else ")")
        )
        parts.append(f"treatment {cfg['treatment']} ({data['treatments'][cfg['treatment']]['title']})")
    parts.append(f"capture {cfg['capture']}")
    offs = [s for s, v in cfg["stages"].items() if not v and not (cfg["capture"] == "direct" and s in TUBE_STAGES)]
    if cfg["capture"] == "screen" and "camera" in offs:
        offs.remove("camera")
    if offs:
        parts.append("off: " + ", ".join(offs))
    if cfg["strengths"]:
        parts.append("strengths: " + ", ".join(f"{k}={v:g}" for k, v in cfg["strengths"].items()))
    return "; ".join(parts)
