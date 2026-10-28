"""The VHS signal model: a 1987 consumer camcorder, an SP recording, the playback deck, and optionally a
deck-to-deck dub, with a snapshot after every stage. A line-for-line port of the reference look-development code
(camcorder / record / playback / vhs_signal), with SciPy replaced by sigproc.py.

Signal model (NTSC VHS, 480 visible lines; 720 samples per picture height along each line, so 960 samples per
active line on a 4:3 picture, 18.25 samples per microsecond):
  S1 camcorder: lens/CCD softness, tungsten white balance, highlight bloom, CCD vertical smear, tube lag, knee,
     AGC gain noise, date burned in
  S2 480-line interlaced raster
  S3 per generation, record: FM luma low-pass (TVL), colour-under chroma low-pass (TVL) + 1H comb, tape luma and
     chroma noise, dropouts, chroma delay
  S4 per generation, playback: time-base error (line jitter, tape-stretch wobble, top flagging, head-switching
     skew), edge-enhancement halos, head-switching noise, tracking band
  S5 the second generation (a dub), then output levels

Rasters: the camcorder works at CW x CH with CH = 720 square pixels (960 x 720 for 4:3). The tape has LINES = 480
lines of SW = CW samples, so TVL figures (per picture height) mean the same thing at any aspect ratio.
"""

from __future__ import annotations

import math
import zlib
from typing import Dict, List, Optional

import cv2
import numpy as np

from . import osd
from .sigproc import frac_shift, gauss1d, gauss2d, shift_rows

LINES = 480
CH = 720

RGB2YIQ = np.array([[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]], np.float32)
YIQ2RGB = np.linalg.inv(RGB2YIQ).astype(np.float32)


def raster_width(aspect: float) -> int:
    """Camcorder raster width (= samples per tape line) for a picture aspect ratio, even, at least 96."""
    return max(96, int(round(CH * aspect / 2.0)) * 2)


def per_gen(v, g):
    return v[min(g, len(v) - 1)] if isinstance(v, (list, tuple)) else v


def tvl_sigma(tvl: float) -> float:
    """Gaussian sigma (samples) whose MTF falls to 10 % at `tvl` TV lines per picture height.
    (looktest: f = tvl * 4/3 / 2 / 960 cycles per sample on a 4:3 line; 960 = 720 * 4/3.)"""
    if not tvl or tvl <= 0:
        return 0.0
    f = tvl / 2.0 / CH
    return 0.3416 / f


def rngs(i: int, P: dict, seed: int = 0):
    """Per-frame random streams (camcorder, tape). Seed 0 reproduces the reference implementation's noise exactly."""
    tape_key = 20_000 + i * 7 + zlib.crc32(P["name"].encode()) % 1000
    if seed:
        return np.random.default_rng([seed, 10_000 + i]), np.random.default_rng([seed, tape_key])
    return np.random.default_rng(10_000 + i), np.random.default_rng(tape_key)


def camcorder(hist: List[np.ndarray], P: dict, rng, stages: Optional[Dict[str, bool]] = None) -> np.ndarray:
    """The frame as the 1987 camcorder saw it (gamma-encoded video level, CW x CH).
    hist = [frame i, i-1, i-2, i-3] as float32 RGB 0..1 on the camcorder raster (earlier frames feed the tube lag)."""
    stages = stages or {}
    CHh, CWw = hist[0].shape[:2]
    if not stages.get("camcorder", True):
        x = hist[0].copy()
        if P.get("osd") and stages.get("date", True):
            x = osd.draw_date(np.clip(x, 0, 1.1), P["osd"], P.get("osd_pos", "br"))
        return np.clip(x, 0, 1.1).astype(np.float32)

    def lin_hi(j):
        x = gauss2d(hist[min(j, len(hist) - 1)], P["cam_soft"], P["cam_soft"])
        lin = np.clip(x * np.array(P["wb"], np.float32), 0, None) ** 2.2
        return lin, np.clip(lin - P["bloom_thresh"] ** 2.2, 0, None)

    lin, hi = lin_hi(0)
    if P["tube_lag"] > 0:  # Saticon image lag: earlier frames' highlights persist and decay (comet tails)
        for k, wgt in ((1, P["tube_lag"]), (2, P["tube_lag"] ** 2), (3, P["tube_lag"] ** 3)):
            _, hk = lin_hi(k)
            hi = np.maximum(hi, wgt * hk)
            lin = np.maximum(lin, wgt * hk * 1.2)
    r = P["bloom_r"]
    lin = lin + P["bloom_amt"] * (gauss2d(hi, r, r) + 0.5 * gauss2d(hi, 3 * r, 3 * r))
    if P["ccd_smear"] > 0:  # interline-CCD smear: a vertical stripe through every clipped highlight
        clip_hi = np.clip(lin - 0.85, 0, None)
        col = gauss1d(clip_hi.mean(0), 1.0, axis=0)
        lin = lin + P["ccd_smear"] * 6.0 * col[None]
    x = lin ** (1 / 2.2)
    m = x.mean(2, keepdims=True)  # camera colour matrix saturation
    x = m + P["sat"] * (x - m)
    k = P["knee"]  # white knee: unit slope at the knee point, compressing toward an asymptote just above white
    A = (1 - k) * P["knee_slope"] * 3
    x = np.where(x > k, k + A * (1 - np.exp(-(x - k) / A)), x)
    if P["gain_noise"] > 0:  # AGC gain-up noise (gets the tape's bandwidth afterwards: streaky, not grain)
        n = rng.normal(0, P["gain_noise"], (CHh, CWw)).astype(np.float32)
        nc = rng.normal(0, P["gain_noise"] * 0.6, (CHh, CWw, 3)).astype(np.float32)
        x = x + (n[..., None] + nc) * (1.1 - 0.6 * np.clip(x, 0, 1))
    if P.get("osd") and stages.get("date", True):
        x = osd.draw_date(np.clip(x, 0, 1.1), P["osd"], P.get("osd_pos", "br"))
    return np.clip(x, 0, 1.1).astype(np.float32)


def record(yiq: np.ndarray, P: dict, g: int, rng) -> np.ndarray:
    L, SW = yiq.shape[:2]
    Y, I, Q = yiq[..., 0], yiq[..., 1], yiq[..., 2]
    Y = gauss1d(Y, tvl_sigma(per_gen(P["luma_tvl"], g)), axis=1)
    cs = tvl_sigma(per_gen(P["chroma_tvl"], g))
    I = gauss1d(I, cs, axis=1)
    Q = gauss1d(Q, cs, axis=1)
    if P["chroma_comb"]:
        I = 0.5 * (I + np.roll(I, 1, 0))
        Q = 0.5 * (Q + np.roll(Q, 1, 0))
    sat = per_gen(P["chroma_sat"], g)
    I, Q = I * sat, Q * sat
    # tape noise: FM luma noise, horizontally correlated, stronger in the darks
    ln = per_gen(P["luma_noise"], g)
    n = gauss1d(rng.normal(0, 1, (L, SW)).astype(np.float32), 1.1, axis=1) * ln * 1.6
    Y = Y + n * (1.25 - 0.6 * np.clip(Y, 0, 1))
    # colour-under chroma noise: blotches a few chroma cycles long, two-line correlated
    cn = per_gen(P["chroma_noise"], g)
    for C in (I, Q):
        blot = gauss2d(rng.normal(0, 1, (L, SW)).astype(np.float32), 0.8, cs * 0.45)
        blot *= cn / (blot.std() + 1e-6)
        C += blot + gauss1d(rng.normal(0, per_gen(P["chroma_line_noise"], g), L), 1.5)[:, None]
    # dropouts: oxide missing for a moment, bright streak with a decaying tail, half-strength on the next line
    nd = rng.poisson(per_gen(P["dropouts"], g))
    lo, hi = P["dropout_len"]
    for _ in range(nd):
        r, c0 = int(rng.integers(0, L - 2)), int(rng.integers(0, max(1, SW - 40)))
        Ln = int(rng.integers(lo, hi))
        c1 = min(SW, c0 + Ln)
        prof = np.exp(-np.linspace(0, 2.5, c1 - c0)) * 0.6 + 0.4
        amp = rng.uniform(0.35, 0.8)
        if rng.random() < 0.25:  # dropout compensator repeats the line above instead (subtle)
            Y[r, c0:c1] = Y[r - 1, c0:c1]
        else:
            Y[r, c0:c1] = Y[r, c0:c1] * (1 - prof * 0.7) + amp * prof
            Y[r + 1, c0 + 2 : c1] += 0.35 * amp * prof[: c1 - c0 - 2]
            I[r, c0:c1] *= 0.3
            Q[r, c0:c1] *= 0.3
    d = per_gen(P["chroma_delay"], g)
    IQ = frac_shift(np.stack([I, Q], -1).astype(np.float32), d)
    return np.stack([Y, IQ[..., 0], IQ[..., 1]], -1).astype(np.float32)


def playback(yiq: np.ndarray, P: dict, g: int, rng, t: float) -> np.ndarray:
    LN, SW = yiq.shape[:2]
    L = np.arange(LN, dtype=np.float32)
    dx = per_gen(P["wobble"], g) * np.sin(2 * math.pi * (L / LN * P["wobble_cycles"] + t * P["wobble_hz"]))
    dx += gauss1d(rng.normal(0, per_gen(P["jitter"], g) * 1.6, LN), 1.2).astype(np.float32)
    fl = per_gen(P["flag_lines"], g)
    top = L < fl
    dx[top] += (fl - L[top]) ** 1.6 * per_gen(P["flag_amp"], g)
    hsl = per_gen(P["hs_lines"], g)
    hs = L >= LN - hsl
    dx[hs] += per_gen(P["hs_skew"], g) * (1 + (L[hs] - (LN - hsl)) / hsl) * 0.6 + rng.normal(0, 2.0, hs.sum())
    band = np.zeros(LN, np.float32)
    if P["tracking_band"] > 0:  # mistracked band near the bottom, drifting slowly
        yc = LN * (P["tracking_pos"] + 0.03 * math.sin(t * 0.7))
        band = P["tracking_band"] * np.exp(-0.5 * ((L - yc) / (P["tracking_lines"] / 2.355)) ** 2)
        dx += band * rng.normal(0, 3.0, LN)
    out = shift_rows(yiq, dx.astype(np.float32))
    Y = out[..., 0]
    # playback sharpness: edge-enhancement overshoot (the white outline VHS is known for) + a faint ghost right
    es = per_gen(P["ee_sigma"], g)
    hf = Y - gauss1d(Y, es, axis=1)
    Y = Y + per_gen(P["ee_amt"], g) * hf + per_gen(P["ring_amt"], g) * np.roll(hf, int(per_gen(P["ring_delay"], g)), 1)
    # head-switching noise lines
    Y[LN - hsl :] += rng.normal(0.04, 0.07, (hsl, SW))
    out[LN - hsl :, :, 1:] *= 0.4
    if P["tracking_band"] > 0:  # bright noise streaks inside the band
        for r in range(LN):
            if band[r] > 0.08:
                k = rng.poisson(band[r] * 7)
                for _ in range(k):
                    c0 = int(rng.integers(0, max(1, SW - 20)))
                    ln = int(rng.integers(6, 60))
                    Y[r, c0 : c0 + ln] = Y[r, c0 : c0 + ln] * 0.3 + rng.uniform(0.5, 0.95)
                Y[r] += rng.normal(0, 0.05 * band[r], SW)
                out[r, :, 1:] *= 1 - 0.6 * band[r]
    out[..., 0] = Y
    return out


def to_rgb(yiq: np.ndarray) -> np.ndarray:
    return yiq @ YIQ2RGB.T


def levels(rgb: np.ndarray, P: dict) -> np.ndarray:
    rgb = P["black_lift"] + (P["white"] - P["black_lift"]) * np.clip(rgb, 0, 1)
    return np.clip(rgb, 0, 1).astype(np.float32)


def vhs_signal(
    hist: List[np.ndarray],
    P: dict,
    i: int,
    fps: float,
    seed: int = 0,
    stages: Optional[Dict[str, bool]] = None,
    snaps: Optional[dict] = None,
    post=None,
) -> np.ndarray:
    """LINES x SW gamma-encoded RGB of frame i as it leaves the final VCR (levels included).

    stages: toggles {camcorder, date, record, playback}; P["gens"] sets the generations (2 = a dub).
    snaps: if a dict, filled with the S1..S5 signals (vhs_stages.py's snapshots).
    post: optional callable(yiq, rng, i) applied after the last playback (the rewind search effect)."""
    stages = stages or {}
    rng_cam, rng = rngs(i, P, seed)
    t = i / float(fps)
    x = camcorder(hist, P, rng_cam, stages)
    if snaps is not None:
        snaps["S1"] = x
    SW = x.shape[1]
    x = cv2.resize(x, (SW, LINES), interpolation=cv2.INTER_AREA)  # interlaced 480-line raster
    yiq = x @ RGB2YIQ.T
    if P["hue_deg"]:
        a = math.radians(P["hue_deg"])
        I, Q = yiq[..., 1].copy(), yiq[..., 2].copy()
        yiq[..., 1], yiq[..., 2] = I * math.cos(a) - Q * math.sin(a), I * math.sin(a) + Q * math.cos(a)
    if snaps is not None:
        snaps["S2"] = to_rgb(yiq)
    for g in range(int(P["gens"])):
        if stages.get("record", True):
            yiq = record(yiq, P, g, rng)
        if snaps is not None and g == 0:
            snaps["S3"] = to_rgb(yiq)
        if stages.get("playback", True):
            yiq = playback(yiq, P, g, rng, t + 0.37 * g)
        if snaps is not None and g == 0:
            snaps["S4"] = to_rgb(yiq)
    if post is not None:
        yiq = post(yiq, rng, i)
    if P["agc_pump"]:
        yiq[..., 0] *= 1 + P["agc_pump"] * math.sin(2 * math.pi * 0.31 * t)
    rgb = levels(to_rgb(yiq), P)
    if snaps is not None:
        snaps["S5"] = rgb
    return rgb
